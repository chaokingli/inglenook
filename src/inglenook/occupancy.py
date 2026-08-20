from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from inglenook.probes import (
    JsonGet,
    comfy_is_busy,
    fetch_json,
    llama_is_reachable,
    llama_weights_loaded,
)
from inglenook.types import Backend, OccupancyKind, Role, VramSnapshot


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
        occupancy: OccupancyKind | str = OccupancyKind.HEALTH,
        json_get: JsonGet | None = None,
    ) -> None:
        self._registry = registry
        self._reader = reader
        self._idle_used_mb = idle_used_mb
        self._fetcher = fetcher
        self._occupancy = OccupancyKind(occupancy)
        self._json_get = json_get

    def loaded(self) -> frozenset[str]:
        found: set[str] = set()
        chat_present = False
        for backend in self._registry.values():
            if backend.role is not Role.CHAT:
                continue
            if self._chat_occupies(backend):
                found.add(backend.name)
                chat_present = True
        if chat_present:
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

    def _chat_occupies(self, backend: Backend) -> bool:
        if self._occupancy is OccupancyKind.WEIGHTS:
            return llama_weights_loaded(backend, json_get=self._json_get)
        return llama_is_reachable(backend, self._fetcher)


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
