from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from inglenook.probes import (
    JsonGet,
    comfy_is_busy,
    fetch_json,
    llama_is_reachable,
    llama_loaded_model_ids,
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
        if self._occupancy is OccupancyKind.WEIGHTS:
            found = self._loaded_chat_weights()
            if found:
                return found | self._loaded_tts()
        else:
            found = set()
            for backend in self._registry.values():
                if backend.role is not Role.CHAT:
                    continue
                if llama_is_reachable(backend, self._fetcher):
                    found.add(backend.name)
            if found:
                return frozenset(found) | self._loaded_tts()
        tts = self._loaded_tts()
        try:
            snap = self._reader()
        except Exception:
            return tts
        if snap.used_mb <= self._idle_used_mb:
            return tts
        residual: set[str] = set(tts)
        for backend in self._registry.values():
            if backend.role is Role.COMFY and backend.base_url:
                residual.add(backend.name)
        return frozenset(residual)

    def _loaded_tts(self) -> frozenset[str]:
        found: set[str] = set()
        for backend in self._registry.values():
            if backend.role is not Role.TTS or not backend.base_url:
                continue
            if llama_is_reachable(backend, self._fetcher):
                found.add(backend.name)
        return frozenset(found)

    def _loaded_chat_weights(self) -> frozenset[str]:
        found: set[str] = set()
        chats: list[Backend] = [
            backend
            for backend in self._registry.values()
            if backend.role is Role.CHAT and backend.base_url
        ]
        loaded_by_origin: dict[str, tuple[str, ...]] = {}
        for backend in chats:
            origin = backend.base_url.rstrip("/")
            if origin not in loaded_by_origin:
                payload = self._models_payload(origin)
                loaded_by_origin[origin] = (
                    llama_loaded_model_ids(payload) if payload is not None else ()
                )
            if backend.name in loaded_by_origin[origin]:
                found.add(backend.name)
        if found:
            return frozenset(found)
        registered = {backend.name for backend in chats}
        for origin, loaded_ids in loaded_by_origin.items():
            if not any(model_id not in registered for model_id in loaded_ids):
                continue
            candidates = [
                backend for backend in chats if backend.base_url.rstrip("/") == origin
            ]
            if not candidates:
                continue
            catch = [backend for backend in candidates if backend.catch_all]
            pool = catch or candidates
            pick = sorted(pool, key=lambda backend: (backend.priority, backend.name))[0]
            found.add(pick.name)
        return frozenset(found)

    def _models_payload(self, origin: str) -> dict[str, object] | None:
        getter = self._json_get
        if getter is None:
            try:
                payload = fetch_json(origin + "/models")
            except (OSError, ValueError, ConnectionError):
                return None
            return dict(payload)
        try:
            result = getter(origin + "/models")
        except Exception:
            return None
        if isinstance(result, BaseException) or not isinstance(result, dict):
            return None
        return dict(result)


class ProbeBusyChecker:
    def is_busy(self, backend: Backend) -> bool:
        if backend.busy_probe == "none" or not backend.base_url:
            return False
        if backend.busy_probe == "comfy-queue":
            try:
                payload = fetch_json(backend.base_url.rstrip("/") + "/prompt")
            except (OSError, ValueError, ConnectionError):
                return False
            return comfy_is_busy(payload)
        if backend.busy_probe == "llama-health":
            return llama_is_reachable(backend)
        return False
