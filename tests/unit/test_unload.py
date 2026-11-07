from __future__ import annotations

from inglenook.types import Backend, Role
from inglenook.unload import (
    CommandUnloader,
    comfy_free_payload,
    llama_loaded_model_ids,
    llama_unload_payload,
    llama_unload_url,
)


def test_comfy_free_payload() -> None:
    assert comfy_free_payload() == {"unload_models": True, "free_memory": True}


def test_llama_unload_url_uses_backend_base() -> None:
    backend = Backend(
        name="qwen38-chat",
        need_mb=1,
        base_url="http://127.0.0.1:5801/",
        unload_kind="llama-unload",
    )
    assert llama_unload_url(backend) == "http://127.0.0.1:5801/models/unload"


def test_command_unloader_runs_allowlisted_argv() -> None:
    ran: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...]) -> int:
        ran.append(argv)
        return 0

    backend = Backend(
        name="tts-heavy",
        need_mb=1,
        role=Role.TTS,
        unload_kind="command",
        unload_command=("echo", "unload-tts"),
    )
    CommandUnloader(runner=runner).unload(backend)
    assert ran == [("echo", "unload-tts")]


def test_command_unloader_skips_empty_command() -> None:
    ran: list[tuple[str, ...]] = []
    backend = Backend(name="x", need_mb=1, unload_kind="command", unload_command=())
    CommandUnloader(runner=lambda argv: ran.append(argv) or 0).unload(backend)
    assert ran == []


def test_command_unloader_skips_none_kind() -> None:
    posted: list[str] = []
    backend = Backend(name="x", need_mb=1, unload_kind="none")
    CommandUnloader(http_post=lambda url, payload: posted.append(url)).unload(backend)
    assert posted == []


def test_command_unloader_posts_comfy_free() -> None:
    posted: list[tuple[str, object]] = []
    backend = Backend(
        name="ls_comfyui",
        need_mb=1,
        role=Role.COMFY,
        unload_kind="comfy-free",
        base_url="http://127.0.0.1:8188",
    )

    def capture(url: str, payload: object) -> None:
        posted.append((url, payload))

    CommandUnloader(http_post=capture).unload(backend)
    assert posted == [("http://127.0.0.1:8188/api/free", comfy_free_payload())]


def test_llama_unload_payload_includes_model_id() -> None:
    assert llama_unload_payload("qwen35-code") == {"model": "qwen35-code"}


def test_llama_loaded_model_ids_reads_router_status() -> None:
    payload = {
        "data": [
            {"id": "qwen38-chat", "status": {"value": "unloaded"}},
            {"id": "qwen35-code", "status": {"value": "loaded"}},
            {"id": "qwen27-chat", "status": "loading"},
        ]
    }
    assert llama_loaded_model_ids(payload) == ("qwen35-code", "qwen27-chat")


def test_command_unloader_posts_llama_unload() -> None:
    posted: list[tuple[str, object]] = []
    backend = Backend(
        name="qwen38-chat",
        need_mb=1,
        unload_kind="llama-unload",
        base_url="http://127.0.0.1:5801",
    )
    CommandUnloader(
        http_post=lambda url, payload: posted.append((url, payload)),
        json_get=lambda _url: ConnectionError("down"),
    ).unload(backend)
    assert posted == [
        ("http://127.0.0.1:5801/models/unload", llama_unload_payload("qwen38-chat"))
    ]


def test_command_unloader_unloads_loaded_router_models() -> None:
    posted: list[tuple[str, object]] = []
    backend = Backend(
        name="qwen38-chat",
        need_mb=1,
        unload_kind="llama-unload",
        base_url="http://127.0.0.1:8198",
    )

    def json_get(url: str) -> dict[str, object]:
        assert url.endswith("/models")
        return {
            "data": [
                {"id": "qwen38-chat", "status": {"value": "unloaded"}},
                {"id": "qwen35-code", "status": {"value": "loaded"}},
            ]
        }

    CommandUnloader(
        http_post=lambda url, payload: posted.append((url, payload)),
        json_get=json_get,
    ).unload(backend)
    assert posted == [
        ("http://127.0.0.1:8198/models/unload", llama_unload_payload("qwen35-code"))
    ]


def test_command_unloader_posts_remote_comfy_free() -> None:
    posted: list[str] = []
    backend = Backend(
        name="ls_comfyui",
        need_mb=1,
        role=Role.COMFY,
        unload_kind="comfy-free",
        base_url="http://192.168.1.10:8188",
    )
    CommandUnloader(http_post=lambda url, _payload: posted.append(url)).unload(backend)
    assert posted == ["http://192.168.1.10:8188/api/free"]
