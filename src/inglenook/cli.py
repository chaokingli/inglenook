from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from inglenook.config import load_config
from inglenook.errors import InglenookError
from inglenook.ini_convert import convert_models_ini
from inglenook.runtime import read_vram, run_ensure_free
from inglenook.types import parse_backend_name


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return _dispatch(args)
    except InglenookError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "status":
        snap = read_vram()
        print(
            f"total_mb={snap.total_mb} used_mb={snap.used_mb} free_mb={snap.free_mb}"
        )
        for proc in snap.processes:
            print(f"  pid={proc.pid} used_mb={proc.used_mb} name={proc.name}")
        return 0
    if args.command == "ensure-free":
        backend = parse_backend_name(args.backend)
        result = run_ensure_free(backend, Path(args.config))
        print(json.dumps(result.__dict__, indent=2))
        if result.admitted:
            return 0
        return 3
    if args.command == "convert-ini":
        text = Path(args.ini).read_text(encoding="utf-8")
        sys.stdout.write(convert_models_ini(text))
        return 0
    if args.command == "serve":
        from inglenook.http import serve_forever

        serve_forever(host=args.host, port=args.port, config_path=Path(args.config))
        return 0
    if args.command == "show-config":
        cfg = load_config(Path(args.config))
        print(f"backends={', '.join(sorted(cfg.registry))}")
        return 0
    print("error: unknown command", file=sys.stderr)
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="inglenook")
    parser.add_argument(
        "--config",
        default="deploy/gate.yaml",
        help="path to gate.yaml",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status")
    ensure = sub.add_parser("ensure-free")
    ensure.add_argument("--backend", required=True)
    sub.add_parser("show-config")
    convert = sub.add_parser("convert-ini")
    convert.add_argument("--ini", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=9300)
    return parser
