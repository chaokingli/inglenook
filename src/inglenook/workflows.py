from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from inglenook.errors import ConfigError

KINDS = frozenset({"image", "video"})
_NAME = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_LLM_HINTS = ("llama", "llm", "ollama", "lmstudio")


class WorkflowError(ConfigError):
    pass


def workflows_root(config_path: Path) -> Path:
    override = os.environ.get("INGLENOOK_WORKFLOWS")
    if override:
        return Path(override)
    # deploy/gate.yaml -> repo/workflows/api
    return config_path.resolve().parents[1] / "workflows" / "api"


def list_workflows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for kind in ("image", "video"):
        folder = root / kind
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            stat = path.stat()
            rows.append(
                {
                    "id": path.stem,
                    "kind": kind,
                    "name": path.name,
                    "bytes": stat.st_size,
                    "mtime": int(stat.st_mtime),
                }
            )
    return rows


def save_workflow(root: Path, kind: str, name: str, payload: Any) -> Path:
    if kind not in KINDS:
        raise WorkflowError("kind must be image or video")
    stem = name.removesuffix(".json")
    if not _NAME.fullmatch(stem):
        raise WorkflowError("name must match [A-Za-z0-9._-]{1,80}")
    graph = _as_graph(payload)
    _reject_llm_nodes(graph)
    dest_dir = root / kind
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{stem}.json"
    dest.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def _as_graph(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise WorkflowError("workflow must be a JSON object")
    if "prompt" in payload and isinstance(payload["prompt"], dict):
        return payload
    # Comfy API format is a node map
    if payload and all(isinstance(k, str) for k in payload):
        return payload
    raise WorkflowError("workflow JSON is empty")


def _reject_llm_nodes(graph: dict[str, Any]) -> None:
    nodes = graph.get("prompt") if isinstance(graph.get("prompt"), dict) else graph
    if not isinstance(nodes, dict):
        return
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type", "")).lower()
        if any(hint in class_type for hint in _LLM_HINTS):
            raise WorkflowError(
                f"LLM/llama nodes are not allowed in API workflows ({class_type})"
            )
