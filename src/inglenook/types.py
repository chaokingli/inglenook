from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

_BACKEND_NAME = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

UNLOAD_KINDS = frozenset({"none", "llama-unload", "comfy-free", "command"})
BUSY_PROBES = frozenset({"none", "comfy-queue", "llama-health"})
OCCUPANCY_KINDS = frozenset({"health", "weights"})


class Role(StrEnum):
    CHAT = "chat"
    COMFY = "comfy"
    TTS = "tts"
    STT = "stt"
    UNKNOWN = "unknown"


class OccupancyKind(StrEnum):
    HEALTH = "health"
    WEIGHTS = "weights"


class DecisionKind(StrEnum):
    ADMIT = "admit"
    UNLOAD = "unload"
    QUEUE = "queue"
    REJECT = "reject"


def parse_backend_name(raw: str) -> str:
    if not isinstance(raw, str) or not _BACKEND_NAME.fullmatch(raw):
        raise ValueError("backend name must match [A-Za-z0-9._-]{1,64}")
    return raw


@dataclass(frozen=True)
class ProcessUse:
    pid: int
    name: str
    used_mb: int


@dataclass(frozen=True)
class VramSnapshot:
    total_mb: int
    used_mb: int
    free_mb: int
    processes: tuple[ProcessUse, ...] = ()

    def __post_init__(self) -> None:
        if self.total_mb < 0 or self.used_mb < 0 or self.free_mb < 0:
            raise ValueError("VRAM figures cannot be negative")


@dataclass(frozen=True)
class Backend:
    name: str
    need_mb: int
    headroom_mb: int = 800
    role: Role = Role.UNKNOWN
    group: str | None = "gpu-exclusive"
    persistent: bool = False
    unload_kind: str = "none"
    unload_command: tuple[str, ...] = ()
    busy_probe: str = "none"
    base_url: str = ""
    priority: int = 50

    def __post_init__(self) -> None:
        parse_backend_name(self.name)
        if self.need_mb < 0 or self.headroom_mb < 0:
            raise ValueError("need_mb and headroom_mb must be >= 0")
        if self.unload_kind not in UNLOAD_KINDS:
            raise ValueError(f"unsupported unload_kind: {self.unload_kind}")
        if self.busy_probe not in BUSY_PROBES:
            raise ValueError(f"unsupported busy_probe: {self.busy_probe}")

    @property
    def required_free_mb(self) -> int:
        return self.need_mb + self.headroom_mb


@dataclass(frozen=True)
class Policy:
    exclusive_group: str = "gpu-exclusive"
    idle_used_mb: int = 2500
    unknown_used_warn_mb: int = 4096
    unload_timeout_s: int = 180
    poll_interval_ms: int = 500
    chat_waits_for_comfy: bool = True
    generation_waits_for_chat_inflight: bool = True
    generation_preempts_idle_chat: bool = True
    stop_unknown: bool = False
    occupancy: OccupancyKind = OccupancyKind.HEALTH


@dataclass(frozen=True)
class Plan:
    kind: DecisionKind
    unload: tuple[str, ...] = ()
    reason: str = ""
    retry_ms: int = 0
    warning: str = ""


@dataclass(frozen=True)
class EnsureResult:
    admitted: bool
    status: str
    unloaded: tuple[str, ...]
    waited_ms: int
    used_mb: int
    free_mb: int
    reason: str = ""
    warning: str = ""
