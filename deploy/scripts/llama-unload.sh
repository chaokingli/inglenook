#!/usr/bin/env bash
# Unload whatever llama.cpp router currently has in VRAM.
# POST /models/unload requires {"model": "<id>"}; an empty body is a 400.
set -euo pipefail

LLAMA_URL="${LLAMA_CPP_URL:-${LLAMA_URL:-http://127.0.0.1:8198}}"

python3 - "$LLAMA_URL" <<'PY'
import json
import sys
import urllib.error
import urllib.request

origin = sys.argv[1].rstrip("/")
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(url: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    with opener.open(req, timeout=5) as resp:
        data = json.loads(resp.read(65536).decode("utf-8", errors="replace"))
    return data if isinstance(data, dict) else {}


def post_unload(model_id: str) -> None:
    body = json.dumps({"model": model_id}).encode("utf-8")
    req = urllib.request.Request(
        origin + "/models/unload",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with opener.open(req, timeout=10) as resp:
            resp.read(65536)
    except urllib.error.HTTPError as exc:
        # already unloaded / unknown id
        exc.read()


try:
    payload = get(origin + "/models")
except (OSError, urllib.error.URLError, json.JSONDecodeError):
    raise SystemExit(0)

loaded = []
for item in payload.get("data") or []:
    if not isinstance(item, dict):
        continue
    status = item.get("status")
    if isinstance(status, dict):
        value = str(status.get("value", "")).lower()
    else:
        value = str(status or "").lower()
    model_id = item.get("id")
    if isinstance(model_id, str) and value in {"loaded", "loading"}:
        loaded.append(model_id)

for model_id in loaded:
    post_unload(model_id)
PY
