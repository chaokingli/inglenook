#!/bin/sh
set -eu

: "${COMFYUI_URL:?set COMFYUI_URL to the ComfyUI server, e.g. http://192.168.1.10:8188}"
: "${LLAMA_CPP_URL:?set LLAMA_CPP_URL to the llama.cpp server, e.g. http://192.168.1.10:8198}"

export COMFY_URL="$COMFYUI_URL"
export INGLENOOK_VRAM_SOURCE="${INGLENOOK_VRAM_SOURCE:-auto}"
export COMFY_UPSTREAM="$(python3 - <<'PY'
import os
from urllib.parse import urlparse

parsed = urlparse(os.environ["COMFYUI_URL"])
if parsed.scheme not in {"http", "https"} or not parsed.hostname:
    raise SystemExit("COMFYUI_URL must be http(s)://host[:port]")
port = parsed.port or (443 if parsed.scheme == "https" else 80)
if parsed.scheme == "https":
    print(f"https://{parsed.hostname}:{port}")
else:
    print(f"{parsed.hostname}:{port}")
PY
)"

CONFIG_DIR="${INGLENOOK_CONFIG_DIR:-/etc/inglenook}"
LISTEN="${LLAMA_SWAP_LISTEN:-0.0.0.0:9292}"
pids=""

cleanup() {
    trap - INT TERM EXIT
    if [ -n "$pids" ]; then
        kill $pids 2>/dev/null || true
        wait $pids 2>/dev/null || true
    fi
}
trap cleanup INT TERM EXIT

inglenook --config "${CONFIG_DIR}/gate.yaml" serve --host 127.0.0.1 --port 9300 \
  >/var/lib/inglenook/gate.log 2>&1 &
pids="$!"
caddy run --config "${CONFIG_DIR}/Caddyfile" --adapter caddyfile \
  >/var/lib/inglenook/caddy.log 2>&1 &
pids="$pids $!"
llama-swap --config "${CONFIG_DIR}/llama-swap.yaml" --listen "$LISTEN" &
swap_pid=$!
pids="$pids $swap_pid"
wait "$swap_pid"
status=$?
cleanup
exit "$status"
