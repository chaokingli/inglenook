from __future__ import annotations

from inglenook.gate import Gate
from inglenook.types import Backend, Policy, VramSnapshot
from tests.conftest import FakeBusy, FakeClock, FakeOccupancy, FakeUnloader, FakeVram


def _gate(
    registry: dict[str, Backend],
    policy: Policy,
    snapshots: list[VramSnapshot],
    loaded: set[str],
    busy: set[str] | None = None,
) -> tuple[Gate, FakeUnloader, FakeClock, FakeOccupancy, FakeBusy]:
    occupancy = FakeOccupancy(loaded)
    unloader = FakeUnloader(occupancy)
    clock = FakeClock()
    busy_state = FakeBusy(busy or set())
    gate = Gate(
        registry=registry,
        policy=policy,
        reader=FakeVram(snapshots),
        unloader=unloader,
        occupancy=occupancy,
        busy_checker=busy_state,
        clock=clock,
    )
    return gate, unloader, clock, occupancy, busy_state


def test_ensure_free_admits_immediately_when_idle(
    registry: dict[str, Backend],
    policy: Policy,
    idle_vram: VramSnapshot,
) -> None:
    gate, unloader, _, _, _ = _gate(registry, policy, [idle_vram], loaded=set())
    result = gate.ensure_free("qwen38-chat")
    assert result.admitted is True
    assert result.status == "admitted"
    assert result.unloaded == ()
    assert unloader.calls == []


def test_ensure_free_unloads_chat_then_admits_when_vram_drops(
    registry: dict[str, Backend],
    policy: Policy,
    tight_vram: VramSnapshot,
    idle_vram: VramSnapshot,
) -> None:
    gate, unloader, clock, occupancy, _ = _gate(
        registry,
        policy,
        [tight_vram, idle_vram],
        loaded={"qwen38-chat"},
    )
    result = gate.ensure_free("ls_comfyui")
    assert result.admitted is True
    assert result.unloaded == ("qwen38-chat",)
    assert unloader.calls == ["qwen38-chat"]
    assert "qwen38-chat" not in occupancy.loaded()
    assert clock.sleeps == [policy.poll_interval_ms]


def test_ensure_free_waits_while_comfy_busy_then_unloads(
    registry: dict[str, Backend],
    policy: Policy,
    tight_vram: VramSnapshot,
    idle_vram: VramSnapshot,
) -> None:
    occupancy = FakeOccupancy({"ls_comfyui"})
    unloader = FakeUnloader(occupancy)
    clock = FakeClock()
    busy = FakeBusy({"ls_comfyui"})
    snapshots = [tight_vram, tight_vram, idle_vram]
    reader = FakeVram(snapshots)

    original_sleep = clock.sleep_ms

    def sleep_and_finish(ms: int) -> None:
        original_sleep(ms)
        busy.clear("ls_comfyui")

    clock.sleep_ms = sleep_and_finish  # type: ignore[method-assign]

    gate = Gate(
        registry=registry,
        policy=policy,
        reader=reader,
        unloader=unloader,
        occupancy=occupancy,
        busy_checker=busy,
        clock=clock,
    )
    result = gate.ensure_free("qwen38-chat")
    assert result.admitted is True
    assert result.unloaded == ("ls_comfyui",)
    assert result.waited_ms > 0
    assert busy.busy_names == set()


def test_ensure_free_times_out_when_comfy_never_idles(
    registry: dict[str, Backend],
    tight_vram: VramSnapshot,
) -> None:
    policy = Policy(unload_timeout_s=1, poll_interval_ms=500)
    gate, unloader, _, _, _ = _gate(
        registry,
        policy,
        [tight_vram],
        loaded={"ls_comfyui"},
        busy={"ls_comfyui"},
    )
    result = gate.ensure_free("qwen38-chat")
    assert result.admitted is False
    assert result.status == "rejected"
    assert result.reason == "comfy_busy_timeout"
    assert unloader.calls == []


def test_ensure_free_times_out_when_vram_never_drops(
    registry: dict[str, Backend],
    tight_vram: VramSnapshot,
) -> None:
    policy = Policy(unload_timeout_s=1, poll_interval_ms=400)
    gate, unloader, clock, _, _ = _gate(
        registry,
        policy,
        [tight_vram],
        loaded={"qwen38-chat"},
    )
    result = gate.ensure_free("ls_comfyui")
    assert result.admitted is False
    assert "timeout" in result.reason
    assert "qwen38-chat" in result.unloaded
    assert clock.sleeps


def test_unknown_backend_is_rejected(
    registry: dict[str, Backend],
    policy: Policy,
    idle_vram: VramSnapshot,
) -> None:
    gate, _, _, _, _ = _gate(registry, policy, [idle_vram], loaded=set())
    result = gate.ensure_free("nope")
    assert result.admitted is False
    assert result.reason == "unknown_backend"
