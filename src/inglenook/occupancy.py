from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from inglenook.probes import comfy_is_busy, fetch_json, llama_is_reachable
from inglenook.types import Backend, Role, VramSnapshot


class Occupancy(Protocol):
    def loaded(self) -> frozenset[str]: ...


class BusyChecker(Protocol):
    def is_busy(self, backend: Backend) -> bool: ...


class HealthOccupancy:
    def __init__(
        self,
        registry: Mapping[str, Backend],
        reader: Callable[[], VramSnapshot],
        idle_used_mb: int,
        fetcher: Callable[[str], tuple[int, str] | BaseException] | None = None,
    ) -> None:
        self._registry = registry
        self._reader = reader
        self._idle_used_mb = idle_used_mb
        self._fetcher = fetcher

    def loaded(self) -> frozenset[str]:
        found: set[str] = set()
        llama_up = False
        for backend in self._registry.values():
            if backend.role is Role.CHAT and llama_is_reachable(backend, self._fetcher):
                found.add(backend.name)
                llama_up = True
        if llama_up:
            return frozenset(found)
        try:
            snap = self._reader()
        except Exception:
            return frozenset(found)
        if snap.used_mb <= self._idle_used_mb:
            return frozenset(found)
        for backend in self._registry.values():
            if backend.role is Role.COMFY and backend.base_url:
                found.add(backend.name)
        return frozenset(found)


class ProbeBusyChecker:
    def is_busy(self, backend: Backend) -> bool:
        if backend.busy_probe == "none" or not backend.base_url:
            return False
        if backend.busy_probe == "comfy-queue":
            try:
                payload = fetch_json(backend.base_url.rstrip("/") + "/prompt")
            except (OSError, ValueError, ConnectionError):
                return True
            return comfy_is_busy(payload)
        if backend.busy_probe == "llama-health":
            return llama_is_reachable(backend)
        return False
