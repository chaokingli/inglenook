from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

from inglenook.errors import VramError
from inglenook.nvml import NvidiaSmiReader
from inglenook.probes import fetch_json
from inglenook.types import VramSnapshot
from inglenook.urls import require_http_origin

JsonFetcher = Callable[[str], Mapping[str, Any]]
SmiRead = Callable[[], VramSnapshot]

_BYTES_THRESHOLD = 100_000


def parse_comfy_system_stats(payload: Mapping[str, Any]) -> VramSnapshot:
    devices = payload.get("devices")
    if not isinstance(devices, list):
        system = payload.get("system")
        if isinstance(system, Mapping):
            devices = system.get("devices")
    if not isinstance(devices, list) or not devices:
        raise ValueError("comfy system_stats payload has no devices")
    first = devices[0]
    if not isinstance(first, Mapping):
        raise ValueError("comfy system_stats payload has no devices")
    total_raw = first.get("vram_total")
    free_raw = first.get("vram_free")
    if not isinstance(total_raw, (int, float)):
        raise ValueError("comfy system_stats payload has no devices")
    if not isinstance(free_raw, (int, float)):
        raise ValueError("comfy system_stats payload has no devices")
    as_bytes = float(total_raw) > _BYTES_THRESHOLD
    total_mb = _to_mb(total_raw, as_bytes=as_bytes)
    free_mb = _to_mb(free_raw, as_bytes=as_bytes)
    used_mb = max(total_mb - free_mb, 0)
    return VramSnapshot(total_mb=total_mb, used_mb=used_mb, free_mb=free_mb)


def _to_mb(value: int | float, *, as_bytes: bool) -> int:
    if as_bytes:
        return int(float(value) // (1024 * 1024))
    return int(value)


class ComfyStatsReader:
    def __init__(
        self,
        base_url: str,
        fetcher: JsonFetcher | None = None,
    ) -> None:
        origin = require_http_origin(base_url)
        self._url = origin.rstrip("/") + "/system_stats"
        self._fetcher = fetcher or fetch_json

    def read(self) -> VramSnapshot:
        try:
            payload = self._fetcher(self._url)
            return parse_comfy_system_stats(payload)
        except (OSError, ValueError, ConnectionError) as exc:
            raise VramError(f"failed to read ComfyUI VRAM: {exc}") from exc


class AutoVramReader:
    def __init__(
        self,
        smi_reader: SmiRead | None = None,
        comfy_fetcher: JsonFetcher | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._smi = smi_reader or NvidiaSmiReader().read
        self._comfy_fetcher = comfy_fetcher
        self._environ = environ

    def read(self) -> VramSnapshot:
        try:
            return self._smi()
        except VramError:
            env = os.environ if self._environ is None else self._environ
            url = str(env.get("COMFYUI_URL", "")).strip()
            if not url:
                raise
            return ComfyStatsReader(url, fetcher=self._comfy_fetcher).read()


def default_reader() -> NvidiaSmiReader | ComfyStatsReader | AutoVramReader:
    source = os.environ.get("INGLENOOK_VRAM_SOURCE", "auto").strip().lower()
    if source == "comfy":
        url = os.environ.get("COMFYUI_URL", "").strip()
        if not url:
            raise VramError("COMFYUI_URL is required when INGLENOOK_VRAM_SOURCE=comfy")
        return ComfyStatsReader(url)
    if source in {"nvidia-smi", "nvml", "smi"}:
        return NvidiaSmiReader()
    if source in {"auto", ""}:
        return AutoVramReader()
    raise VramError(f"unknown INGLENOOK_VRAM_SOURCE: {source}")
