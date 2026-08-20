from __future__ import annotations

from pathlib import Path

from inglenook.cli import main
from inglenook.types import EnsureResult, VramSnapshot

GATE_YAML = """
policy:
  unload_timeout_s: 1
backends:
  qwen38-chat:
    need_mb: 100
    headroom_mb: 0
    role: chat
    group: gpu-exclusive
    unload_kind: none
"""


def test_cli_status_prints_snapshot(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(GATE_YAML, encoding="utf-8")

    monkeypatch.setattr(
        "inglenook.cli.read_vram",
        lambda: VramSnapshot(total_mb=16303, used_mb=1800, free_mb=14200),
    )
    code = main(["--config", str(path), "status"])
    out = capsys.readouterr().out
    assert code == 0
    assert "16303" in out
    assert "1800" in out


def test_cli_ensure_free_exit_zero_when_admitted(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(GATE_YAML, encoding="utf-8")
    monkeypatch.setattr(
        "inglenook.cli.run_ensure_free",
        lambda *args, **kwargs: EnsureResult(
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
    assert main(["--config", str(path), "ensure-free", "--backend", "qwen38-chat"]) == 0


def test_cli_ensure_free_exit_three_when_rejected(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(GATE_YAML, encoding="utf-8")
    monkeypatch.setattr(
        "inglenook.cli.run_ensure_free",
        lambda *args, **kwargs: EnsureResult(
            admitted=False,
            status="rejected",
            unloaded=(),
            waited_ms=1000,
            used_mb=14648,
            free_mb=1234,
            reason="comfy_busy_timeout",
            warning="",
        ),
    )
    assert main(["--config", str(path), "ensure-free", "--backend", "qwen38-chat"]) == 3


def test_cli_rejects_unsafe_backend_name(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(GATE_YAML, encoding="utf-8")
    assert main(["--config", str(path), "ensure-free", "--backend", "../etc"]) == 1


def test_cli_show_config(tmp_path: Path, capsys) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(GATE_YAML, encoding="utf-8")
    assert main(["--config", str(path), "show-config"]) == 0
    assert "qwen38-chat" in capsys.readouterr().out


def test_cli_convert_ini(tmp_path: Path, capsys) -> None:
    ini = Path(__file__).resolve().parents[1] / "fixtures" / "models-adapted.sample.ini"
    path = tmp_path / "gate.yaml"
    path.write_text(GATE_YAML, encoding="utf-8")
    assert main(["--config", str(path), "convert-ini", "--ini", str(ini)]) == 0
    assert "qwen38-chat:" in capsys.readouterr().out


def test_cli_unknown_command_without_subcommand(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(GATE_YAML, encoding="utf-8")
    assert main(["--config", str(path)]) == 1
