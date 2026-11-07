# inglenook

Thin VRAM gate on top of [llama-swap](https://github.com/mostlygeek/llama-swap): exclusive swap groups, unload confirmation, and turn-taking for local chat, image, and video on a 16GB card.

This is **not** another OpenAI gateway. llama-swap owns process lifecycle. Inglenook only answers: *is there enough free VRAM, and if not, who may be unloaded?*

## Layout

```
src/inglenook/     VRAM gate (ensure_free)
deploy/            llama-swap.yaml, split proxy, systemd, budget table, live-switch report
deploy/docker/     NAS compose configs (env-driven upstreams)
docker/            container entrypoint and llama-swap installer
compose.yaml       NAS Docker Compose
workflows/api/     Comfy API-format JSON (no LLM nodes)
tests/             pytest
```

## Ports

| Port | Process | Who talks to it |
|------|---------|-----------------|
| 9292 | llama-swap | OpenWebUI / SillyTavern chat and audio (`/v1`) |
| 9293 | split reverse proxy | OWUI Images + video Tool, ST ComfyUI extension |
| 8188 | ComfyUI on `127.0.0.1` | only the split proxy and llama-swap |
| 8198 | existing llama.cpp router | llama-swap proxies this; do not start a second server |
| 9300 | optional gate sidecar | localhost status |
| 8210 | voice-engine TTS (`tts-heavy`) | llama-swap `/v1/audio/speech`; default stack coresides with `qwen35-voice` |
| 9293 `/inglenook/workflows` | API-format Comfy JSON library | drop files or POST `{kind,name,workflow}` |

OpenWebUI runs in **NAS Docker**. Its `127.0.0.1` is the NAS. Always use the GPU machine LAN IP.

## One-click (GPU machine)

Default is the tested **voice-stack**: `qwen35-voice` + IndexTTS (`tts-heavy`) stay loaded together. Comfy `POST /prompt` unloads both.

```bash
~/start-inglenook.sh           # start / refresh the stack
~/start-inglenook.sh start -f  # start, then follow live logs
~/start-inglenook.sh logs      # follow logs of an already-running stack
~/start-inglenook.sh status
~/start-inglenook.sh stop      # keep llama-swap.service
~/start-inglenook.sh start --full   # 35B fills the card, no TTS
```

SillyTavern: `http://<GPU-LAN-IP>:9292/v1` chat model **`qwen35-voice`**, TTS **`tts-heavy`**. Images/video: `:9293`.

## Policy

- `voice-stack`: `qwen35-voice` and `tts-heavy` stay loaded together.
- `gpu-exclusive`: Comfy image/video unloads the voice-stack.
- Chat **queues** while Comfy is busy. It does not kill a running video.
- ST **Connect** (`GET /system_stats`, `/object_info`) must not swap. Only POST `/prompt` goes through llama-swap.

## Install (GPU machine)

```bash
cd ~/dev/inglenook
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest --cov=inglenook
```

Download [llama-swap](https://github.com/mostlygeek/llama-swap/releases) into `~/.local/bin`. Local llama-swap **proxies** `http://127.0.0.1:8198` and Comfy on `:8188`. It does not start another `llama-server` and does not need GGUF paths.

Optional loopback URL overrides (defaults are already `:8198` / `:8188`):

```bash
mkdir -p ~/.config/inglenook
cp deploy/env.example ~/.config/inglenook/env
chmod 600 ~/.config/inglenook/env
```

Starting llama-swap on `:9292` does not unload the current router model. Unload happens only on exclusive swap (`ensure-free` / `llama-unload.sh`). Keep `~/start-llama.sh` on `:8198` running. Extra chat names for other setups can still be generated with `python3 -m inglenook convert-ini --ini ~/models-adapted.ini` (that output spawns servers — do not merge it onto this machine's `:8198` router).

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

- Chat / audio: `http://<GPU-LAN-IP>:9292/v1` (or the NAS IP when using Compose)
- Image / video: `http://<GPU-LAN-IP>:9293` (or the NAS IP when using Compose)
- Timeouts for video: 10–15 minutes on the split proxy, OWUI tool, and llama-swap `timeouts.responseHeader`

See `deploy/runbook.md`, `deploy/vram-budget.md`, and the 2026-08-21 GPU live switch write-up `deploy/live-switch-report.md`.

## NAS Docker

The published image is `ghcr.io/chaokingli/inglenook`. Each build installs the current [llama-swap](https://github.com/mostlygeek/llama-swap/releases) release and this project. ComfyUI and llama.cpp stay on the GPU server; the container talks to them over the LAN.

```bash
cp .env.example .env
# set COMFYUI_URL and LLAMA_CPP_URL to the GPU machine, not 127.0.0.1
docker compose pull
docker compose up -d
```

Synology Container Manager can use `docker-compose.yml` (same contents as `compose.yaml`).

| Variable | Meaning |
|----------|---------|
| `COMFYUI_URL` | ComfyUI origin, e.g. `http://192.168.1.10:8188` |
| `LLAMA_CPP_URL` | llama.cpp / llama-server origin, e.g. `http://192.168.1.10:8198` |
| `INGLENOOK_VERSION` | Image tag (`latest` or a release such as `0.1.1`) |
| `INGLENOOK_VRAM_SOURCE` | `comfy` (NAS default, Comfy `/system_stats`), `auto`, or `nvidia-smi` |

Local systemd and Docker both use `policy.occupancy: weights`: llama.cpp `GET /models` `status.value` (`loaded`/`loading` vs `sleeping`/`unloaded`), or single-server `GET /props` `is_sleeping`. `/health` is not used to decide who owns VRAM. Unload sends `POST /models/unload` with `{"model": "<id>"}` for each loaded id.

Frontend URLs on the NAS:

- Chat / audio: `http://<NAS-IP>:9292/v1`
- Image / video: `http://<NAS-IP>:9293`

To build locally instead of pulling GHCR:

```bash
docker build -t ghcr.io/chaokingli/inglenook:local --build-arg LLAMA_SWAP_VERSION=latest .
INGLENOOK_IMAGE=ghcr.io/chaokingli/inglenook INGLENOOK_VERSION=local INGLENOOK_PULL_POLICY=never docker compose up -d
```

`LLAMA_CPP_URL` and `COMFYUI_URL` must be origins (`http://host:port`), not `/v1` paths. After a swap, llama.cpp must accept the next chat request (reload on demand). Comfy stays up and is unloaded with `/api/free`.

Private GHCR pulls need `docker login ghcr.io`. First publish may create a private package; set it public in GitHub Packages if the NAS should pull without a token. Releases and images are published by `.github/workflows/package.yml`, which bumps the version on each merge to `main`.
