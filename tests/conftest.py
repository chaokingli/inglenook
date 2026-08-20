from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from inglenook.types import Backend, Policy, Role, VramSnapshot


@pytest.fixture
def policy() -> Policy:
    return Policy()


@pytest.fixture
def chat() -> Backend:
    return Backend(
        name="qwen38-chat",
        need_mb=14600,
        headroom_mb=800,
        role=Role.CHAT,
        group="gpu-exclusive",
        unload_kind="llama-unload",
        base_url="http://127.0.0.1:5801",
        priority=50,
    )


@pytest.fixture
def comfy() -> Backend:
    return Backend(
        name="ls_comfyui",
        need_mb=15000,
        headroom_mb=800,
        role=Role.COMFY,
        group="gpu-exclusive",
        persistent=True,
        unload_kind="comfy-free",
        busy_probe="comfy-queue",
        base_url="http://127.0.0.1:8188",
        priority=80,
    )


@pytest.fixture
def tts() -> Backend:
    return Backend(
        name="tts-heavy",
        need_mb=4000,
        headroom_mb=500,
        role=Role.TTS,
        group="gpu-exclusive",
        unload_kind="command",
        unload_command=("true",),
        priority=10,
    )


@pytest.fixture
def whisper() -> Backend:
    return Backend(
        name="whisper-cpu",
        need_mb=0,
        headroom_mb=0,
        role=Role.STT,
        group="always-cpu",
        persistent=True,
        unload_kind="none",
        priority=0,
    )


@pytest.fixture
def registry(
    chat: Backend, comfy: Backend, tts: Backend, whisper: Backend
) -> dict[str, Backend]:
    return {
        chat.name: chat,
        comfy.name: comfy,
        tts.name: tts,
        whisper.name: whisper,
    }


@pytest.fixture
def tight_vram() -> VramSnapshot:
    return VramSnapshot(total_mb=16303, used_mb=14648, free_mb=1234)


@pytest.fixture
def idle_vram() -> VramSnapshot:
    return VramSnapshot(total_mb=16303, used_mb=400, free_mb=15903)


@dataclass
class FakeClock:
    now_ms: int = 0
    sleeps: list[int] = field(default_factory=list)

    def monotonic_ms(self) -> int:
        return self.now_ms

    def sleep_ms(self, ms: int) -> None:
        self.sleeps.append(ms)
        self.now_ms += ms


@dataclass
class FakeVram:
    snapshots: list[VramSnapshot]
    index: int = 0

    def read(self) -> VramSnapshot:
        if not self.snapshots:
            raise RuntimeError("no snapshots")
        if self.index >= len(self.snapshots):
            return self.snapshots[-1]
        snap = self.snapshots[self.index]
        self.index += 1
        return snap


@dataclass
class FakeOccupancy:
    loaded_names: set[str]

    def loaded(self) -> frozenset[str]:
        return frozenset(self.loaded_names)

    def drop(self, name: str) -> None:
        self.loaded_names.discard(name)


@dataclass
class FakeBusy:
    busy_names: set[str]

    def is_busy(self, backend: Backend) -> bool:
        return backend.name in self.busy_names

    def clear(self, name: str) -> None:
        self.busy_names.discard(name)


@dataclass
class FakeUnloader:
    occupancy: FakeOccupancy
    calls: list[str] = field(default_factory=list)

    def unload(self, backend: Backend) -> None:
        self.calls.append(backend.name)
        self.occupancy.drop(backend.name)
