# VRAM budget — RTX 5070 Ti (16303 MiB)

Measured 2026-08-20 while planning. Re-run `inglenook status` after each preset change.

| Role | What was running | used MiB | free MiB | `need_mb` in gate.yaml |
|------|-------------------|----------|----------|------------------------|
| System idle (approx) | nothing registered | ~800 | ~15500 | idle_used_mb = 2500 |
| Chat 27B Q4_K (qwen38-chat) | llama-server on :8198 | 14648 | 1234 | 14600 + 800 headroom |
| Chat 27B longer ctx (novel/code) | same weights, larger KV | 14800–15000 (est.) | <1500 | 14800–15000 |
| ComfyUI empty | process up, weights freed | wait until used < 2500 | — | /free then poll |
| Comfy video (H3 / WAN) | almost full card | ~15000+ | exclusive | 15000 |
| Heavy TTS (future) | Chatterbox / IndexTTS | 2000–8000 | exclusive | 4000 |
| CPU Whisper / Kokoro | no GPU | 0 | n/a | always-cpu group |

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
