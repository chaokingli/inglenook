from __future__ import annotations

import json
import subprocess
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlparse

from inglenook.types import Backend

CommandRunner = Callable[[tuple[str, ...]], int]
HttpPoster = Callable[[str, Mapping[str, Any]], None]


def comfy_free_payload() -> dict[str, bool]:
    return {"unload_models": True, "free_memory": True}


def llama_unload_url(backend: Backend) -> str:
    return backend.base_url.rstrip("/") + "/models/unload"


class CommandUnloader:
    def __init__(
        self,
        runner: CommandRunner | None = None,
        http_post: HttpPoster | None = None,
    ) -> None:
        self._runner = runner or _run_command
        self._http_post = http_post or _http_post_json

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
                self._http_post(llama_unload_url(backend), {})
            return
        raise ValueError(f"unsupported unload_kind: {backend.unload_kind}")


def _run_command(argv: tuple[str, ...]) -> int:
    if not argv:
        return 0
    completed = subprocess.run(list(argv), check=False, timeout=60)  # noqa: S603
    return int(completed.returncode)


def _http_post_json(url: str, payload: Mapping[str, Any]) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=10) as resp:
            resp.read(65536)
    except OSError:
        return
