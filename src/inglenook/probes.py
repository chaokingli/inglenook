from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from inglenook.types import Backend
from inglenook.urls import http_opener, require_http_url

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


_WEIGHT_STATUSES = frozenset({"loaded", "loading"})
JsonGet = Callable[[str], Mapping[str, Any] | BaseException]


def llama_models_have_weights(payload: Mapping[str, Any]) -> bool | None:
    data = payload.get("data")
    if not isinstance(data, list):
        return None
    saw_status = False
    for item in data:
        if not isinstance(item, Mapping):
            continue
        status = item.get("status")
        value = ""
        if isinstance(status, Mapping):
            value = str(status.get("value", "")).lower()
        elif isinstance(status, str):
            value = status.lower()
        if not value:
            continue
        saw_status = True
        if value in _WEIGHT_STATUSES:
            return True
    if saw_status:
        return False
    return None


def llama_props_have_weights(payload: Mapping[str, Any]) -> bool | None:
    if "is_sleeping" not in payload:
        return None
    return not bool(payload.get("is_sleeping"))


def llama_weights_loaded(backend: Backend, json_get: JsonGet | None = None) -> bool:
    if not backend.base_url:
        return False
    getter = json_get or _default_json_get
    origin = backend.base_url.rstrip("/")
    models = _probe_json(getter, origin + "/models")
    if models is not None:
        decided = llama_models_have_weights(models)
        if decided is not None:
            return decided
    props = _probe_json(getter, origin + "/props")
    if props is not None:
        decided = llama_props_have_weights(props)
        if decided is not None:
            return decided
    return False


def _probe_json(getter: JsonGet, url: str) -> Mapping[str, Any] | None:
    try:
        result = getter(url)
    except Exception:
        return None
    if isinstance(result, BaseException) or not isinstance(result, Mapping):
        return None
    return result


def _default_json_get(url: str) -> Mapping[str, Any]:
    return fetch_json(url)


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


_NO_PROXY = http_opener()


def fetch_json(url: str, timeout_s: float = 2.0) -> Mapping[str, Any]:
    req = urllib.request.Request(require_http_url(url), method="GET")  # noqa: S310
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
    req = urllib.request.Request(require_http_url(url), method="GET")  # noqa: S310
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
