#!/usr/bin/env python3
"""Split reverse proxy on :9293 (stdlib, no Caddy required).

POST mutating Comfy paths go to llama-swap /comfyui/ (exclusive swap).
Everything else, including GET /prompt and WebSocket /ws, goes to :8188.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

SWAP_PATHS = {
    "/prompt",
    "/upload/image",
    "/interrupt",
    "/api/prompt",
    "/api/upload/image",
    "/api/interrupt",
}
WORKFLOW_PREFIX = b"/inglenook/workflows"

log = logging.getLogger("comfy-split-proxy")


def _header_value(headers: list[tuple[bytes, bytes]], name: bytes) -> bytes | None:
    target = name.lower()
    for key, value in headers:
        if key.lower() == target:
            return value
    return None


def _parse_headers(raw: bytes) -> tuple[bytes, bytes, bytes, list[tuple[bytes, bytes]]]:
    head, _, _rest = raw.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    if not lines or len(lines[0].split(b" ", 2)) < 2:
        raise ValueError("invalid request line")
    parts = lines[0].split(b" ", 2)
    method = parts[0]
    target = parts[1]
    version = parts[2] if len(parts) > 2 else b"HTTP/1.1"
    headers: list[tuple[bytes, bytes]] = []
    for line in lines[1:]:
        if not line or b":" not in line:
            continue
        key, _, value = line.partition(b":")
        headers.append((key.strip(), value.strip()))
    return method, target, version, headers


def _origin_path(target: bytes) -> bytes:
    path = target.split(b"?", 1)[0]
    return path if path.startswith(b"/") else b"/" + path


def _should_swap(method: bytes, target: bytes) -> bool:
    if method.upper() != b"POST":
        return False
    return _origin_path(target).decode("ascii", "replace") in SWAP_PATHS


def _is_workflow(target: bytes) -> bool:
    path = _origin_path(target)
    return path == WORKFLOW_PREFIX or path.startswith(WORKFLOW_PREFIX + b"/")


def _rewrite_request(
    method: bytes,
    target: bytes,
    version: bytes,
    headers: list[tuple[bytes, bytes]],
    *,
    swap: bool,
    gate: bool = False,
    host: bytes,
) -> bytes:
    if gate:
        path, sep, query = target.partition(b"?")
        path = path.replace(b"/inglenook/workflows", b"/v1/workflows", 1)
        target = path + (sep + query if sep else b"")
    elif swap:
        path, sep, query = target.partition(b"?")
        # llama-swap v250: POST /comfyui/prompt 409s unless the model is
        # already loaded. /upstream/<id>/prompt starts comfyui_auto.
        target = b"/upstream/comfyui_auto" + path + (sep + query if sep else b"")
    out_headers: list[bytes] = []
    seen_host = False
    for key, value in headers:
        lowered = key.lower()
        if lowered == b"host":
            out_headers.append(b"Host: " + host)
            seen_host = True
            continue
        if lowered == b"proxy-connection":
            continue
        out_headers.append(key + b": " + value)
    if not seen_host:
        out_headers.append(b"Host: " + host)
    return (
        method
        + b" "
        + target
        + b" "
        + version
        + b"\r\n"
        + b"\r\n".join(out_headers)
        + b"\r\n\r\n"
    )


async def _pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await src.read(65536)
            if not chunk:
                break
            dst.write(chunk)
            await dst.drain()
    except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
        pass
    finally:
        try:
            dst.close()
        except Exception:
            pass


async def _handle(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    comfy: tuple[str, int],
    swap: tuple[str, int],
    gate: tuple[str, int],
) -> None:
    peer = client_writer.get_extra_info("peername")
    try:
        header_buf = await client_reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionResetError):
        client_writer.close()
        return
    try:
        method, target, version, headers = _parse_headers(header_buf)
    except ValueError:
        client_writer.close()
        return

    use_gate = _is_workflow(target)
    use_swap = (not use_gate) and _should_swap(method, target)
    dest = gate if use_gate else (swap if use_swap else comfy)
    host = f"{dest[0]}:{dest[1]}".encode("ascii")
    rewritten = _rewrite_request(
        method,
        target,
        version,
        headers,
        swap=use_swap,
        gate=use_gate,
        host=host,
    )
    log.info(
        "%s %s %s -> %s:%s",
        peer,
        method.decode(),
        target.decode(errors="replace"),
        dest[0],
        dest[1],
    )
    try:
        upstream_reader, upstream_writer = await asyncio.open_connection(*dest)
    except OSError as exc:
        log.warning("upstream %s failed: %s", dest, exc)
        client_writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        await client_writer.drain()
        client_writer.close()
        return

    upstream_writer.write(rewritten)
    extra = header_buf.split(b"\r\n\r\n", 1)
    if len(extra) == 2 and extra[1]:
        upstream_writer.write(extra[1])
    await upstream_writer.drain()

    content_length = _header_value(headers, b"content-length")
    remaining = 0
    if content_length is not None:
        try:
            remaining = int(content_length)
        except ValueError:
            remaining = 0
        already = len(extra[1]) if len(extra) == 2 else 0
        remaining = max(0, remaining - already)
        while remaining > 0:
            chunk = await client_reader.read(min(65536, remaining))
            if not chunk:
                break
            upstream_writer.write(chunk)
            remaining -= len(chunk)
            await upstream_writer.drain()

    to_up = asyncio.create_task(_pipe(client_reader, upstream_writer))
    to_down = asyncio.create_task(_pipe(upstream_reader, client_writer))
    try:
        await asyncio.wait({to_up, to_down}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (to_up, to_down):
            task.cancel()
        try:
            client_writer.close()
        except Exception:
            pass
        try:
            upstream_writer.close()
        except Exception:
            pass


async def _serve(
    listen: tuple[str, int],
    comfy: tuple[str, int],
    swap: tuple[str, int],
    gate: tuple[str, int],
) -> None:
    async def on_client(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await _handle(reader, writer, comfy, swap, gate)

    server = await asyncio.start_server(on_client, listen[0], listen[1], limit=1024 * 1024)
    sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    log.info("listening on %s", sockets)
    async with server:
        await server.serve_forever()


def _hostport(value: str) -> tuple[str, int]:
    host, _, port = value.rpartition(":")
    if not host or not port:
        raise argparse.ArgumentTypeError("expected host:port")
    return host, int(port)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Comfy split reverse proxy")
    parser.add_argument("--listen", default="0.0.0.0:9293", type=_hostport)
    parser.add_argument("--comfy", default="127.0.0.1:8188", type=_hostport)
    parser.add_argument("--swap", default="127.0.0.1:9292", type=_hostport)
    parser.add_argument("--gate", default="127.0.0.1:9300", type=_hostport)
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s comfy-split-proxy %(levelname)s %(message)s",
    )
    try:
        asyncio.run(_serve(args.listen, args.comfy, args.swap, args.gate))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
