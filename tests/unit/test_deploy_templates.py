from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"


def test_llama_swap_yaml_has_exclusive_group_and_comfy() -> None:
    data = yaml.safe_load((DEPLOY / "llama-swap.yaml").read_text(encoding="utf-8"))
    assert "comfyui_auto" in data["models"]
    assert data["models"]["comfyui_auto"]["unlisted"] is True
    group = data["routing"]["router"]["settings"]["groups"]["gpu-exclusive"]
    members = group["members"]
    assert "comfyui_auto" in members
    assert "qwen35-voice" not in members
    assert "qwen38-chat" not in members
    assert "qwen38-chat" not in data["models"]
    assert "tts-heavy" not in members
    voice_grp = data["routing"]["router"]["settings"]["groups"]["voice-stack"]
    assert voice_grp["exclusive"] is True
    assert voice_grp["swap"] is False
    assert "tts-heavy" in voice_grp["members"]
    assert "qwen35-voice" in voice_grp["members"]
    assert "tts-heavy" in data["models"]
    assert "qwen35-code" in data["models"]["qwen35-voice"]["aliases"]
    assert data["models"]["tts-heavy"]["ttl"] == 0
    assert "8210" in str(data["models"]["tts-heavy"]["proxy"])
    assert "index-tts2" in data["models"]["tts-heavy"]["aliases"]
    front = (DEPLOY / "scripts" / "swap-front.py").read_text(encoding="utf-8")
    assert "/upstream/tts-heavy" in front
    assert "/api/v1/voices" in front
    unit = (DEPLOY / "systemd" / "llama-swap.service").read_text(encoding="utf-8")
    assert "swap-front.py" in unit
    assert "127.0.0.1:9291" in unit
    assert group["exclusive"] is True
    assert data["sendLoadingState"] is True
    assert data["models"]["comfyui_auto"]["unloadTimeout"] >= 180
    chat_cmd = data["models"]["qwen35-voice"]["cmd"]
    assert "swap_start" in chat_cmd
    assert "llama-server" not in chat_cmd
    assert "swap_start" in data["models"]["comfyui_auto"]["cmd"]
    assert "ls_comfyui" in data["models"]["comfyui_auto"]["cmd"]
    assert "swap-start.sh" in str(data.get("macros", {}))
    starter = (DEPLOY / "scripts" / "swap-start.sh").read_text(encoding="utf-8")
    assert "ensure-free" in starter
    assert "inglenook-keepalives" in starter
    assert "127.0.0.1:8198" in str(data["models"]["qwen35-voice"]["proxy"])
    assert data["models"]["qwen35-voice"]["ttl"] == 0
    assert data.get("includeAliasesInList") is True
    stop = data["models"]["qwen35-voice"]["cmdStop"]
    assert "swap_stop" in stop
    assert "qwen35-voice" in stop
    assert "comfyui" in data["models"]["comfyui_auto"]["aliases"]
    assert "ls_comfyui" in data["models"]["comfyui_auto"]["aliases"]
    assert "swap_stop" in data["models"]["comfyui_auto"]["cmdStop"]
    assert data["models"]["comfyui_auto"]["compat"]["ignoreWebsockets"] is True
    script = (DEPLOY / "scripts" / "llama-unload.sh").read_text(encoding="utf-8")
    assert "/models/unload" in script
    assert '"model"' in script or "model" in script
    stop_script = (DEPLOY / "scripts" / "swap-stop.sh").read_text(encoding="utf-8")
    assert "llama-unload.sh" in stop_script
    assert "comfy-free.sh" in stop_script
    assert "tts-heavy" in stop_script
    assert "voice-engine" in stop_script
    starter = (DEPLOY / "scripts" / "swap-start.sh").read_text(encoding="utf-8")
    assert "tts-heavy" in starter
    assert "serve.sh" in starter
    assert "8210/health" in starter
    assert "index-tts2" in (DEPLOY / "llama-swap.yaml").read_text(encoding="utf-8")


def test_gate_yaml_has_budgeted_backends() -> None:
    data = yaml.safe_load((DEPLOY / "gate.yaml").read_text(encoding="utf-8"))
    assert data["gpu"]["total_mb"] == 16303
    assert data["backends"]["qwen35-chat"]["need_mb"] >= 14000
    assert "qwen38-chat" not in data["backends"]
    assert data["backends"]["ls_comfyui"]["unload_kind"] == "comfy-free"
    tts = data["backends"]["tts-heavy"]
    assert tts["group"] == "gpu-exclusive"
    assert tts["unload_kind"] == "command"
    assert tts["base_url"] == "http://127.0.0.1:8210"
    assert "qwen35-voice" in tts["coexist_with"]
    voice = data["backends"]["qwen35-voice"]
    assert voice["need_mb"] <= 8000
    assert "tts-heavy" in voice["coexist_with"]
    assert data["backends"]["qwen35-chat"].get("catch_all") is True


def test_split_proxy_only_sends_mutating_comfy_paths() -> None:
    nginx = (DEPLOY / "nginx-comfy-split.conf").read_text(encoding="utf-8")
    assert "listen 9293" in nginx
    assert "proxy_read_timeout 900s" in nginx
    assert "/comfyui/" in nginx
    assert "127.0.0.1:8188" in nginx
    caddy = (DEPLOY / "Caddyfile.comfy-split").read_text(encoding="utf-8")
    assert "path /prompt /upload/image /interrupt" in caddy
    assert "method POST" in caddy
    proxy = (DEPLOY / "scripts" / "comfy-split-proxy.py").read_text(encoding="utf-8")
    assert "/upstream/comfyui_auto" in proxy
    assert '"/prompt"' in proxy
    assert "/inglenook/workflows" in proxy
    assert "--gate" in proxy
