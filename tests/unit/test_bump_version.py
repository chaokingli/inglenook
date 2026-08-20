from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bump_version.py"


def _load():
    spec = importlib.util.spec_from_file_location("bump_version", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bump_patch_minor_major() -> None:
    bump = _load().bump
    assert bump("0.1.0", "patch") == "0.1.1"
    assert bump("0.1.9", "minor") == "0.2.0"
    assert bump("0.9.4", "major") == "1.0.0"


def test_infer_part_from_conventional_commit() -> None:
    infer = _load().infer_part
    assert infer("feat: add docker compose") == "minor"
    assert infer("feat!: drop localhost-only urls") == "major"
    assert infer("fix: unload remote comfy\n\nBREAKING CHANGE: remote urls") == "major"
    assert infer("fix: gate timeout") == "patch"
    assert infer("chore: docs") == "patch"


def test_replace_version_in_pyproject_and_init(tmp_path: Path) -> None:
    replace_version = _load().replace_version
    pyproject = tmp_path / "pyproject.toml"
    init = tmp_path / "__init__.py"
    pyproject.write_text('[project]\nversion = "0.1.0"\n', encoding="utf-8")
    init.write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    replace_version(pyproject, init, "0.1.1")
    assert 'version = "0.1.1"' in pyproject.read_text(encoding="utf-8")
    assert '__version__ = "0.1.1"' in init.read_text(encoding="utf-8")


def test_bump_rejects_unknown_part() -> None:
    with pytest.raises(ValueError, match="part"):
        _load().bump("0.1.0", "build")


def test_print_only_does_not_change_files(tmp_path: Path, capsys) -> None:
    module = _load()
    code = module.main(["--print-only"])
    assert code == 0
    assert capsys.readouterr().out.strip() == "0.1.0"
