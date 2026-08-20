from __future__ import annotations

import pytest

from inglenook.nvml import NvidiaSmiReader, parse_smi_memory, parse_smi_processes


def test_parse_smi_memory_csv() -> None:
    snap = parse_smi_memory("16303, 14648, 1234\n")
    assert snap.total_mb == 16303
    assert snap.used_mb == 14648
    assert snap.free_mb == 1234
    assert snap.processes == ()


def test_parse_smi_memory_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="nvidia-smi"):
        parse_smi_memory("not-a-csv")


def test_parse_smi_processes() -> None:
    raw = "7503, /usr/local/bin/llama-server, 14624\n11434, ollama, 512\n"
    procs = parse_smi_processes(raw)
    assert len(procs) == 2
    assert procs[0].pid == 7503
    assert procs[0].used_mb == 14624
    assert "llama-server" in procs[0].name
    assert procs[1].name == "ollama"


def test_parse_smi_processes_empty() -> None:
    assert parse_smi_processes("") == ()
    assert parse_smi_processes("\n") == ()


def test_parse_smi_memory_empty() -> None:
    with pytest.raises(ValueError, match="nvidia-smi"):
        parse_smi_memory("   \n")


def test_parse_smi_processes_skips_malformed() -> None:
    assert parse_smi_processes("not-csv\n7503, llama, nope\n") == ()


def test_reader_raises_vram_error_on_os_error() -> None:
    from inglenook.errors import VramError
    from inglenook.nvml import _default_runner

    with pytest.raises(VramError):
        _default_runner(["false-binary-that-does-not-exist"])


def test_reader_combines_memory_and_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(query: list[str]) -> str:
        calls.append(query)
        if "memory.total" in query[1]:
            return "16303, 14648, 1234"
        return "7503, llama-server, 14624"

    reader = NvidiaSmiReader(runner=fake_run)
    snap = reader.read()
    assert snap.used_mb == 14648
    assert snap.processes[0].pid == 7503
    assert len(calls) == 2
