#!/usr/bin/env bash
# Keep llama-swap's Comfy member "running" while the remote ComfyUI process lives.
# Do not start Comfy from the NAS container.
set -euo pipefail

COMFY_URL="${COMFY_URL:-${COMFYUI_URL:-http://127.0.0.1:8188}}"

is_up() {
    curl -fsS --max-time 2 "${COMFY_URL}/system_stats" >/dev/null
}

if ! is_up; then
    echo "comfy-keepalive: ComfyUI is not reachable at ${COMFY_URL}" >&2
    exit 1
fi

exec tail -f /dev/null
