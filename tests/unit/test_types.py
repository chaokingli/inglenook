from __future__ import annotations

import pytest

from inglenook.types import Backend, Role, VramSnapshot, parse_backend_name


def test_required_free_includes_headroom() -> None:
    backend = Backend(name="qwen38-chat", need_mb=14600, headroom_mb=800)
    assert backend.required_free_mb == 15400


def test_vram_snapshot_rejects_negative() -> None:
    with pytest.raises(ValueError, match="negative"):
        VramSnapshot(total_mb=16303, used_mb=-1, free_mb=1)


def test_parse_backend_name_accepts_safe_ids() -> None:
    assert parse_backend_name("qwen38-chat") == "qwen38-chat"
    assert parse_backend_name("ls_comfyui") == "ls_comfyui"
    assert parse_backend_name("tts.heavy") == "tts.heavy"


@pytest.mark.parametrize("raw", ["", "../etc", "a/b", "has space", "qwen;rm", "x" * 65])
def test_parse_backend_name_rejects_unsafe_ids(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_backend_name(raw)


def test_role_from_string() -> None:
    assert Role("chat") is Role.CHAT
    assert Role("comfy") is Role.COMFY
