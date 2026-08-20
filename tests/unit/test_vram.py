from __future__ import annotations

import pytest

from inglenook.errors import VramError
from inglenook.vram import AutoVramReader, ComfyStatsReader, parse_comfy_system_stats


def test_parse_comfy_system_stats_bytes() -> None:
    payload = {
        "devices": [
            {"vram_total": 17163091968, "vram_free": 2097152000},
        ]
    }
    snap = parse_comfy_system_stats(payload)
    assert snap.total_mb == 16368
    assert snap.free_mb == 2000
    assert snap.used_mb == 14368


def test_parse_comfy_system_stats_tight_free_still_bytes() -> None:
    payload = {
        "devices": [{"vram_total": 17163091968, "vram_free": 50000}],
    }
    snap = parse_comfy_system_stats(payload)
    assert snap.total_mb == 16368
    assert snap.free_mb == 0
    assert snap.used_mb == 16368


def test_parse_comfy_system_stats_already_mb() -> None:
    payload = {"system": {"devices": [{"vram_total": 16303, "vram_free": 15100}]}}
    snap = parse_comfy_system_stats(payload)
    assert snap.total_mb == 16303
    assert snap.free_mb == 15100
    assert snap.used_mb == 1203


def test_parse_comfy_system_stats_missing_devices() -> None:
    with pytest.raises(ValueError, match="devices"):
        parse_comfy_system_stats({})


def test_comfy_stats_reader_uses_fetcher() -> None:
    payload = {"devices": [{"vram_total": 16303, "vram_free": 8000}]}

    def fetch(_url: str) -> dict[str, object]:
        return payload

    snap = ComfyStatsReader("http://gpu.lan:8188", fetcher=fetch).read()
    assert snap.free_mb == 8000
    assert snap.total_mb == 16303


def test_auto_reader_prefers_working_smi(monkeypatch: pytest.MonkeyPatch) -> None:
    from inglenook.types import VramSnapshot

    monkeypatch.setenv("COMFYUI_URL", "http://gpu.lan:8188")
    smi_snap = VramSnapshot(total_mb=16303, used_mb=1800, free_mb=14503)
    called = {"comfy": False}

    def comfy(_url: str) -> dict[str, object]:
        called["comfy"] = True
        return {"devices": [{"vram_total": 1, "vram_free": 1}]}

    reader = AutoVramReader(smi_reader=lambda: smi_snap, comfy_fetcher=comfy)
    assert reader.read() == smi_snap
    assert called["comfy"] is False


def test_auto_reader_falls_back_to_comfy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMFYUI_URL", "http://gpu.lan:8188")
    payload = {"devices": [{"vram_total": 16303, "vram_free": 9000}]}

    def fail_smi() -> None:
        raise VramError("no nvidia-smi")

    reader = AutoVramReader(
        smi_reader=lambda: fail_smi(),  # type: ignore[arg-type]
        comfy_fetcher=lambda _url: payload,
    )
    snap = reader.read()
    assert snap.free_mb == 9000


def test_auto_reader_raises_when_smi_and_comfy_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COMFYUI_URL", raising=False)

    def fail_smi() -> None:
        raise VramError("no nvidia-smi")

    reader = AutoVramReader(smi_reader=lambda: fail_smi())  # type: ignore[arg-type]
    with pytest.raises(VramError, match="nvidia-smi"):
        reader.read()


def test_parse_comfy_system_stats_rejects_bad_device() -> None:
    with pytest.raises(ValueError, match="devices"):
        parse_comfy_system_stats({"devices": ["nope"]})
    with pytest.raises(ValueError, match="devices"):
        parse_comfy_system_stats({"devices": [{"vram_total": "x", "vram_free": 1}]})


def test_comfy_stats_reader_wraps_fetch_errors() -> None:
    def boom(_url: str) -> dict[str, object]:
        raise ConnectionError("down")

    with pytest.raises(VramError, match="ComfyUI"):
        ComfyStatsReader("http://gpu.lan:8188", fetcher=boom).read()


def test_default_reader_uses_comfy_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from inglenook.vram import default_reader

    monkeypatch.setenv("INGLENOOK_VRAM_SOURCE", "comfy")
    monkeypatch.setenv("COMFYUI_URL", "http://gpu.lan:8188")
    reader = default_reader()
    assert isinstance(reader, ComfyStatsReader)


def test_default_reader_comfy_requires_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from inglenook.vram import default_reader

    monkeypatch.setenv("INGLENOOK_VRAM_SOURCE", "comfy")
    monkeypatch.delenv("COMFYUI_URL", raising=False)
    with pytest.raises(VramError, match="COMFYUI_URL"):
        default_reader()


def test_default_reader_nvidia_smi(monkeypatch: pytest.MonkeyPatch) -> None:
    from inglenook.nvml import NvidiaSmiReader
    from inglenook.vram import default_reader

    monkeypatch.setenv("INGLENOOK_VRAM_SOURCE", "nvidia-smi")
    assert isinstance(default_reader(), NvidiaSmiReader)


def test_default_reader_rejects_unknown_source(monkeypatch: pytest.MonkeyPatch) -> None:
    from inglenook.vram import default_reader

    monkeypatch.setenv("INGLENOOK_VRAM_SOURCE", "come")
    with pytest.raises(VramError, match="INGLENOOK_VRAM_SOURCE"):
        default_reader()
