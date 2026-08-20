from __future__ import annotations

from pathlib import Path

import pytest

from inglenook.config import load_config
from inglenook.errors import ConfigError
from inglenook.types import Role

SAMPLE = """
gpu:
  total_mb: 16303
  idle_used_mb: 2500
  unknown_used_warn_mb: 4096

policy:
  exclusive_group: gpu-exclusive
  unload_timeout_s: 180
  poll_interval_ms: 500
  chat_waits_for_comfy: true
  generation_waits_for_chat_inflight: true
  generation_preempts_idle_chat: true
  stop_unknown: false

backends:
  qwen38-chat:
    need_mb: 14600
    headroom_mb: 800
    role: chat
    group: gpu-exclusive
    unload_kind: llama-unload
    base_url: http://127.0.0.1:5801
    priority: 50
  ls_comfyui:
    need_mb: 15000
    role: comfy
    group: gpu-exclusive
    persistent: true
    unload_kind: comfy-free
    busy_probe: comfy-queue
    base_url: http://127.0.0.1:8188
    priority: 80
"""


def test_load_config_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(SAMPLE, encoding="utf-8")
    cfg = load_config(path)
    assert cfg.policy.idle_used_mb == 2500
    assert cfg.policy.unload_timeout_s == 180
    assert "qwen38-chat" in cfg.registry
    chat = cfg.registry["qwen38-chat"]
    assert chat.role is Role.CHAT
    assert chat.required_free_mb == 15400
    assert cfg.registry["ls_comfyui"].persistent is True


def test_load_config_rejects_missing_backends(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text("policy: {}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="backends"):
        load_config(path)


def test_load_config_rejects_bad_need_mb(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(
        "backends:\n  x:\n    need_mb: -3\n    role: chat\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="need_mb"):
        load_config(path)


def test_load_config_rejects_non_local_base_url(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(
        "backends:\n  x:\n    need_mb: 1\n    base_url: http://8.8.8.8:9\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="localhost"):
        load_config(path)


def test_load_config_rejects_unknown_role(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(
        "backends:\n  x:\n    need_mb: 1\n    role: spaceship\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="role"):
        load_config(path)


def test_load_config_rejects_unknown_unload_kind(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(
        "backends:\n  x:\n    need_mb: 1\n    unload_kind: explode\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unload_kind"):
        load_config(path)
