#!/usr/bin/env python3
"""Bump the project version in pyproject.toml and src/inglenook/__init__.py."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
INIT = ROOT / "src" / "inglenook" / "__init__.py"


def bump(version: str, part: str) -> str:
    pieces = version.split(".")
    if len(pieces) != 3 or not all(item.isdigit() for item in pieces):
        raise ValueError("version must be X.Y.Z")
    major, minor, patch = (int(item) for item in pieces)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown bump part: {part}")


def infer_part(message: str) -> str:
    head = message.split("\n", 1)[0]
    type_token = head.split(":", 1)[0]
    if "BREAKING CHANGE" in message or "!" in type_token:
        return "major"
    if type_token.startswith("feat"):
        return "minor"
    return "patch"


def replace_version(pyproject: Path, init: Path, new: str) -> None:
    py_text = pyproject.read_text(encoding="utf-8")
    py_new, count = re.subn(
        r'(?m)^version = "[^"]+"',
        f'version = "{new}"',
        py_text,
        count=1,
    )
    if count != 1:
        raise ValueError("could not find version in pyproject.toml")
    pyproject.write_text(py_new, encoding="utf-8")
    init_text = init.read_text(encoding="utf-8")
    init_new, count = re.subn(
        r'(?m)^__version__ = "[^"]+"',
        f'__version__ = "{new}"',
        init_text,
        count=1,
    )
    if count != 1:
        raise ValueError("could not find __version__")
    init.write_text(init_new, encoding="utf-8")


def read_version(pyproject: Path) -> str:
    text = pyproject.read_text(encoding="utf-8")
    match = re.search(r'(?m)^version = "([^"]+)"', text)
    if not match:
        raise ValueError("version not found")
    return match.group(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--part",
        choices=["patch", "minor", "major", "auto"],
        default="auto",
    )
    parser.add_argument("--message", default="")
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="print the current version and exit",
    )
    args = parser.parse_args(argv)
    current = read_version(PYPROJECT)
    if args.print_only:
        sys.stdout.write(current + "\n")
        return 0
    part = infer_part(args.message) if args.part == "auto" else args.part
    new = bump(current, part)
    replace_version(PYPROJECT, INIT, new)
    sys.stdout.write(new + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
