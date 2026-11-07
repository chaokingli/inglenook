# Runbook

## Happy path

1. llama-swap listens on `:9292`.
2. Split proxy listens on `:9293`.
3. ComfyUI listens on `127.0.0.1:8188` only.
4. OpenWebUI (NAS Docker) and SillyTavern use:
   - chat: `http://<GPU-LAN-IP>:9292/v1` model **`qwen35-voice`** (default). Do not use `qwen38-chat`.
   - TTS: same `/v1/audio/speech` model `tts-heavy` (alias **`index-tts2`** for st-indextts). Voice list/upload: `GET|POST /api/v1/voices` (rewritten to tts-heavy). Stays loaded with `qwen35-voice`; only Comfy unloads both.
   - image/video: `http://<GPU-LAN-IP>:9293`
   - workflow library: `http://<GPU-LAN-IP>:9293/inglenook/workflows`
5. One-click: `~/start-inglenook.sh` (voice stack) or `~/start-inglenook.sh start --full`.
6. Never put `127.0.0.1` in NAS OpenWebUI — that is the NAS.
7. Do not select `qwen35-code` while TTS is resident; that GGUF switch skips ensure-free and can OOM.

NAS Compose (`compose.yaml`) runs llama-swap + inglenook on the NAS and talks to the GPU over `COMFYUI_URL` / `LLAMA_CPP_URL`. Frontends then use `http://<NAS-IP>:9292/v1` and `http://<NAS-IP>:9293`.

## Failures

| Symptom | Likely cause | What to do |
|---------|--------------|------------|
| Unload timeout | `/free` returned but CUDA context still holds VRAM | wait; `inglenook status`; last resort restart Comfy user service |
| Swap hangs ~180s then works | `cmd` keepalive is `tail -f /dev/null`; `cmdStop` frees VRAM but does not reap it; llama-swap waits `unloadTimeout` | VRAM is already free — wait or restart `llama-swap.service`; fix is `swap-stop.sh` / pid kill (see `deploy/live-switch-report.md`) |
| `comfyui_auto not found` | GPU `llama-swap.yaml` missing `ls_comfyui` alias `comfyui`; Docker yaml already has it | add the alias and reload llama-swap; do not use `GET /ls_comfyui/…` (404) — `/upstream/ls_comfyui/…` or `/comfyui/…` after the alias |
| Chat loaded 27B instead of 35B | old clients still send `qwen38-chat` | use **`qwen35-voice`**; that id is gone from llama-swap |
| Chat 503 / queued | video still running | wait; ST disconnect already sends `/interrupt` |
| 27B reload 10–30s | expected | `sendLoadingState: true` |
| Video cut at ~60s | proxy/tool timeout | `:9293` `proxy_read_timeout` 900s; OWUI tool 10–15 min |
| ST Connect unloads 27B | `/object_info` went through llama-swap | fix split proxy; only POST /prompt may hit `/comfyui/` |
| NAS cannot reach models | OWUI pointed at NAS localhost | GPU LAN IP on `:9292` / `:9293` |
| OOM with "nothing loaded" | Ollama or a browser tab on the GPU | `systemctl --user stop ollama`; close local UIs |
| llama-swap never swaps back to 27B | Comfy web UI WebSocket counted as in-flight | do not leave Comfy web open; `ignoreWebsockets: true`; WS stays on :8188 |
| `:9293` connection refused | split proxy not installed (no Caddy/nginx) | install `comfy-split-caddy.service`; bind Comfy to `127.0.0.1` |

## Rollback

Keep `~/start-llama.sh` on `:8198`. llama-swap on `:9292` proxies that router; it must not start a second llama-server. Point frontends back at `:8198` only if llama-swap is down. Do not run Ollama and llama.cpp at the same time.

Occupancy is `weights` (`GET /models` status). Comfy down is idle, not busy. `POST /models/unload` requires `{"model":"<id>"}`. llama-swap `GET /running` is not occupancy — it only means the keepalive `cmd` is alive.

Live GPU-machine results and change list: `deploy/live-switch-report.md`.

## Workflows

API workflows (no LLM nodes) live in `workflows/api/`. Export from Comfy **Save (API Format)**. Do not POST the hand-tuned graph that contains an LLM node — that deadlocks the exclusive group.
