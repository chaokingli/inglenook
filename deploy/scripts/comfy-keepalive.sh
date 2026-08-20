#!/usr/bin/env bash
# Keep ComfyUI resident while llama-swap treats this model as "running".
# If 8188 is already healthy, do not restart it. Otherwise start it bound to localhost.
set -euo pipefail

COMFY_URL="${COMFY_URL:-http://127.0.0.1:8188}"
START_COMFY="${START_COMFY:-$HOME/comfy/start-comfyui.sh}"

is_up() {
    curl -fsS --max-time 2 "${COMFY_URL}/system_stats" >/dev/null
}

if is_up; then
    exec tail -f /dev/null
fi

if [[ ! -x "$START_COMFY" ]]; then
    echo "comfy-keepalive: missing start script $START_COMFY" >&2
    exit 1
fi

# Bind only to loopback so NAS/ST cannot bypass the split proxy on :9293.
"$START_COMFY" minimax --listen 127.0.0.1 &
for i in $(seq 1 90); do
    if is_up; then
        exec tail -f /dev/null
    fi
    sleep 2
done

echo "comfy-keepalive: ComfyUI did not become healthy on ${COMFY_URL}" >&2
exit 1
