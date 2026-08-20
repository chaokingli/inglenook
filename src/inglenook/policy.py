from __future__ import annotations

from collections.abc import Mapping

from inglenook.types import (
    Backend,
    DecisionKind,
    Plan,
    Policy,
    Role,
    VramSnapshot,
)


def plan_ensure(
    backend_name: str,
    registry: Mapping[str, Backend],
    snapshot: VramSnapshot,
    loaded: frozenset[str],
    busy: frozenset[str],
    policy: Policy,
) -> Plan:
    requester = registry.get(backend_name)
    if requester is None:
        return Plan(kind=DecisionKind.REJECT, reason="unknown_backend")

    warning = _unknown_warning(registry, snapshot, loaded, policy)
    others = _exclusive_others(requester, registry, loaded, policy)

    busy_comfy = [b for b in others if b.role is Role.COMFY and b.name in busy]
    busy_chat = [b for b in others if b.role is Role.CHAT and b.name in busy]

    if busy_comfy and requester.role in {Role.CHAT, Role.COMFY, Role.TTS}:
        if requester.role is Role.CHAT and not policy.chat_waits_for_comfy:
            return Plan(
                kind=DecisionKind.REJECT,
                reason="comfy_busy_no_wait",
                warning=warning,
            )
        return Plan(
            kind=DecisionKind.QUEUE,
            reason="comfy_busy",
            retry_ms=policy.poll_interval_ms,
            warning=warning,
        )

    if (
        requester.role is Role.COMFY
        and busy_chat
        and policy.generation_waits_for_chat_inflight
    ):
        return Plan(
            kind=DecisionKind.QUEUE,
            reason="wait_chat_inflight",
            retry_ms=policy.poll_interval_ms,
            warning=warning,
        )

    unloadable = [b for b in others if not (b.role is Role.COMFY and b.name in busy)]
    if requester.role is Role.COMFY and not policy.generation_preempts_idle_chat:
        unloadable = [b for b in unloadable if b.role is not Role.CHAT]

    unloadable.sort(key=lambda backend: (backend.priority, backend.name))
    if unloadable:
        return Plan(
            kind=DecisionKind.UNLOAD,
            unload=tuple(backend.name for backend in unloadable),
            reason="exclusive_swap",
            warning=warning,
        )

    if snapshot.free_mb >= requester.required_free_mb:
        return Plan(kind=DecisionKind.ADMIT, warning=warning)
    if requester.name in loaded and requester.role is Role.CHAT:
        return Plan(kind=DecisionKind.ADMIT, warning=warning)

    return Plan(
        kind=DecisionKind.REJECT,
        reason="insufficient_vram",
        warning=warning,
    )


def _exclusive_others(
    requester: Backend,
    registry: Mapping[str, Backend],
    loaded: frozenset[str],
    policy: Policy,
) -> list[Backend]:
    if requester.group != policy.exclusive_group:
        return []
    others: list[Backend] = []
    for name in loaded:
        if name == requester.name:
            continue
        backend = registry.get(name)
        if backend is None:
            continue
        if backend.group != policy.exclusive_group:
            continue
        others.append(backend)
    return others


def _unknown_warning(
    registry: Mapping[str, Backend],
    snapshot: VramSnapshot,
    loaded: frozenset[str],
    policy: Policy,
) -> str:
    if snapshot.used_mb < policy.unknown_used_warn_mb:
        return ""
    exclusive_loaded = any(
        (backend := registry.get(name)) is not None
        and backend.group == policy.exclusive_group
        for name in loaded
    )
    if exclusive_loaded:
        return ""
    return f"unknown occupancy {snapshot.used_mb} MiB"
