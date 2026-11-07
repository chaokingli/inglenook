# VRAM budget — RTX 5070 Ti (16303 MiB)

Measured 2026-08-20 while planning; live switch 2026-08-21 (see `deploy/live-switch-report.md`). Re-run `inglenook status` after each preset change.

| Role | What was running | used MiB | free MiB | `need_mb` in gate.yaml |
|------|-------------------|----------|----------|------------------------|
| System idle (approx) | nothing registered | ~18–800 | ~15500+ | idle_used_mb = 2500 |
| Chat 35B Q6_K (qwen35-code) | llama.cpp router on :8198 | 14730–15014 (live 14859–14977) | 868–1128 (live 905–1023) | 14500 + 400 headroom |
| Chat 27B Q4_K (qwen38-chat) | llama-server on :8198 | 14648 | 1234 | same chat slot |
| ComfyUI empty | process up, weights freed | ~390–484 | ~15398–15492 | used < idle_used_mb |
| Comfy SDXL (weights resident) | python on :8188 | **7108** (live, 512² / 2 step) | **8774** | residual occupancy |
| Comfy video (H3 / WAN) | almost full card | ~15000+ | exclusive | 14000 + 400 headroom |
| Heavy TTS (`tts-heavy`) | voice-engine / IndexTTS-2.5 | 2000–8000 (measure after first load) | coreside with `qwen35-voice` | 4000 |
| Chat voice (`qwen35-voice`) | 35B-A3B Q6 + `cpu-moe` + `fit-target=8192` + ctx 64k | measure on first warmup | coreside with TTS | 8000 |
| CPU Whisper / Kokoro | no GPU | 0 | n/a | always-cpu group |

`required_free_mb` must stay below post-`/api/free` free (~15398) and empty-card free (~15492). 14600+800 blocked admission by 2 MiB.

Live gate timings (2026-08-21): `ensure-free ls_comfyui` with 35B resident **585–639 ms** (14977 → 390 MiB); `ensure-free qwen38-chat` with SDXL resident **1257 ms** (7108 → 484 MiB). llama-swap exclusive-group swap still waited the full `unloadTimeout` (180 s) because keepalive `tail` was not reaped — that is a process bug, not a budget miss.

## Policy

- One member of `gpu-exclusive` at a time.
- Generation (`POST /prompt`) waits for in-flight chat (prompt expansion), then unloads chat.
- Chat queues while Comfy `queue_remaining > 0`. It does not SIGTERM a running video.
- Unknown used > 4 GiB with no registered backend: log a warning (Ollama/browser). Do not auto-kill.

## Recalibrate

```bash
inglenook --config deploy/gate.yaml status
nvidia-smi --query-gpu=memory.total,memory.used,memory.free --format=csv
nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv
```
