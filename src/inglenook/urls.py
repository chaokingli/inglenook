from __future__ import annotations

import os
import re
import urllib.request
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

_ENV_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class _RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        raise ValueError("http redirects are not allowed")


def http_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _RejectRedirect,
    )


def require_http_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("base_url must be http(s)")
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"base_url must be http(s): {url}")
    if not parsed.hostname:
        raise ValueError(f"base_url must be http(s) with a host: {url}")
    if parsed.username or parsed.password:
        raise ValueError(f"base_url must not include userinfo: {url}")
    return url


def require_http_origin(url: str) -> str:
    url = require_http_url(url)
    parsed = urlparse(url)
    path = parsed.path or ""
    if path not in {"", "/"}:
        raise ValueError(f"base_url must be an origin without a path: {url}")
    if parsed.query or parsed.params or parsed.fragment:
        raise ValueError(f"base_url must be an origin without a query: {url}")
    host = parsed.hostname or ""
    netloc = f"{host}:{parsed.port}" if parsed.port else host
    return f"{parsed.scheme}://{netloc}"


def expand_env(text: str, environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        default = match.group(2)
        value = env.get(key)
        if value:
            return value
        if default is not None:
            return default
        raise ValueError(f"missing environment variable: {key}")

    expanded = _ENV_PLACEHOLDER.sub(replace, text)
    if "\n" in expanded or "\r" in expanded:
        raise ValueError("environment values cannot contain newlines")
    return expanded


def expand_env_tree(value: Any, environ: Mapping[str, str] | None = None) -> Any:
    if isinstance(value, str):
        return expand_env(value, environ)
    if isinstance(value, dict):
        return {key: expand_env_tree(item, environ) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env_tree(item, environ) for item in value]
    return value
