from __future__ import annotations

from inglenook.occupancy import HealthOccupancy, ProbeBusyChecker
from inglenook.types import Backend, OccupancyKind, VramSnapshot


def test_health_occupancy_detects_reachable_llama(
    chat: Backend, comfy: Backend, idle_vram: VramSnapshot
) -> None:
    occupancy = HealthOccupancy(
        registry={chat.name: chat, comfy.name: comfy},
        reader=lambda: idle_vram,
        idle_used_mb=2500,
        fetcher=lambda url: (200, "ok") if ":5801" in url else (500, "no"),
    )
    assert occupancy.loaded() == frozenset({chat.name})


def test_health_occupancy_assumes_comfy_when_vram_high_and_llama_down(
    chat: Backend, comfy: Backend, tight_vram: VramSnapshot
) -> None:
    occupancy = HealthOccupancy(
        registry={chat.name: chat, comfy.name: comfy},
        reader=lambda: tight_vram,
        idle_used_mb=2500,
        fetcher=lambda url: ConnectionError("down"),
    )
    assert occupancy.loaded() == frozenset({comfy.name})


def test_health_occupancy_idle_with_nothing_up(
    chat: Backend, comfy: Backend, idle_vram: VramSnapshot
) -> None:
    occupancy = HealthOccupancy(
        registry={chat.name: chat, comfy.name: comfy},
        reader=lambda: idle_vram,
        idle_used_mb=2500,
        fetcher=lambda url: ConnectionError("down"),
    )
    assert occupancy.loaded() == frozenset()


def test_weights_occupancy_ignores_health_when_models_unloaded(
    chat: Backend, comfy: Backend, tight_vram: VramSnapshot
) -> None:
    def json_get(url: str) -> dict[str, object]:
        if url.endswith("/models"):
            return {"data": [{"id": chat.name, "status": {"value": "unloaded"}}]}
        raise ConnectionError(url)

    occupancy = HealthOccupancy(
        registry={chat.name: chat, comfy.name: comfy},
        reader=lambda: tight_vram,
        idle_used_mb=2500,
        occupancy=OccupancyKind.WEIGHTS,
        json_get=json_get,
        fetcher=lambda _url: (200, '{"status":"ok"}'),
    )
    assert occupancy.loaded() == frozenset({comfy.name})


def test_weights_occupancy_detects_router_loaded_weights(
    chat: Backend, comfy: Backend, idle_vram: VramSnapshot
) -> None:
    def json_get(url: str) -> dict[str, object]:
        if url.endswith("/models"):
            return {"data": [{"id": chat.name, "status": {"value": "loaded"}}]}
        raise ConnectionError(url)

    occupancy = HealthOccupancy(
        registry={chat.name: chat, comfy.name: comfy},
        reader=lambda: idle_vram,
        idle_used_mb=2500,
        occupancy=OccupancyKind.WEIGHTS,
        json_get=json_get,
        fetcher=lambda _url: (503, "Loading model"),
    )
    assert occupancy.loaded() == frozenset({chat.name})


def test_weights_occupancy_sleeping_and_idle_vram_is_empty(
    chat: Backend, comfy: Backend, idle_vram: VramSnapshot
) -> None:
    def json_get(url: str) -> dict[str, object]:
        if url.endswith("/models"):
            return {"object": "list", "data": [{"id": "x", "object": "model"}]}
        if url.endswith("/props"):
            return {"is_sleeping": True}
        raise ConnectionError(url)

    occupancy = HealthOccupancy(
        registry={chat.name: chat, comfy.name: comfy},
        reader=lambda: idle_vram,
        idle_used_mb=2500,
        occupancy=OccupancyKind.WEIGHTS,
        json_get=json_get,
    )
    assert occupancy.loaded() == frozenset()


def test_probe_busy_checker_none_is_never_busy(chat: Backend) -> None:
    assert ProbeBusyChecker().is_busy(chat) is False


def test_probe_busy_checker_comfy_queue(monkeypatch, comfy: Backend) -> None:
    monkeypatch.setattr(
        "inglenook.occupancy.fetch_json",
        lambda url: {"exec_info": {"queue_remaining": 1}},
    )
    assert ProbeBusyChecker().is_busy(comfy) is True
    monkeypatch.setattr(
        "inglenook.occupancy.fetch_json",
        lambda url: (_ for _ in ()).throw(ConnectionError("down")),
    )
    assert ProbeBusyChecker().is_busy(comfy) is True
