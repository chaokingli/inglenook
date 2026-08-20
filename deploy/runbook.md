# Runbook

## Happy path

1. llama-swap listens on `:9292`.
2. Split proxy listens on `:9293`.
3. ComfyUI listens on `127.0.0.1:8188` only.
4. OpenWebUI (NAS Docker) and SillyTavern use:
   - chat/audio: `http://<GPU-LAN-IP>:9292/v1`
   - image/video: `http://<GPU-LAN-IP>:9293`
5. Never put `127.0.0.1` in NAS OpenWebUI — that is the NAS.

NAS Compose (`compose.yaml`) runs llama-swap + inglenook on the NAS and talks to the GPU over `COMFYUI_URL` / `LLAMA_CPP_URL`. Frontends then use `http://<NAS-IP>:9292/v1` and `http://<NAS-IP>:9293`.

## Failures

| Symptom | Likely cause | What to do |
|---------|--------------|------------|
| Unload timeout | `/free` returned but CUDA context still holds VRAM | wait; `inglenook status`; last resort restart Comfy user service |
| Chat 503 / queued | video still running | wait; ST disconnect already sends `/interrupt` |
| 27B reload 10–30s | expected | `sendLoadingState: true` |
| Video cut at ~60s | proxy/tool timeout | `:9293` `proxy_read_timeout` 900s; OWUI tool 10–15 min |
| ST Connect unloads 27B | `/object_info` went through llama-swap | fix split proxy; only POST /prompt may hit `/comfyui/` |
| NAS cannot reach models | OWUI pointed at NAS localhost | GPU LAN IP on `:9292` / `:9293` |
| OOM with "nothing loaded" | Ollama or a browser tab on the GPU | `systemctl --user stop ollama`; close local UIs |
| llama-swap never swaps back to 27B | Comfy web UI WebSocket counted as in-flight | do not leave Comfy web open; `ignoreWebsockets: true`; WS stays on :8188 |

## Rollback

Keep `~/start-llama.sh` on `:8198`. Point frontends back there only if llama-swap is down. Do not run Ollama and llama.cpp at the same time.

## Workflows

API workflows (no LLM nodes) live in `workflows/api/`. Export from Comfy **Save (API Format)**. Do not POST the hand-tuned graph that contains an LLM node — that deadlocks the exclusive group.
