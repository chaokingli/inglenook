#!/usr/bin/env bash
# Unload ComfyUI weights without killing the process.
# Bounded loops only — llama-swap will cut an unbounded while.
set -euo pipefail

COMFY_URL="${COMFY_URL:-http://127.0.0.1:8188}"
IDLE_RATIO="${IDLE_RATIO:-0.90}"

queue_remaining() {
    curl -fsS --max-time 2 "${COMFY_URL}/prompt" \
        | python3 -c 'import json,sys; print(int(json.load(sys.stdin).get("exec_info",{}).get("queue_remaining",0)))'
}

vram_ratio() {
    python3 - "$COMFY_URL" <<'PY'
import json, sys, urllib.request
url = sys.argv[1].rstrip("/") + "/system_stats"
with urllib.request.urlopen(url, timeout=2) as resp:
    payload = json.load(resp)
devices = payload.get("devices") or payload.get("system", {}).get("devices") or []
if not devices:
    print("0")
    raise SystemExit
total = float(devices[0].get("vram_total") or 0)
free = float(devices[0].get("vram_free") or 0)
print(f"{(free / total) if total else 0:.4f}")
PY
}

for i in $(seq 1 450); do
    remaining="$(queue_remaining 2>/dev/null || echo 1)"
    if [[ "$remaining" == "0" ]]; then
        break
    fi
    sleep 2
done

remaining="$(queue_remaining 2>/dev/null || echo 1)"
if [[ "$remaining" != "0" ]]; then
    echo "comfy-free: queue still busy (${remaining}); refusing to /free" >&2
    exit 1
fi

curl -fsS --max-time 10 -X POST "${COMFY_URL}/api/free" \
    -H 'Content-Type: application/json' \
    -d '{"unload_models": true, "free_memory": true}' >/dev/null \
    || curl -fsS --max-time 10 -X POST "${COMFY_URL}/free" \
        -H 'Content-Type: application/json' \
        -d '{"unload_models": true, "free_memory": true}' >/dev/null \
    || true

for i in $(seq 1 60); do
    ratio="$(vram_ratio 2>/dev/null || echo 0)"
    python3 -c "import sys; sys.exit(0 if float('${ratio}') >= float('${IDLE_RATIO}') else 1)" && exit 0
    sleep 2
done

echo "comfy-free: VRAM did not drop below idle ratio ${IDLE_RATIO}" >&2
exit 1
