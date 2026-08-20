from __future__ import annotations

import pytest

from inglenook.probes import (
    comfy_is_busy,
    comfy_vram_free_ratio,
    llama_is_reachable,
    llama_models_have_weights,
    llama_props_have_weights,
    llama_weights_loaded,
)
from inglenook.types import Backend, Role


def test_comfy_busy_when_queue_remaining_positive() -> None:
    assert comfy_is_busy({"exec_info": {"queue_remaining": 2}}) is True


def test_comfy_idle_when_queue_empty() -> None:
    assert comfy_is_busy({"exec_info": {"queue_remaining": 0}}) is False


def test_comfy_idle_when_payload_missing_exec_info() -> None:
    assert comfy_is_busy({}) is False
    assert comfy_is_busy({"exec_info": {}}) is False
    assert comfy_is_busy({"exec_info": {"queue_remaining": "nope"}}) is False


def test_comfy_vram_ratio_invalid_device() -> None:
    assert comfy_vram_free_ratio({"devices": ["nope"]}) is None
    zero = {"devices": [{"vram_total": 0, "vram_free": 0}]}
    bad = {"devices": [{"vram_total": "x", "vram_free": 1}]}
    assert comfy_vram_free_ratio(zero) is None
    assert comfy_vram_free_ratio(bad) is None


def test_llama_unreachable_without_base_url() -> None:
    backend = Backend(name="qwen38-chat", need_mb=1, role=Role.CHAT)
    assert llama_is_reachable(backend) is False


def test_llama_fetcher_raises() -> None:
    backend = Backend(
        name="qwen38-chat",
        need_mb=1,
        role=Role.CHAT,
        base_url="http://127.0.0.1:5801",
    )

    def boom(_url: str) -> tuple[int, str]:
        raise RuntimeError("network")

    assert llama_is_reachable(backend, fetcher=boom) is False


def test_comfy_vram_free_ratio() -> None:
    payload = {"devices": [{"vram_total": 16303, "vram_free": 15100}]}
    ratio = comfy_vram_free_ratio(payload)
    assert ratio == pytest.approx(15100 / 16303)


def test_comfy_vram_free_ratio_alt_keys() -> None:
    payload = {"system": {"devices": [{"vram_total": 100, "vram_free": 93}]}}
    assert comfy_vram_free_ratio(payload) == 0.93


def test_comfy_vram_free_ratio_missing() -> None:
    assert comfy_vram_free_ratio({}) is None


def test_llama_is_reachable_uses_health_fetcher() -> None:
    backend = Backend(
        name="qwen38-chat",
        need_mb=1,
        role=Role.CHAT,
        base_url="http://127.0.0.1:5801",
    )
    assert llama_is_reachable(backend, fetcher=lambda url: (200, "ok")) is True
    assert llama_is_reachable(backend, fetcher=lambda url: (500, "no")) is False
    down = llama_is_reachable(
        backend, fetcher=lambda url: ConnectionError("down")
    )
    assert down is False


def test_llama_models_have_weights_from_router_status() -> None:
    loaded = {
        "data": [{"id": "qwen38-chat", "status": {"value": "loaded"}}],
    }
    sleeping = {
        "data": [{"id": "qwen38-chat", "status": {"value": "sleeping"}}],
    }
    unloaded = {
        "data": [{"id": "qwen38-chat", "status": {"value": "unloaded"}}],
    }
    loading = {
        "data": [{"id": "qwen38-chat", "status": {"value": "loading"}}],
    }
    openai_only = {"data": [{"id": "qwen38-chat", "object": "model"}]}
    assert llama_models_have_weights(loaded) is True
    assert llama_models_have_weights(loading) is True
    assert llama_models_have_weights(sleeping) is False
    assert llama_models_have_weights(unloaded) is False
    assert llama_models_have_weights(openai_only) is None
    assert llama_models_have_weights({}) is None


def test_llama_props_have_weights_from_sleep_flag() -> None:
    assert llama_props_have_weights({"is_sleeping": False}) is True
    assert llama_props_have_weights({"is_sleeping": True}) is False
    assert llama_props_have_weights({"model_alias": "x"}) is None


def test_llama_weights_loaded_prefers_models_over_health() -> None:
    backend = Backend(
        name="qwen38-chat",
        need_mb=1,
        role=Role.CHAT,
        base_url="http://192.168.1.10:8198",
    )

    def json_get(url: str) -> dict[str, object]:
        if url.endswith("/models"):
            return {
                "data": [{"id": "qwen38-chat", "status": {"value": "unloaded"}}],
            }
        if url.endswith("/props"):
            return {"is_sleeping": False}
        raise AssertionError(url)

    assert llama_weights_loaded(backend, json_get=json_get) is False


def test_llama_weights_loaded_uses_props_when_models_uninformative() -> None:
    backend = Backend(
        name="qwen38-chat",
        need_mb=1,
        role=Role.CHAT,
        base_url="http://192.168.1.10:8198",
    )

    def json_get(url: str) -> dict[str, object]:
        if url.endswith("/models"):
            return {"data": [{"id": "qwen38-chat", "object": "model"}]}
        if url.endswith("/props"):
            return {"is_sleeping": False}
        raise AssertionError(url)

    assert llama_weights_loaded(backend, json_get=json_get) is True


def test_llama_weights_loaded_false_when_probes_fail() -> None:
    backend = Backend(
        name="qwen38-chat",
        need_mb=1,
        role=Role.CHAT,
        base_url="http://192.168.1.10:8198",
    )
    down = llama_weights_loaded(
        backend, json_get=lambda _url: ConnectionError("down")
    )
    assert down is False
