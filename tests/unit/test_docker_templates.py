from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from inglenook.config import load_config

ROOT = Path(__file__).resolve().parents[2]
DOCKER = ROOT / "deploy" / "docker"


def test_compose_yaml_matches_docker_compose_yml() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    legacy = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert compose == legacy


def test_compose_yaml_exposes_chat_and_image_ports() -> None:
    data = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    service = data["services"]["inglenook"]
    ports = service["ports"]
    joined = "\n".join(str(item) for item in ports)
    assert "9292" in joined
    assert "9293" in joined
    env = service["environment"]
    env_text = yaml.safe_dump(env)
    assert "COMFYUI_URL" in env_text
    assert "LLAMA_CPP_URL" in env_text
    image = str(service["image"])
    assert "ghcr.io" in image
    assert "inglenook" in image


def test_docker_gate_yaml_uses_upstream_env_placeholders() -> None:
    text = (DOCKER / "gate.yaml").read_text(encoding="utf-8")
    assert "${COMFYUI_URL}" in text
    assert "${LLAMA_CPP_URL}" in text
    data = yaml.safe_load(
        text.replace("${COMFYUI_URL}", "http://gpu:8188").replace(
            "${LLAMA_CPP_URL}", "http://gpu:8198"
        )
    )
    assert data["backends"]["ls_comfyui"]["base_url"] == "http://gpu:8188"
    assert data["backends"]["ls_comfyui"]["unload_kind"] == "comfy-free"
    chat = data["backends"]["qwen38-chat"]
    assert chat["base_url"] == "http://gpu:8198"
    assert chat["unload_kind"] == "llama-unload"


def test_docker_llama_swap_yaml_proxies_to_env_upstreams() -> None:
    data = yaml.safe_load((DOCKER / "llama-swap.yaml").read_text(encoding="utf-8"))
    models = data["models"]
    assert "ls_comfyui" in models
    assert "qwen38-chat" in models
    assert "${env.LLAMA_CPP_URL}" in str(models["qwen38-chat"]["proxy"])
    assert "${env.COMFYUI_URL}" in str(models["ls_comfyui"]["proxy"])
    group = data["routing"]["router"]["settings"]["groups"]["gpu-exclusive"]
    assert group["exclusive"] is True
    assert "ls_comfyui" in group["members"]
    chat_cmd = models["qwen38-chat"]["cmd"]
    assert "ensure-free" in chat_cmd
    assert models["ls_comfyui"]["unlisted"] is True
    assert "comfyui" in models["ls_comfyui"]["aliases"]


def test_docker_comfy_keepalive_does_not_start_local_comfy() -> None:
    text = (DOCKER / "comfy-keepalive.sh").read_text(encoding="utf-8")
    assert "start-comfyui" not in text
    assert "system_stats" in text
    caddy = (ROOT / "docker" / "Caddyfile.template").read_text(encoding="utf-8")
    assert "rewrite * /comfyui{uri}" in caddy
    assert "handle /healthz" in caddy


def test_dockerfile_installs_llama_swap_and_inglenook() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "llama-swap" in text
    assert "entrypoint.sh" in text
    assert "EXPOSE 9292" in text


def test_env_example_documents_upstream_urls() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "COMFYUI_URL=" in text
    assert "LLAMA_CPP_URL=" in text


def test_docker_gate_yaml_loads_with_upstream_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMFYUI_URL", "http://gpu.lan:8188")
    monkeypatch.setenv("LLAMA_CPP_URL", "http://gpu.lan:8198")
    cfg = load_config(DOCKER / "gate.yaml")
    assert cfg.registry["qwen38-chat"].base_url == "http://gpu.lan:8198"
    assert cfg.registry["ls_comfyui"].base_url == "http://gpu.lan:8188"
    assert cfg.policy.occupancy.value == "weights"
