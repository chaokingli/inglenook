#!/usr/bin/env python3
"""Public :9292 front for llama-swap.

SillyTavern IndexTTS plugins call GET/POST /api/v1/voices on the same host
as /v1/audio/speech. llama-swap only routes by JSON ``model`` (or
``/upstream/<id>/...``), so those paths 404. Rewrite them to
``/upstream/tts-heavy/api/v1/...`` so tts-heavy is loaded and the request
reaches voice-engine.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import subprocess
import sys
from typing import Sequence

log = logging.getLogger("swap-front")

TTS_PREFIXES = (
    b"/api/v1/voices",
    b"/api/v1/upload",
    b"/api/v1/tts/tasks",
    b"/api/v1/indextts2_cloning",
)
TTS_UPSTREAM = b"/upstream/tts-heavy"


def rewrite_target(target: bytes) -> bytes:
    path, sep, query = target.partition(b"?")
    if any(path == prefix or path.startswith(prefix + b"/") for prefix in TTS_PREFIXES):
        return TTS_UPSTREAM + path + (sep + query if sep else b"")
    if path == b"/api/v1" or path.startswith(b"/api/v1/"):
        return TTS_UPSTREAM + path + (sep + query if sep else b"")
    return target


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


def _build_request(
    method: bytes,
    target: bytes,
    version: bytes,
    headers: list[tuple[bytes, bytes]],
    host: bytes,
) -> bytes:
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
    backend: tuple[str, int],
) -> None:
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

    rewritten = rewrite_target(target)
    host = f"{backend[0]}:{backend[1]}".encode("ascii")
    request = _build_request(method, rewritten, version, headers, host)
    if rewritten != target:
        log.info(
            "%s %s -> %s",
            method.decode(),
            target.decode(errors="replace"),
            rewritten.decode(errors="replace"),
        )
    try:
        upstream_reader, upstream_writer = await asyncio.open_connection(*backend)
    except OSError as exc:
        log.warning("backend %s failed: %s", backend, exc)
        client_writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        await client_writer.drain()
        client_writer.close()
        return

    upstream_writer.write(request)
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


def _hostport(value: str) -> tuple[str, int]:
    host, _, port = value.rpartition(":")
    if not host or not port:
        raise argparse.ArgumentTypeError("expected host:port")
    return host, int(port)


def _spawn_swap(args: argparse.Namespace) -> subprocess.Popen[bytes] | None:
    if not args.swap_bin:
        return None
    cmd = [
        args.swap_bin,
        "--config",
        args.swap_config,
        "--listen",
        args.swap_listen,
    ]
    log.info("starting llama-swap: %s", " ".join(cmd))
    return subprocess.Popen(cmd)


async def _serve(listen: tuple[str, int], backend: tuple[str, int]) -> None:
    async def on_client(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await _handle(reader, writer, backend)

    server = await asyncio.start_server(on_client, listen[0], listen[1], limit=1024 * 1024)
    sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    log.info("listening on %s -> %s:%s", sockets, backend[0], backend[1])
    async with server:
        await server.serve_forever()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="llama-swap IndexTTS path front")
    parser.add_argument("--listen", default="0.0.0.0:9292", type=_hostport)
    parser.add_argument("--backend", default="127.0.0.1:9291", type=_hostport)
    parser.add_argument("--swap-bin", default="")
    parser.add_argument("--swap-config", default="")
    parser.add_argument("--swap-listen", default="127.0.0.1:9291")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s swap-front %(levelname)s %(message)s",
    )
    child = _spawn_swap(args)

    def _stop(signum: int, _frame: object) -> None:
        if child and child.poll() is None:
            child.send_signal(signum)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        asyncio.run(_serve(args.listen, args.backend))
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                child.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
