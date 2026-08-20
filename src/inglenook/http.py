from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from inglenook.errors import InglenookError
from inglenook.runtime import read_vram, run_ensure_free
from inglenook.types import parse_backend_name

MAX_BODY = 8192
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost"})
_ENSURE_LOCK = threading.Lock()


class GateServer:
    def __init__(self, host: str, port: int, config_path: Path) -> None:
        if host not in ALLOWED_HOSTS:
            raise InglenookError("HTTP sidecar must bind localhost")
        self._httpd = ThreadingHTTPServer((host, port), _make_handler(config_path))
        self.port = int(self._httpd.server_address[1])

    def serve_forever(self) -> None:
        self._httpd.serve_forever()

    def shutdown(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


def serve_forever(host: str, port: int, config_path: Path) -> None:
    if host not in ALLOWED_HOSTS:
        raise InglenookError("HTTP sidecar must bind localhost")
    GateServer(host=host, port=port, config_path=config_path).serve_forever()


def _make_handler(config_path: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            if _path(self.path) != "/v1/status":
                self._send(404, {"error": "not found"})
                return
            snap = read_vram()
            self._send(
                200,
                {
                    "total_mb": snap.total_mb,
                    "used_mb": snap.used_mb,
                    "free_mb": snap.free_mb,
                },
            )

        def do_POST(self) -> None:
            if _path(self.path) != "/v1/ensure-free":
                self._send(404, {"error": "not found"})
                return
            payload = self._read_json()
            if payload is None:
                return
            raw_backend = payload.get("backend", "")
            try:
                backend = parse_backend_name(str(raw_backend))
            except ValueError:
                self._send(400, {"error": "invalid backend name"})
                return
            try:
                with _ENSURE_LOCK:
                    result = run_ensure_free(backend, config_path)
            except InglenookError as exc:
                self._send(500, {"error": str(exc)})
                return
            code = 200 if result.admitted else 503
            self._send(code, result.__dict__)

        def _read_json(self) -> dict[str, Any] | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send(400, {"error": "invalid content-length"})
                return None
            if length < 0 or length > MAX_BODY:
                self._send(413, {"error": "payload too large"})
                return None
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send(400, {"error": "invalid json"})
                return None
            if not isinstance(data, dict):
                self._send(400, {"error": "json object required"})
                return None
            return data

        def _send(self, code: int, body: dict[str, Any]) -> None:
            blob = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

    return Handler


def _path(raw: str) -> str:
    return urlparse(raw).path
