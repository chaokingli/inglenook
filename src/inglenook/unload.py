from __future__ import annotations

import json
import subprocess
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from inglenook.probes import JsonGet, fetch_json, llama_loaded_model_ids
from inglenook.types import Backend
from inglenook.urls import http_opener, require_http_url

CommandRunner = Callable[[tuple[str, ...]], int]
HttpPoster = Callable[[str, Mapping[str, Any]], None]


def comfy_free_payload() -> dict[str, bool]:
    return {"unload_models": True, "free_memory": True}


def llama_unload_payload(model_id: str) -> dict[str, str]:
    return {"model": model_id}


def llama_unload_url(backend: Backend) -> str:
    return backend.base_url.rstrip("/") + "/models/unload"


class CommandUnloader:
    def __init__(
        self,
        runner: CommandRunner | None = None,
        http_post: HttpPoster | None = None,
        json_get: JsonGet | None = None,
    ) -> None:
        self._runner = runner or _run_command
        self._http_post = http_post or _http_post_json
        self._json_get = json_get

    def unload(self, backend: Backend) -> None:
        if backend.unload_kind == "none":
            return
        if backend.unload_kind == "command":
            if backend.unload_command:
                self._runner(backend.unload_command)
            return
        if backend.unload_kind == "comfy-free":
            if backend.base_url:
                self._http_post(
                    backend.base_url.rstrip("/") + "/api/free",
                    comfy_free_payload(),
                )
            return
        if backend.unload_kind == "llama-unload":
            if backend.base_url:
                self._unload_llama(backend)
            return
        raise ValueError(f"unsupported unload_kind: {backend.unload_kind}")

    def _unload_llama(self, backend: Backend) -> None:
        url = llama_unload_url(backend)
        for model_id in self._llama_targets(backend):
            self._http_post(url, llama_unload_payload(model_id))

    def _llama_targets(self, backend: Backend) -> tuple[str, ...]:
        origin = backend.base_url.rstrip("/")
        payload = self._models_payload(origin)
        if payload is not None:
            loaded = llama_loaded_model_ids(payload)
            if loaded:
                return loaded
        return (backend.name,)

    def _models_payload(self, origin: str) -> Mapping[str, Any] | None:
        getter = self._json_get
        if getter is None:
            try:
                return fetch_json(origin + "/models")
            except (OSError, ValueError, ConnectionError):
                return None
        try:
            result = getter(origin + "/models")
        except Exception:
            return None
        if isinstance(result, BaseException) or not isinstance(result, Mapping):
            return None
        return result


def _run_command(argv: tuple[str, ...]) -> int:
    if not argv:
        return 0
    completed = subprocess.run(list(argv), check=False, timeout=60)  # noqa: S603
    return int(completed.returncode)


def _http_post_json(url: str, payload: Mapping[str, Any]) -> None:
    try:
        require_http_url(url)
    except ValueError:
        return
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    opener = http_opener()
    try:
        with opener.open(req, timeout=10) as resp:
            resp.read(65536)
    except OSError:
        return
