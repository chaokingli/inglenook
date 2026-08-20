from __future__ import annotations

import pytest

from inglenook.probes import comfy_is_busy, comfy_vram_free_ratio, llama_is_reachable
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
