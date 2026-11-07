#!/usr/bin/env bash
# llama-swap v250 execs cmdStop tokens directly (no shell). Keep this as argv0.
# Free VRAM, then reap the keepalive pid so exclusive swap is not unloadTimeout.
set -euo pipefail

BACKEND="${1:?backend name}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}/inglenook-keepalives"
PIDFILE="$RUNTIME_DIR/${BACKEND}.pid"

if [[ "$BACKEND" == "ls_comfyui" ]]; then
    "$SCRIPT_DIR/comfy-free.sh"
elif [[ "$BACKEND" == "tts-heavy" ]]; then
    VOICE_ENGINE_HOME="${VOICE_ENGINE_HOME:-$HOME/dev/voice-engine}"
    if [[ -x "$VOICE_ENGINE_HOME/scripts/stop.sh" ]]; then
        "$VOICE_ENGINE_HOME/scripts/stop.sh" || true
    fi
else
    "$SCRIPT_DIR/llama-unload.sh"
fi

if [[ -f "$PIDFILE" ]]; then
    pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    rm -f "$PIDFILE"
    if [[ -n "${pid}" ]] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        for _ in 1 2 3 4 5; do
            kill -0 "$pid" 2>/dev/null || exit 0
            sleep 0.2
        done
        kill -9 "$pid" 2>/dev/null || true
    fi
fi
