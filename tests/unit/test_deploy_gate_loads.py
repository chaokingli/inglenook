from __future__ import annotations

from pathlib import Path

from inglenook.config import load_config


def test_shipped_gate_yaml_loads() -> None:
    path = Path(__file__).resolve().parents[2] / "deploy" / "gate.yaml"
    cfg = load_config(path)
    assert "qwen38-chat" in cfg.registry
    assert "ls_comfyui" in cfg.registry
    assert cfg.policy.unload_timeout_s == 180
    assert cfg.policy.occupancy.value == "health"
