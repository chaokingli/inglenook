from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from inglenook.errors import InglenookError
from inglenook.http import GateServer
from inglenook.types import EnsureResult, VramSnapshot


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    cfg = tmp_path / "gate.yaml"
    cfg.write_text(
        """
backends:
  qwen38-chat:
    need_mb: 100
    headroom_mb: 0
    role: chat
    unload_kind: none
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "inglenook.http.read_vram",
        lambda: VramSnapshot(total_mb=16303, used_mb=1800, free_mb=14200),
    )
    monkeypatch.setattr(
        "inglenook.http.run_ensure_free",
        lambda backend, config: EnsureResult(
            admitted=True,
            status="admitted",
            unloaded=(),
            waited_ms=0,
            used_mb=1800,
            free_mb=14200,
            reason="",
            warning="",
        ),
    )
    srv = GateServer(host="127.0.0.1", port=0, config_path=cfg)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{srv.port}"
    yield url
    srv.shutdown()
    thread.join(timeout=2)


def _get(url: str) -> tuple[int, dict[str, object]]:
    with urllib.request.urlopen(url, timeout=2) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def _post(
    url: str, payload: object, timeout: float = 2
) -> tuple[int, dict[str, object]]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read().decode("utf-8"))
        return exc.code, body


def test_status_endpoint(server: str) -> None:
    status, body = _get(f"{server}/v1/status")
    assert status == 200
    assert body["used_mb"] == 1800
    assert body["total_mb"] == 16303


def test_ensure_free_endpoint(server: str) -> None:
    status, body = _post(f"{server}/v1/ensure-free", {"backend": "qwen38-chat"})
    assert status == 200
    assert body["admitted"] is True


def test_rejects_unknown_path(server: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(f"{server}/secret")
    assert exc.value.code == 404


def test_rejects_unsafe_backend_name(server: str) -> None:
    status, body = _post(f"{server}/v1/ensure-free", {"backend": "../etc/passwd"})
    assert status == 400
    assert "backend" in body["error"].lower()


def test_rejects_negative_content_length(server: str) -> None:
    req = urllib.request.Request(
        f"{server}/v1/ensure-free",
        data=b'{"backend":"qwen38-chat"}',
        method="POST",
        headers={"Content-Type": "application/json", "Content-Length": "-1"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=2)
    assert exc.value.code == 413


def test_gate_server_rejects_non_localhost(tmp_path: Path) -> None:
    cfg = tmp_path / "gate.yaml"
    cfg.write_text("backends:\n  x:\n    need_mb: 1\n", encoding="utf-8")
    with pytest.raises(InglenookError, match="localhost"):
        GateServer(host="0.0.0.0", port=0, config_path=cfg)  # noqa: S104


def test_rejects_oversized_body(server: str) -> None:
    payload = {"backend": "qwen38-chat", "pad": "x" * 9000}
    status, body = _post(f"{server}/v1/ensure-free", payload)
    assert status == 413


def test_post_unknown_path(server: str) -> None:
    status, body = _post(f"{server}/v1/nope", {"backend": "qwen38-chat"})
    assert status == 404
    assert "not found" in body["error"]


def test_rejects_non_object_json(server: str) -> None:
    req = urllib.request.Request(
        f"{server}/v1/ensure-free",
        data=b"[1,2,3]",
        method="POST",
        headers={"Content-Type": "application/json", "Content-Length": "7"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=2)
    assert exc.value.code == 400


def test_rejects_non_json(server: str) -> None:
    req = urllib.request.Request(
        f"{server}/v1/ensure-free",
        data=b"not-json",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=2)
    assert exc.value.code == 400
