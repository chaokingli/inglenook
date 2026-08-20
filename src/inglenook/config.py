from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from inglenook.errors import ConfigError
from inglenook.types import (
    BUSY_PROBES,
    UNLOAD_KINDS,
    Backend,
    Policy,
    Role,
    parse_backend_name,
)


class GateConfig:
    def __init__(self, policy: Policy, registry: dict[str, Backend]) -> None:
        self.policy = policy
        self.registry = registry


def load_config(path: Path) -> GateConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("config root must be a mapping")

    policy = _parse_policy(raw.get("gpu"), raw.get("policy"))
    backends_raw = raw.get("backends")
    if not isinstance(backends_raw, dict) or not backends_raw:
        raise ConfigError("config must define a backends mapping")

    registry: dict[str, Backend] = {}
    for name, body in backends_raw.items():
        try:
            backend_name = parse_backend_name(str(name))
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
        if not isinstance(body, dict):
            raise ConfigError(f"backend {backend_name} must be a mapping")
        registry[backend_name] = _parse_backend(backend_name, body)
    return GateConfig(policy=policy, registry=registry)


def _parse_policy(gpu_raw: Any, policy_raw: Any) -> Policy:
    gpu = gpu_raw if isinstance(gpu_raw, dict) else {}
    policy = policy_raw if isinstance(policy_raw, dict) else {}
    return Policy(
        exclusive_group=str(policy.get("exclusive_group", "gpu-exclusive")),
        idle_used_mb=_int(
            policy.get("idle_used_mb", gpu.get("idle_used_mb", 2500)),
            "idle_used_mb",
        ),
        unknown_used_warn_mb=_int(
            policy.get("unknown_used_warn_mb", gpu.get("unknown_used_warn_mb", 4096)),
            "unknown_used_warn_mb",
        ),
        unload_timeout_s=_int(policy.get("unload_timeout_s", 180), "unload_timeout_s"),
        poll_interval_ms=_int(policy.get("poll_interval_ms", 500), "poll_interval_ms"),
        chat_waits_for_comfy=bool(policy.get("chat_waits_for_comfy", True)),
        generation_waits_for_chat_inflight=bool(
            policy.get("generation_waits_for_chat_inflight", True)
        ),
        generation_preempts_idle_chat=bool(
            policy.get("generation_preempts_idle_chat", True)
        ),
        stop_unknown=bool(policy.get("stop_unknown", False)),
    )


def _parse_backend(name: str, body: dict[str, Any]) -> Backend:
    need_mb = _int(body.get("need_mb", 0), "need_mb")
    if need_mb < 0:
        raise ConfigError("need_mb must be >= 0")
    unload_kind = str(body.get("unload_kind", "none"))
    if unload_kind not in UNLOAD_KINDS:
        raise ConfigError(f"unsupported unload_kind: {unload_kind}")
    busy_probe = str(body.get("busy_probe", "none"))
    if busy_probe not in BUSY_PROBES:
        raise ConfigError(f"unsupported busy_probe: {busy_probe}")
    role_raw = str(body.get("role", "unknown"))
    try:
        role = Role(role_raw)
    except ValueError as exc:
        raise ConfigError(f"unsupported role: {role_raw}") from exc
    base_url = str(body.get("base_url", ""))
    if base_url:
        _validate_local_url(base_url)
    command = body.get("unload_command")
    if not command:
        unload_command: tuple[str, ...] = ()
    elif isinstance(command, (list, tuple)) and all(
        isinstance(item, str) for item in command
    ):
        unload_command = tuple(command)
    else:
        raise ConfigError("unload_command must be a list of strings")
    return Backend(
        name=name,
        need_mb=need_mb,
        headroom_mb=_int(body.get("headroom_mb", 800), "headroom_mb"),
        role=role,
        group=str(body.get("group", "gpu-exclusive")),
        persistent=bool(body.get("persistent", False)),
        unload_kind=unload_kind,
        unload_command=unload_command,
        busy_probe=busy_probe,
        base_url=base_url,
        priority=_int(body.get("priority", 50), "priority"),
    )


def _validate_local_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ConfigError(f"base_url must be http(s): {url}")
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ConfigError("base_url must point at localhost")


def _int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{field} must be an integer") from exc
