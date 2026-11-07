from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "deploy" / "scripts" / "swap-front.py"


def _load():
    spec = importlib.util.spec_from_file_location("swap_front", MODULE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rewrites_st_indextts_voice_paths() -> None:
    rewrite = _load().rewrite_target
    assert rewrite(b"/api/v1/voices") == b"/upstream/tts-heavy/api/v1/voices"
    assert rewrite(b"/api/v1/voices?x=1") == b"/upstream/tts-heavy/api/v1/voices?x=1"
    assert rewrite(b"/api/v1/upload") == b"/upstream/tts-heavy/api/v1/upload"
    assert rewrite(b"/api/v1/tts/tasks") == b"/upstream/tts-heavy/api/v1/tts/tasks"


def test_leaves_openai_and_chat_paths_alone() -> None:
    rewrite = _load().rewrite_target
    assert rewrite(b"/v1/audio/speech") == b"/v1/audio/speech"
    assert rewrite(b"/v1/chat/completions") == b"/v1/chat/completions"
    assert rewrite(b"/health") == b"/health"
    assert rewrite(b"/upstream/tts-heavy/health") == b"/upstream/tts-heavy/health"
