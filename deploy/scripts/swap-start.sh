#!/usr/bin/env bash
# llama-swap v250 execs cmd tokens directly (no shell). Keep this as the argv0.
set -euo pipefail

BACKEND="${1:?backend name}"
if [[ -n "${INGLENOOK_CONFIG:-}" ]]; then
    CONFIG="$INGLENOOK_CONFIG"
elif [[ -f /etc/inglenook/gate.yaml ]]; then
    CONFIG=/etc/inglenook/gate.yaml
else
    CONFIG="${INGLENOOK_HOME:-$HOME/dev/inglenook}/deploy/gate.yaml"
fi
if [[ -z "${PYTHONPATH:-}" && -d "${INGLENOOK_HOME:-$HOME/dev/inglenook}/src" ]]; then
    export PYTHONPATH="${INGLENOOK_HOME:-$HOME/dev/inglenook}/src"
fi

python3 -m inglenook --config "$CONFIG" ensure-free --backend "$BACKEND"

# llama-swap waits for this cmd to exit. Record the pid so cmdStop can
# reap the keepalive immediately instead of sitting on unloadTimeout.
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}/inglenook-keepalives"
mkdir -p "$RUNTIME_DIR"
echo $$ > "$RUNTIME_DIR/${BACKEND}.pid"

if [[ "$BACKEND" == "ls_comfyui" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    exec "$SCRIPT_DIR/comfy-keepalive.sh"
fi

if [[ "$BACKEND" == "tts-heavy" ]]; then
    if curl -fsS --max-time 2 http://127.0.0.1:8210/health >/dev/null 2>&1; then
        exec tail -f /dev/null
    fi
    VOICE_ENGINE_HOME="${VOICE_ENGINE_HOME:-$HOME/dev/voice-engine}"
    if [[ -x "$VOICE_ENGINE_HOME/scripts/serve.sh" ]]; then
        exec "$VOICE_ENGINE_HOME/scripts/serve.sh"
    fi
fi

exec tail -f /dev/null
