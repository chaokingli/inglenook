from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlparse

from inglenook.types import Backend

Fetcher = Callable[[str], tuple[int, str] | BaseException]


def comfy_is_busy(payload: Mapping[str, Any]) -> bool:
    exec_info = payload.get("exec_info")
    if not isinstance(exec_info, Mapping):
        return False
    remaining = exec_info.get("queue_remaining", 0)
    try:
        return int(remaining) > 0
    except (TypeError, ValueError):
        return False


def comfy_vram_free_ratio(payload: Mapping[str, Any]) -> float | None:
    devices = _devices(payload)
    if not devices:
        return None
    first = devices[0]
    if not isinstance(first, Mapping):
        return None
    total = first.get("vram_total")
    free = first.get("vram_free")
    if not isinstance(total, (int, float)) or not isinstance(free, (int, float)):
        return None
    if total <= 0:
        return None
    return float(free) / float(total)


def llama_is_reachable(backend: Backend, fetcher: Fetcher | None = None) -> bool:
    if not backend.base_url:
        return False
    url = backend.base_url.rstrip("/") + "/health"
    fetch = fetcher or default_http_get
    try:
        result = fetch(url)
    except Exception:
        return False
    if isinstance(result, BaseException):
        return False
    status, _body = result
    return status == 200


_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _require_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("only http(s) URLs are allowed")
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("only localhost URLs are allowed")
    return url


def fetch_json(url: str, timeout_s: float = 2.0) -> Mapping[str, Any]:
    req = urllib.request.Request(_require_http_url(url), method="GET")  # noqa: S310
    try:
        with _NO_PROXY.open(req, timeout=timeout_s) as resp:
            raw = resp.read(65536).decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError) as exc:
        raise ConnectionError(str(exc)) from exc
    data = json.loads(raw)
    if not isinstance(data, Mapping):
        raise ValueError("expected a JSON object")
    return data


def default_http_get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(_require_http_url(url), method="GET")  # noqa: S310
    try:
        with _NO_PROXY.open(req, timeout=2) as resp:
            body = resp.read(65536).decode("utf-8", errors="replace")
            return int(resp.status), body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), body


def _devices(payload: Mapping[str, Any]) -> list[Any]:
    devices = payload.get("devices")
    if isinstance(devices, list):
        return devices
    system = payload.get("system")
    if isinstance(system, Mapping):
        nested = system.get("devices")
        if isinstance(nested, list):
            return nested
    return []
