from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import replace

from inglenook.errors import VramError
from inglenook.types import ProcessUse, VramSnapshot

NVIDIA_SMI = "/usr/bin/nvidia-smi"
MEMORY_QUERY: tuple[str, ...] = (
    NVIDIA_SMI,
    "--query-gpu=memory.total,memory.used,memory.free",
    "--format=csv,noheader,nounits",
)
PROCESS_QUERY: tuple[str, ...] = (
    NVIDIA_SMI,
    "--query-compute-apps=pid,process_name,used_gpu_memory",
    "--format=csv,noheader,nounits",
)

SmiRunner = Callable[[list[str]], str]
_SMI_BAD_PAYLOAD = "nvidia-smi memory query returned an unexpected payload"


def parse_smi_memory(raw: str) -> VramSnapshot:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        raise ValueError(_SMI_BAD_PAYLOAD)
    parts = [part.strip() for part in lines[0].split(",")]
    if len(parts) < 3:
        raise ValueError(_SMI_BAD_PAYLOAD)
    try:
        total_mb = int(float(parts[0]))
        used_mb = int(float(parts[1]))
        free_mb = int(float(parts[2]))
    except ValueError as exc:
        raise ValueError(_SMI_BAD_PAYLOAD) from exc
    return VramSnapshot(total_mb=total_mb, used_mb=used_mb, free_mb=free_mb)


def parse_smi_processes(raw: str) -> tuple[ProcessUse, ...]:
    processes: list[ProcessUse] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = [part.strip() for part in stripped.split(",")]
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            used_mb = int(float(parts[-1]))
        except ValueError:
            continue
        name = ",".join(parts[1:-1]).strip()
        processes.append(ProcessUse(pid=pid, name=name, used_mb=used_mb))
    return tuple(processes)


def _default_runner(query: list[str]) -> str:
    if not query or query[0] not in {NVIDIA_SMI, "nvidia-smi"}:
        raise VramError("refusing to run a non nvidia-smi query")
    try:
        completed = subprocess.run(  # noqa: S603
            query,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VramError(f"failed to run nvidia-smi: {exc}") from exc
    return completed.stdout


class NvidiaSmiReader:
    def __init__(self, runner: SmiRunner | None = None) -> None:
        self._runner = runner or _default_runner

    def read(self) -> VramSnapshot:
        memory = parse_smi_memory(self._runner(list(MEMORY_QUERY)))
        processes = parse_smi_processes(self._runner(list(PROCESS_QUERY)))
        return replace(memory, processes=processes)
