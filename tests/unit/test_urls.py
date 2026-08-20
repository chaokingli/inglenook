from __future__ import annotations

import pytest

from inglenook.urls import expand_env, require_http_origin, require_http_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8188",
        "http://localhost:8198/v1",
        "https://gpu.lan:8188",
        "http://192.168.1.10:8188",
        "http://10.0.0.5",
    ],
)
def test_require_http_url_accepts_http_hosts(url: str) -> None:
    assert require_http_url(url) == url.strip()


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://gpu.lan/model",
        "http:///no-host",
        "not-a-url",
        "",
    ],
)
def test_require_http_url_rejects_non_http(url: str) -> None:
    with pytest.raises(ValueError, match="http"):
        require_http_url(url)


def test_require_http_origin_strips_trailing_slash() -> None:
    assert require_http_origin("http://gpu.lan:8188/") == "http://gpu.lan:8188"


def test_require_http_origin_rejects_path() -> None:
    with pytest.raises(ValueError, match="origin"):
        require_http_origin("http://gpu.lan:8198/v1")


def test_require_http_url_rejects_userinfo() -> None:
    with pytest.raises(ValueError, match="userinfo"):
        require_http_url("http://user:pass@gpu.lan:8188")


def test_expand_env_uses_default_when_value_empty() -> None:
    text = expand_env(
        "${OPTIONAL_URL:-http://127.0.0.1:8198}",
        environ={"OPTIONAL_URL": ""},
    )
    assert text == "http://127.0.0.1:8198"


def test_expand_env_rejects_newlines() -> None:
    with pytest.raises(ValueError, match="newlines"):
        expand_env("${INJECT}", environ={"INJECT": "http://x\nunload_kind: command"})
