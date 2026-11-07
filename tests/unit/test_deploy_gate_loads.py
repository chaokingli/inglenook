from __future__ import annotations

from pathlib import Path

from inglenook.config import load_config


def test_shipped_gate_yaml_loads() -> None:
    path = Path(__file__).resolve().parents[2] / "deploy" / "gate.yaml"
    cfg = load_config(path)
    assert "qwen38-chat" not in cfg.registry
    assert "qwen35-chat" in cfg.registry
    assert "ls_comfyui" in cfg.registry
    assert "tts-heavy" in cfg.registry
    assert "qwen35-voice" in cfg.registry
    assert cfg.registry["tts-heavy"].group == "gpu-exclusive"
    assert cfg.registry["tts-heavy"].base_url == "http://127.0.0.1:8210"
    assert "qwen35-voice" in cfg.registry["tts-heavy"].coexist_with
    assert "tts-heavy" in cfg.registry["qwen35-voice"].coexist_with
    assert cfg.registry["qwen35-chat"].catch_all is True
    assert cfg.policy.unload_timeout_s == 180
    assert cfg.policy.occupancy.value == "weights"
    assert cfg.registry["qwen35-voice"].base_url == "http://127.0.0.1:8198"
