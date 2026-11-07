from __future__ import annotations

from pathlib import Path

import pytest

from inglenook.workflows import WorkflowError, list_workflows, save_workflow


def test_save_and_list_image_workflow(tmp_path: Path) -> None:
    graph = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}
    dest = save_workflow(tmp_path, "image", "demo", graph)
    assert dest.name == "demo.json"
    rows = list_workflows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["kind"] == "image"
    assert rows[0]["id"] == "demo"


def test_rejects_llm_nodes(tmp_path: Path) -> None:
    graph = {"9": {"class_type": "OllamaGenerate", "inputs": {}}}
    with pytest.raises(WorkflowError, match="LLM"):
        save_workflow(tmp_path, "video", "bad", graph)


def test_rejects_bad_kind(tmp_path: Path) -> None:
    with pytest.raises(WorkflowError, match="kind"):
        save_workflow(tmp_path, "audio", "x", {"1": {"class_type": "Empty"}})
