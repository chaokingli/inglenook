# AGENTS.md

Thin VRAM gate on top of llama-swap. llama-swap owns process lifecycle. This repo only answers: is there enough free VRAM, and if not, who may be unloaded? It is not an OpenAI gateway.

Python 3.11+, src layout. Package: `inglenook`.

```
src/inglenook/     gate (ensure_free)
tests/unit/        pytest, no hardware
tests/integration/ local sockets
deploy/            llama-swap.yaml, gate.yaml, systemd, scripts, live-switch-report.md
docker/            image entrypoint and llama-swap installer
workflows/api/     Comfy API-format JSON (no LLM nodes)
scripts/           version bump used by CI
```

## Commands

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

pytest --cov=inglenook --cov-report=term-missing   # fail_under 80
pytest -m unit
pytest -m integration

ruff check src tests scripts
ruff format src tests scripts
mypy

python -m build
```

CI (`.github/workflows/test.yml`) runs pytest with coverage, then `ruff check src tests scripts`.

Do not bump `pyproject.toml` / `src/inglenook/__init__.py` by hand. Use `python scripts/bump_version.py`.

Local status (does not take the GPU):

```bash
PYTHONPATH=src python3 -m inglenook --config deploy/gate.yaml status
```

## Code style

- `from __future__ import annotations` in every module.
- Type every public function. mypy `strict` on `inglenook`.
- Frozen dataclasses and tuples; do not mutate snapshots, backends, or results.
- Inject hardware via Protocols (`VramReader`, `Unloader`, `BusyChecker`). Tests use fakes in `tests/conftest.py`.
- Ruff: line length 88, py311, rules `E,F,I,N,W,UP,B,S`. Tests may use `assert` (`S101`).
- Errors: raise `InglenookError` subclasses; CLI prints `error: …` and non-zero.
- Occupancy is `policy.occupancy: weights` (llama.cpp `/models` or `/props`). Do not use `/health` to decide who owns VRAM.
- Unload llama.cpp with `POST /models/unload`. Unload Comfy with `/api/free`.
- Do not spawn a second `llama-server`. `:8198` already owns GGUF weights; llama-swap proxies it.
- HTTP sidecar (`inglenook serve`) binds localhost only.
- Comfy graphs in `workflows/api/` must stay API-format JSON with no LLM nodes.

## Do not modify

- `src/inglenook.egg-info/`
- `dist/`, `build/`, `.venv/`
- `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`
- `LICENSE`
