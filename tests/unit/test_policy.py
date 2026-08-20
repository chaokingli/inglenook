from __future__ import annotations

from inglenook.policy import plan_ensure
from inglenook.types import Backend, DecisionKind, Policy, Role, VramSnapshot


def test_admits_when_free_and_no_exclusive_conflict(
    registry: dict[str, Backend],
    idle_vram: VramSnapshot,
    policy: Policy,
) -> None:
    plan = plan_ensure(
        "qwen38-chat",
        registry,
        idle_vram,
        loaded=frozenset(),
        busy=frozenset(),
        policy=policy,
    )
    assert plan.kind is DecisionKind.ADMIT
    assert plan.unload == ()


def test_idempotent_admit_when_requester_already_loaded(
    registry: dict[str, Backend],
    idle_vram: VramSnapshot,
    policy: Policy,
) -> None:
    plan = plan_ensure(
        "qwen38-chat",
        registry,
        idle_vram,
        loaded=frozenset({"qwen38-chat"}),
        busy=frozenset(),
        policy=policy,
    )
    assert plan.kind is DecisionKind.ADMIT
    assert plan.unload == ()


def test_chat_admits_when_already_resident_even_if_free_is_low(
    registry: dict[str, Backend],
    tight_vram: VramSnapshot,
    policy: Policy,
) -> None:
    plan = plan_ensure(
        "qwen38-chat",
        registry,
        tight_vram,
        loaded=frozenset({"qwen38-chat"}),
        busy=frozenset(),
        policy=policy,
    )
    assert plan.kind is DecisionKind.ADMIT


def test_comfy_does_not_admit_on_stale_loaded_flag_when_vram_is_tight(
    registry: dict[str, Backend],
    tight_vram: VramSnapshot,
    policy: Policy,
) -> None:
    plan = plan_ensure(
        "ls_comfyui",
        registry,
        tight_vram,
        loaded=frozenset({"ls_comfyui"}),
        busy=frozenset(),
        policy=policy,
    )
    assert plan.kind is DecisionKind.REJECT
    assert plan.reason == "insufficient_vram"


def test_chat_queues_when_comfy_is_busy(
    registry: dict[str, Backend],
    tight_vram: VramSnapshot,
    policy: Policy,
) -> None:
    plan = plan_ensure(
        "qwen38-chat",
        registry,
        tight_vram,
        loaded=frozenset({"ls_comfyui"}),
        busy=frozenset({"ls_comfyui"}),
        policy=policy,
    )
    assert plan.kind is DecisionKind.QUEUE
    assert plan.reason == "comfy_busy"
    assert plan.unload == ()
    assert plan.retry_ms == policy.poll_interval_ms


def test_chat_unloads_idle_comfy_weights(
    registry: dict[str, Backend],
    tight_vram: VramSnapshot,
    policy: Policy,
) -> None:
    plan = plan_ensure(
        "qwen38-chat",
        registry,
        tight_vram,
        loaded=frozenset({"ls_comfyui"}),
        busy=frozenset(),
        policy=policy,
    )
    assert plan.kind is DecisionKind.UNLOAD
    assert plan.unload == ("ls_comfyui",)


def test_generation_waits_for_in_flight_chat(
    registry: dict[str, Backend],
    tight_vram: VramSnapshot,
    policy: Policy,
) -> None:
    plan = plan_ensure(
        "ls_comfyui",
        registry,
        tight_vram,
        loaded=frozenset({"qwen38-chat"}),
        busy=frozenset({"qwen38-chat"}),
        policy=policy,
    )
    assert plan.kind is DecisionKind.QUEUE
    assert plan.reason == "wait_chat_inflight"
    assert plan.unload == ()


def test_generation_preempts_idle_chat(
    registry: dict[str, Backend],
    tight_vram: VramSnapshot,
    policy: Policy,
) -> None:
    plan = plan_ensure(
        "ls_comfyui",
        registry,
        tight_vram,
        loaded=frozenset({"qwen38-chat"}),
        busy=frozenset(),
        policy=policy,
    )
    assert plan.kind is DecisionKind.UNLOAD
    assert plan.unload == ("qwen38-chat",)


def test_generation_can_kill_in_flight_chat_when_configured(
    registry: dict[str, Backend],
    tight_vram: VramSnapshot,
) -> None:
    policy = Policy(generation_waits_for_chat_inflight=False)
    plan = plan_ensure(
        "ls_comfyui",
        registry,
        tight_vram,
        loaded=frozenset({"qwen38-chat"}),
        busy=frozenset({"qwen38-chat"}),
        policy=policy,
    )
    assert plan.kind is DecisionKind.UNLOAD
    assert plan.unload == ("qwen38-chat",)


def test_unload_order_is_tts_then_chat_then_comfy(
    registry: dict[str, Backend],
    tight_vram: VramSnapshot,
    policy: Policy,
) -> None:
    plan = plan_ensure(
        "ls_comfyui",
        registry,
        tight_vram,
        loaded=frozenset({"tts-heavy", "qwen38-chat"}),
        busy=frozenset(),
        policy=policy,
    )
    assert plan.kind is DecisionKind.UNLOAD
    assert plan.unload == ("tts-heavy", "qwen38-chat")


def test_cpu_group_is_not_unloaded_for_gpu_request(
    registry: dict[str, Backend],
    idle_vram: VramSnapshot,
    policy: Policy,
) -> None:
    plan = plan_ensure(
        "qwen38-chat",
        registry,
        idle_vram,
        loaded=frozenset({"whisper-cpu"}),
        busy=frozenset(),
        policy=policy,
    )
    assert plan.kind is DecisionKind.ADMIT
    assert plan.unload == ()


def test_exclusive_conflict_unloads_even_if_bytes_look_free(
    registry: dict[str, Backend],
    idle_vram: VramSnapshot,
    policy: Policy,
) -> None:
    plan = plan_ensure(
        "ls_comfyui",
        registry,
        idle_vram,
        loaded=frozenset({"qwen38-chat"}),
        busy=frozenset(),
        policy=policy,
    )
    assert plan.kind is DecisionKind.UNLOAD
    assert plan.unload == ("qwen38-chat",)


def test_rejects_unknown_backend(
    registry: dict[str, Backend],
    idle_vram: VramSnapshot,
    policy: Policy,
) -> None:
    plan = plan_ensure(
        "missing",
        registry,
        idle_vram,
        loaded=frozenset(),
        busy=frozenset(),
        policy=policy,
    )
    assert plan.kind is DecisionKind.REJECT
    assert plan.reason == "unknown_backend"


def test_rejects_when_vram_short_and_nothing_to_unload(
    registry: dict[str, Backend],
    tight_vram: VramSnapshot,
    policy: Policy,
) -> None:
    plan = plan_ensure(
        "qwen38-chat",
        registry,
        tight_vram,
        loaded=frozenset(),
        busy=frozenset(),
        policy=policy,
    )
    assert plan.kind is DecisionKind.REJECT
    assert plan.reason == "insufficient_vram"
    assert "unknown occupancy" in plan.warning.lower()


def test_warns_about_unknown_occupancy_above_threshold(
    registry: dict[str, Backend],
    policy: Policy,
) -> None:
    snap = VramSnapshot(total_mb=16303, used_mb=6000, free_mb=10000)
    plan = plan_ensure(
        "tts-heavy",
        registry,
        snap,
        loaded=frozenset(),
        busy=frozenset(),
        policy=policy,
    )
    assert plan.kind is DecisionKind.ADMIT
    assert "unknown occupancy" in plan.warning.lower()


def test_never_unloads_busy_comfy_for_another_gpu_job(
    registry: dict[str, Backend],
    tight_vram: VramSnapshot,
    policy: Policy,
) -> None:
    extra = Backend(
        name="comfy-other",
        need_mb=15000,
        role=Role.COMFY,
        group="gpu-exclusive",
        busy_probe="comfy-queue",
        priority=80,
    )
    registry = {**registry, extra.name: extra}
    plan = plan_ensure(
        "comfy-other",
        registry,
        tight_vram,
        loaded=frozenset({"ls_comfyui"}),
        busy=frozenset({"ls_comfyui"}),
        policy=policy,
    )
    assert plan.kind is DecisionKind.QUEUE
    assert plan.reason == "comfy_busy"


def test_does_not_preempt_chat_when_disabled(
    registry: dict[str, Backend],
    tight_vram: VramSnapshot,
) -> None:
    policy = Policy(generation_preempts_idle_chat=False)
    plan = plan_ensure(
        "ls_comfyui",
        registry,
        tight_vram,
        loaded=frozenset({"qwen38-chat"}),
        busy=frozenset(),
        policy=policy,
    )
    assert plan.kind is DecisionKind.REJECT
    assert plan.reason == "insufficient_vram"


def test_ignores_unregistered_loaded_names(
    registry: dict[str, Backend],
    idle_vram: VramSnapshot,
    policy: Policy,
) -> None:
    plan = plan_ensure(
        "qwen38-chat",
        registry,
        idle_vram,
        loaded=frozenset({"ghost"}),
        busy=frozenset(),
        policy=policy,
    )
    assert plan.kind is DecisionKind.ADMIT


def test_chat_does_not_queue_when_policy_disables_wait(
    registry: dict[str, Backend],
    tight_vram: VramSnapshot,
) -> None:
    policy = Policy(chat_waits_for_comfy=False)
    plan = plan_ensure(
        "qwen38-chat",
        registry,
        tight_vram,
        loaded=frozenset({"ls_comfyui"}),
        busy=frozenset({"ls_comfyui"}),
        policy=policy,
    )
    assert plan.kind is DecisionKind.REJECT
    assert plan.reason == "comfy_busy_no_wait"
