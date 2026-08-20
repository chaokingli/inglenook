# inglenook

Thin VRAM gate on top of [llama-swap](https://github.com/mostlygeek/llama-swap): exclusive swap groups, unload confirmation, and turn-taking for local chat, image, and video on a 16GB card.

This is **not** another OpenAI gateway. llama-swap owns process lifecycle. Inglenook only answers: *is there enough free VRAM, and if not, who may be unloaded?*

## Layout

```
src/inglenook/     VRAM gate (ensure_free)
deploy/            llama-swap.yaml, split proxy, systemd, budget table
workflows/api/     Comfy API-format JSON (no LLM nodes)
tests/             pytest
```

## Ports

| Port | Process | Who talks to it |
|------|---------|-----------------|
| 9292 | llama-swap | OpenWebUI / SillyTavern chat and audio (`/v1`) |
| 9293 | split reverse proxy | OWUI Images + video Tool, ST ComfyUI extension |
| 8188 | ComfyUI on `127.0.0.1` | only the split proxy and llama-swap |
| 8198 | existing llama.cpp router | rollback only; frontends should stop using it |
| 9300 | optional gate sidecar | localhost status |

OpenWebUI runs in **NAS Docker**. Its `127.0.0.1` is the NAS. Always use the GPU machine LAN IP.

## Policy

- `gpu-exclusive`: chat 27B, Comfy image/video, heavy TTS — one at a time.
- A `POST /prompt` waits for in-flight chat (prompt expansion), then unloads the LLM.
- Chat **queues** while Comfy is busy. It does not kill a running video.
- ST **Connect** (`GET /system_stats`, `/object_info`) must not swap. Only POST `/prompt` (and upload/interrupt) goes through llama-swap `/comfyui/`.

## Install (GPU machine)

```bash
cd ~/dev/inglenook
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest --cov=inglenook
```

Download [llama-swap](https://github.com/mostlygeek/llama-swap/releases) into `~/.local/bin`. Extra chat models can be generated from the existing llama.cpp INI:

```bash
python3 -m inglenook convert-ini --ini ~/models-adapted.ini
```

Point llama-swap at the GGUF files via environment variables (see `deploy/env.example`). The process will refuse to start if any of them are unset.

```bash
mkdir -p ~/.config/inglenook
cp deploy/env.example ~/.config/inglenook/env
chmod 600 ~/.config/inglenook/env
# edit ~/.config/inglenook/env with local GGUF paths
```

Do not start llama-swap on top of a busy 27B session until you are ready to move frontends off `:8198`.

```bash
# optional user services
mkdir -p ~/.config/systemd/user
cp deploy/systemd/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

Manual check, without taking the current card:

```bash
PYTHONPATH=src python3 -m inglenook --config deploy/gate.yaml status
```

## Frontend URLs

- Chat / audio: `http://<GPU-LAN-IP>:9292/v1`
- Image / video: `http://<GPU-LAN-IP>:9293`
- Timeouts for video: 10–15 minutes on the split proxy, OWUI tool, and llama-swap `timeouts.responseHeader`

See `deploy/runbook.md` and `deploy/vram-budget.md`.
