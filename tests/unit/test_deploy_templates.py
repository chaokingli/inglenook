from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"


def test_llama_swap_yaml_has_exclusive_group_and_comfy() -> None:
    data = yaml.safe_load((DEPLOY / "llama-swap.yaml").read_text(encoding="utf-8"))
    assert "ls_comfyui" in data["models"]
    assert data["models"]["ls_comfyui"]["unlisted"] is True
    group = data["routing"]["router"]["settings"]["groups"]["gpu-exclusive"]
    members = group["members"]
    assert "ls_comfyui" in members
    assert "qwen38-chat" in members
    assert group["exclusive"] is True
    assert data["sendLoadingState"] is True
    assert data["models"]["ls_comfyui"]["unloadTimeout"] >= 180
    chat_cmd = data["models"]["qwen38-chat"]["cmd"]
    assert "set -euo pipefail" in chat_cmd
    assert data["models"]["ls_comfyui"]["compat"]["ignoreWebsockets"] is True


def test_gate_yaml_has_budgeted_backends() -> None:
    data = yaml.safe_load((DEPLOY / "gate.yaml").read_text(encoding="utf-8"))
    assert data["gpu"]["total_mb"] == 16303
    assert data["backends"]["qwen38-chat"]["need_mb"] >= 14000
    assert data["backends"]["ls_comfyui"]["unload_kind"] == "comfy-free"


def test_split_proxy_only_sends_mutating_comfy_paths() -> None:
    nginx = (DEPLOY / "nginx-comfy-split.conf").read_text(encoding="utf-8")
    assert "listen 9293" in nginx
    assert "proxy_read_timeout 900s" in nginx
    assert "/comfyui/" in nginx
    assert "127.0.0.1:8188" in nginx
    caddy = (DEPLOY / "Caddyfile.comfy-split").read_text(encoding="utf-8")
    assert "path /prompt /upload/image /interrupt" in caddy
    assert "method POST" in caddy
