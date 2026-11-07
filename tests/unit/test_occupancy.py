from __future__ import annotations

from inglenook.occupancy import HealthOccupancy, ProbeBusyChecker
from inglenook.types import Backend, OccupancyKind, Role, VramSnapshot


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


def test_weights_occupancy_maps_voice_preset_not_catch_all(
    chat: Backend, voice: Backend, comfy: Backend, idle_vram: VramSnapshot
) -> None:
    catch = Backend(
        name=chat.name,
        need_mb=chat.need_mb,
        headroom_mb=chat.headroom_mb,
        role=chat.role,
        group=chat.group,
        unload_kind=chat.unload_kind,
        base_url=chat.base_url,
        priority=chat.priority,
        catch_all=True,
    )

    def json_get(url: str) -> dict[str, object]:
        if url.endswith("/models"):
            return {"data": [{"id": "qwen35-voice", "status": {"value": "loaded"}}]}
        raise ConnectionError(url)

    occupancy = HealthOccupancy(
        registry={catch.name: catch, voice.name: voice, comfy.name: comfy},
        reader=lambda: idle_vram,
        idle_used_mb=2500,
        occupancy=OccupancyKind.WEIGHTS,
        json_get=json_get,
        fetcher=lambda _url: ConnectionError("down"),
    )
    assert occupancy.loaded() == frozenset({voice.name})


def test_weights_occupancy_unknown_id_uses_catch_all_chat(
    chat: Backend, voice: Backend, comfy: Backend, idle_vram: VramSnapshot
) -> None:
    catch = Backend(
        name=chat.name,
        need_mb=chat.need_mb,
        headroom_mb=chat.headroom_mb,
        role=chat.role,
        group=chat.group,
        unload_kind=chat.unload_kind,
        base_url=chat.base_url,
        priority=chat.priority,
        catch_all=True,
    )

    def json_get(url: str) -> dict[str, object]:
        if url.endswith("/models"):
            return {"data": [{"id": "qwen35-code", "status": {"value": "loaded"}}]}
        raise ConnectionError(url)

    occupancy = HealthOccupancy(
        registry={catch.name: catch, voice.name: voice, comfy.name: comfy},
        reader=lambda: idle_vram,
        idle_used_mb=2500,
        occupancy=OccupancyKind.WEIGHTS,
        json_get=json_get,
        fetcher=lambda _url: ConnectionError("down"),
    )
    assert occupancy.loaded() == frozenset({catch.name})


def test_health_occupancy_detects_tts_health(
    chat: Backend, comfy: Backend, tts: Backend, idle_vram: VramSnapshot
) -> None:
    tts_up = Backend(
        name=tts.name,
        need_mb=tts.need_mb,
        headroom_mb=tts.headroom_mb,
        role=tts.role,
        group=tts.group,
        unload_kind=tts.unload_kind,
        unload_command=tts.unload_command,
        base_url="http://127.0.0.1:8210",
        priority=tts.priority,
    )
    occupancy = HealthOccupancy(
        registry={chat.name: chat, comfy.name: comfy, tts_up.name: tts_up},
        reader=lambda: idle_vram,
        idle_used_mb=2500,
        occupancy=OccupancyKind.WEIGHTS,
        json_get=lambda _url: {"data": [{"id": chat.name, "status": {"value": "unloaded"}}]},
        fetcher=lambda url: (200, "ok") if ":8210" in url else ConnectionError("down"),
    )
    assert occupancy.loaded() == frozenset({tts_up.name})


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
    assert ProbeBusyChecker().is_busy(comfy) is False


def test_weights_occupancy_shared_router_only_marks_loaded_id(
    comfy: Backend, idle_vram: VramSnapshot
) -> None:
    chat = Backend(
        name="qwen38-chat",
        need_mb=1,
        role=Role.CHAT,
        unload_kind="llama-unload",
        base_url="http://127.0.0.1:8198",
    )
    sibling = Backend(
        name="qwen35-code",
        need_mb=1,
        role=Role.CHAT,
        unload_kind="llama-unload",
        base_url="http://127.0.0.1:8198",
    )

    def json_get(url: str) -> dict[str, object]:
        if url.endswith("/models"):
            return {
                "data": [
                    {"id": "qwen38-chat", "status": {"value": "unloaded"}},
                    {"id": "qwen35-code", "status": {"value": "loaded"}},
                ]
            }
        raise ConnectionError(url)

    occupancy = HealthOccupancy(
        registry={chat.name: chat, sibling.name: sibling, comfy.name: comfy},
        reader=lambda: idle_vram,
        idle_used_mb=2500,
        occupancy=OccupancyKind.WEIGHTS,
        json_get=json_get,
        fetcher=lambda _url: (200, "ok"),
    )
    assert occupancy.loaded() == frozenset({sibling.name})


def test_weights_occupancy_unknown_loaded_id_uses_chat_slot(
    chat: Backend, comfy: Backend, idle_vram: VramSnapshot
) -> None:
    def json_get(url: str) -> dict[str, object]:
        if url.endswith("/models"):
            return {"data": [{"id": "qwen35-code", "status": {"value": "loaded"}}]}
        raise ConnectionError(url)

    occupancy = HealthOccupancy(
        registry={chat.name: chat, comfy.name: comfy},
        reader=lambda: idle_vram,
        idle_used_mb=2500,
        occupancy=OccupancyKind.WEIGHTS,
        json_get=json_get,
        fetcher=lambda _url: (200, "ok"),
    )
    assert occupancy.loaded() == frozenset({chat.name})
