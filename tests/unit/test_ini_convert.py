from __future__ import annotations

from pathlib import Path

from inglenook.ini_convert import convert_models_ini, parse_models_ini

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "models-adapted.sample.ini"


def test_parse_models_ini_skips_star_section() -> None:
    models = parse_models_ini(FIXTURE.read_text(encoding="utf-8"))
    names = [m.name for m in models]
    assert names == ["qwen38-chat", "qwen38-code"]
    chat = models[0]
    assert chat.model.endswith("qwen38-27b-q4_k.gguf")
    assert chat.mmproj.endswith("bf16.gguf")
    assert chat.values["ctx-size"] == "65536"
    assert chat.values["offline"] == "1"
    assert chat.values["jinja"] == "1"


def test_convert_models_ini_emits_llama_swap_cmds() -> None:
    text = convert_models_ini(FIXTURE.read_text(encoding="utf-8"))
    assert "qwen38-chat:" in text
    assert "${llama_server}" in text
    assert "--model /models/qwen38-27b-q4_k.gguf" in text
    assert "--mmproj /models/mmproj-model-bf16.gguf" in text
    assert "--ctx-size 65536" in text
    assert "--jinja" in text
    assert "group: gpu-exclusive" in text
    assert "members:" in text
    assert "qwen38-code" in text
