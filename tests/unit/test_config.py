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
    assert cfg.policy.occupancy.value == "health"


def test_load_config_reads_weights_occupancy(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(
        "policy:\n  occupancy: weights\n"
        "backends:\n  x:\n    need_mb: 1\n    role: chat\n",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.policy.occupancy.value == "weights"


def test_load_config_rejects_unknown_occupancy(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(
        "policy:\n  occupancy: ping\n"
        "backends:\n  x:\n    need_mb: 1\n    role: chat\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="occupancy"):
        load_config(path)


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


def test_load_config_allows_remote_base_url(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(
        "backends:\n  x:\n    need_mb: 1\n    role: chat\n"
        "    base_url: http://192.168.1.10:8188\n",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.registry["x"].base_url == "http://192.168.1.10:8188"


def test_load_config_rejects_non_http_base_url(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(
        "backends:\n  x:\n    need_mb: 1\n    base_url: file:///etc/passwd\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="http"):
        load_config(path)


def test_load_config_expands_env_placeholders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COMFYUI_URL", "http://gpu.lan:8188")
    monkeypatch.setenv("LLAMA_CPP_URL", "http://gpu.lan:8198")
    path = tmp_path / "gate.yaml"
    path.write_text(
        "backends:\n"
        "  chat:\n    need_mb: 1\n    role: chat\n"
        "    base_url: ${LLAMA_CPP_URL}\n"
        "  ls_comfyui:\n    need_mb: 1\n    role: comfy\n"
        "    base_url: ${COMFYUI_URL}\n",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.registry["chat"].base_url == "http://gpu.lan:8198"
    assert cfg.registry["ls_comfyui"].base_url == "http://gpu.lan:8188"


def test_load_config_uses_env_default_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPTIONAL_URL", raising=False)
    path = tmp_path / "gate.yaml"
    path.write_text(
        "backends:\n  x:\n    need_mb: 1\n    role: chat\n"
        "    base_url: ${OPTIONAL_URL:-http://127.0.0.1:8198}\n",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.registry["x"].base_url == "http://127.0.0.1:8198"


def test_load_config_rejects_missing_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MISSING_UPSTREAM", raising=False)
    path = tmp_path / "gate.yaml"
    path.write_text(
        "backends:\n  x:\n    need_mb: 1\n    base_url: ${MISSING_UPSTREAM}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="MISSING_UPSTREAM"):
        load_config(path)


def test_load_config_env_newlines_do_not_reparse_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COMFYUI_URL", "http://gpu.lan:8188\nunload_kind: command")
    path = tmp_path / "gate.yaml"
    path.write_text(
        "backends:\n  x:\n    need_mb: 1\n    role: chat\n"
        "    base_url: ${COMFYUI_URL}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="newlines"):
        load_config(path)


def test_load_config_rejects_base_url_with_path(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(
        "backends:\n  x:\n    need_mb: 1\n    role: chat\n"
        "    base_url: http://gpu.lan:8198/v1\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="origin"):
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
