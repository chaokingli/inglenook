from __future__ import annotations

from pathlib import Path

from inglenook.config import GateConfig, load_config
from inglenook.gate import Gate
from inglenook.nvml import NvidiaSmiReader
from inglenook.occupancy import HealthOccupancy, ProbeBusyChecker
from inglenook.types import EnsureResult, VramSnapshot
from inglenook.unload import CommandUnloader


def read_vram() -> VramSnapshot:
    return NvidiaSmiReader().read()


def build_gate(cfg: GateConfig, reader: NvidiaSmiReader | None = None) -> Gate:
    vram_reader = reader or NvidiaSmiReader()
    occupancy = HealthOccupancy(
        registry=cfg.registry,
        reader=vram_reader.read,
        idle_used_mb=cfg.policy.idle_used_mb,
    )
    return Gate(
        registry=cfg.registry,
        policy=cfg.policy,
        reader=vram_reader,
        unloader=CommandUnloader(),
        occupancy=occupancy,
        busy_checker=ProbeBusyChecker(),
    )


def run_ensure_free(backend: str, config: Path) -> EnsureResult:
    cfg = load_config(config)
    return build_gate(cfg).ensure_free(backend)
