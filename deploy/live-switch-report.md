# Live switch report — GPU machine

Measured 2026-08-21 on Celili-PC-Tower. Card: RTX 5070 Ti, 16303 MiB. llama-swap **v250** (`~/.local/bin/llama-swap`). llama.cpp router on `:8198` (`--models-max 1`). ComfyUI 0.33.0 on `:8188`. Gate config: `deploy/gate.yaml`, occupancy `weights`.

This is not a unit-test log. It records what actually happened with 35B chat weights resident (~15 GiB) and with SDXL resident (~7 GiB).

Related: `deploy/vram-budget.md`, `deploy/runbook.md`.

## Setup under test

| Piece | State |
|-------|--------|
| `llama-swap.service` | enabled, `0.0.0.0:9292` |
| llama.cpp `:8198` | already running; llama-swap **proxies** it |
| ComfyUI | running (`python main.py … --listen 0.0.0.0`) |
| Split proxy `:9293` | **not installed** (no Caddy, no nginx) |
| `inglenook-gate.service` | not installed (CLI `ensure-free` used instead) |
| Ollama | running, cloud tags only; not on the GPU during these runs |

LAN IP of this machine: `192.168.178.119`. Chat path: `http://192.168.178.119:9292/v1`.

## What passed

### Unit / static

- `pytest --cov=inglenook`: all green, 87.65% (fail-under 80).
- `ruff check src tests scripts`: clean.
- `compose.yaml` renders with dummy `COMFYUI_URL` / `LLAMA_CPP_URL`.

### Chat proxy (no swap)

- `GET /health` → `OK`.
- `GET /running` shows `qwen38-chat` ready, proxy `http://127.0.0.1:8198`.
- `POST /v1/chat/completions` with alias `qwen35-code` → 200 in ~4.2–4.8 s when weights already mapped (or ~4.5 s including first load from empty).
- Occupancy `weights` maps the unregistered loaded id `qwen35-code` onto registered backend `qwen38-chat`.

### ST Connect must not swap

`GET http://127.0.0.1:8188/object_info` while 35B was loaded: still `qwen35-code=loaded`, used **14977 MiB**, llama-swap still `qwen38-chat` ready. Direct Comfy GET does not go through llama-swap. This is the intended Connect path.

### Gate `ensure-free` — high occupancy, both directions

VRAM decision and unload are correct and fast. llama-swap process state is **not** updated by a CLI `ensure-free` (it still shows the previous model `ready`).

| Step | Before | After | Wall time |
|------|--------|-------|-----------|
| `ensure-free ls_comfyui` with 35B resident | used 14865–14977, free 905–1017, occ=`qwen38-chat`, `qwen35-code` loaded | used **390–484**, free **15398–15492**, llama unloaded | **585–639 ms** (`unloaded: [qwen38-chat]`) |
| SDXL `sd_xl_base_1.0` 512² / 2 steps | Comfy idle ~390–484 | used **7108**, free **8774**, occ=`ls_comfyui` | ~6 s to resident |
| `ensure-free qwen38-chat` with SDXL resident | used 7108, occ=`ls_comfyui` | used **484**, free **15398**, `/api/free` dropped weights | **1257 ms** (`unloaded: [ls_comfyui]`) |

35B was admitted for unload with only ~900 MiB free. SDXL residual occupancy was attributed to `ls_comfyui` (not chat). Post-`/api/free` free (15398) still clears `required_free_mb` for chat.

Reload after a gate free: `POST /v1/chat/completions` model `qwen35-code` brought used back to **14859** in ~4.2 s.

### llama-swap exclusive group — swap happens, slowly

Trigger: `GET /upstream/ls_comfyui/system_stats` (this **does** start `ls_comfyui`; `GET /ls_comfyui/system_stats` is 404).

| Direction | VRAM effect | llama-swap | Client |
|-----------|-------------|------------|--------|
| 35B → Comfy | weights dropped 14977 → 390 **immediately** | `qwen38-chat` stop then `ls_comfyui` start; health on `:8188/system_stats` | request **timed out at 180 s**; server logged the same GET as 200 empty body in **3m0.099 s** |
| Comfy (SDXL just freed) → chat | `/api/free` already at used 484 while model still `stopping` | `ls_comfyui` stop then `qwen38-chat` start | chat POST **timed out at 180 s**; server 200 empty body in **3m0.092 s**; follow-up chat loaded 35B in 4.8 s |

The 180 s is `unloadTimeout` (global 180; `ls_comfyui` is 900). `cmd` is `swap-start.sh` which ends in `tail -f /dev/null` (or `comfy-keepalive.sh` → same). `cmdStop` only unloads weights (`llama-unload.sh` / `comfy-free.sh`) and does **not** reap that keepalive. llama-swap waits the full timeout, then SIGKILLs `tail`.

## Findings

### F1 — Exclusive swap latency is `unloadTimeout`, not gate (high)

**Symptom.** Frontends wait ~3 minutes to swap even though VRAM is already free in <1 s.

**Cause.** llama-swap v250 execs `cmd` without a shell. Keepalive is `tail -f /dev/null`. `cmdStop` is a separate script that does not kill that process. Stop waits `unloadTimeout` then force-kills.

**Impact.** OpenWebUI / SillyTavern image or chat after a swap look hung. Client timeouts (180 s) can return an empty 200 and a later retry actually talks to the new upstream.

### F2 — Local `ls_comfyui` has no `comfyui` alias (high for `:9293`)

Docker `deploy/docker/llama-swap.yaml` has `aliases: [comfyui]`. GPU `deploy/llama-swap.yaml` does not.

```text
GET /comfyui/system_stats
{"error":"local model comfyui_auto not found","src":"llama-swap"}
```

Caddy/nginx rewrite POST `/prompt` → `http://127.0.0.1:9292/comfyui/prompt`. llama-swap v250's `/comfyui/` endpoint looks up a model named `comfyui` / `comfyui_auto`, not `ls_comfyui`. Without the alias (and without `:9293`), the documented image/video path cannot trigger a swap.

Workaround that **does** swap: `GET /upstream/ls_comfyui/…`.

### F3 — Split proxy `:9293` not deployed (high for ST / OWUI images)

Caddy and nginx are absent. `comfy-split-caddy.service` is not installed. Image/video frontends cannot use the split path; hitting `:8188` bypasses exclusive swap, hitting `/comfyui/` on `:9292` hits F2.

### F4 — llama-swap model id collides with a llama.cpp preset (medium)

Canonical llama-swap id is `qwen38-chat`, which is also a real `:8198` preset (27B). `POST /v1/chat/completions` with `"model":"qwen38-chat"` makes the **router** load 27B, not keep 35B.

Aliases (`qwen35-code`, …) are forwarded to the same proxy **and** passed through as the llama.cpp model name, so they select the right preset. Frontends must use the alias that matches the desired GGUF, not the llama-swap member id.

### F5 — CLI `ensure-free` desyncs llama-swap `/running` (low)

After `ensure-free ls_comfyui` unloaded 35B, `/running` still listed `qwen38-chat` `ready` (the `tail` keepalive). Occupancy was empty. Harmless for VRAM; confusing for ops. Exclusive-group requests still go through llama-swap stop/start.

### F6 — `GET /unload` is not llama-swap’s unload API (low)

`GET http://127.0.0.1:9292/unload` is proxied to the **current upstream**. On llama.cpp that is `/unload`, which took **3m0 s** and dropped 35B. llama-swap’s own API is `POST /api/models/unload` (and `/api/models/unload/:id`).

### F7 — Comfy listens on `0.0.0.0:8188` (medium)

Runbook wants `127.0.0.1` so NAS/ST cannot skip `:9293`. Live process used `--listen 0.0.0.0`. Bypass remains possible until bind + split proxy are fixed.

### F8 — Not exercised in this session

- Comfy **busy** queue (`queue_remaining > 0`) vs chat wait / no SIGTERM of video.
- H3 / WAN video (~15 GiB) exclusive swap.
- In-flight chat preemption before `POST /prompt`.
- NAS Compose (`compose.yaml`) against this GPU over LAN (would collide on host `:9292` if started locally).
- `inglenook serve` on `:9300`.

## Conclusions

1. **The gate is doing its job.** `policy.occupancy: weights`, `POST /models/unload` with `{"model":"<id>"}`, and Comfy `/api/free` all work on this card. High occupancy is not a correctness problem: 35B at ~15 GiB used / ~1 GiB free unloads in ~0.6 s; SDXL at 7108 MiB frees in ~1.3 s.

2. **Perceived swap slowness is llama-swap process lifecycle**, not VRAM. Keepalive `tail` + `unloadTimeout` 180/900 s makes exclusive-group swaps take three minutes even after weights are gone.

3. **Chat via `:9292` is production-usable today** if clients request a real llama.cpp alias (`qwen35-code`, not `qwen38-chat`).

4. **Image/video via the documented `:9293` / `/comfyui/` path is not production-usable yet** on this machine: no split proxy, and local yaml missing the `comfyui` alias.

5. **Do not treat llama-swap `/running` as occupancy.** Occupancy is `GET :8198/models` status plus Comfy residual VRAM. `/running` only means “keepalive cmd is alive”.

## Recommended changes

Priority: P0 = blocks documented image/video swap; P1 = user-visible 3 min delay; P2 = footguns / hygiene.

### P0 — Make `/comfyui/` resolve

Add the same alias the Docker config already has:

```yaml
# deploy/llama-swap.yaml  (ls_comfyui)
aliases:
  - comfyui
```

Reload llama-swap. Confirm:

```bash
curl -sS http://127.0.0.1:9292/comfyui/system_stats
# Comfy JSON, not comfyui_auto 404
```

Extend `tests/unit/test_deploy_templates.py` so GPU and Docker yaml both require `comfyui` in `ls_comfyui.aliases`.

### P0 — Deploy the split proxy

Install Caddy (or nginx) and enable `deploy/systemd/comfy-split-caddy.service`. Bind Comfy to loopback only (`--listen 127.0.0.1`), matching `deploy/scripts/comfy-keepalive.sh` and the runbook.

Verify:

- `GET :9293/object_info` and `GET :9293/system_stats` stay on `:8188` (no swap, 35B stays loaded).
- `POST :9293/prompt` rewrites to llama-swap `/comfyui/prompt` and **does** exclusive-swap.

### P1 — Stop keepalive instead of waiting `unloadTimeout`

`cmdStop` must both free VRAM **and** exit the `cmd` process llama-swap is waiting on.

Preferred shape:

1. Keep `llama-unload.sh` / `comfy-free.sh` as the VRAM half.
2. After a successful free, signal the keepalive (`tail` / `comfy-keepalive.sh`) so llama-swap sees `cmd` exit in milliseconds.
3. Leave `ls_comfyui.unloadTimeout` large (900) only as a cap for `/api/free` while a video is draining — not as the happy-path wait.

Concrete options (pick one):

- **A.** `swap-start.sh` writes `$XDG_RUNTIME_DIR/inglenook-$BACKEND.pid`; `cmdStop` runs the unload script then `kill` that pid.
- **B.** Single `swap-stop.sh <backend>` used as `cmdStop` (no YAML `|` multiline shell). llama-swap v250 execs `cmd` tokens directly; keep `cmdStop` as one executable too, same as `cmd`.
- **C.** Drop `tail -f /dev/null` if llama-swap can treat an already-up proxy (`checkEndpoint` only) without a long-lived `cmd`. Only if v250 actually allows that — do not assume; verify.

Acceptance: exclusive `GET /upstream/ls_comfyui/system_stats` with 35B resident returns Comfy `system_stats` in **a few seconds**, not 180 s. Chat after SDXL `/api/free` similarly.

Optional: lower global `unloadTimeout` from 180 to ~30 once stop actually reaps the process, so a wedged `tail` cannot pin the group for three minutes.

### P1 — Do not collide with llama.cpp preset names

Either:

- Rename the llama-swap member to something that is **not** a preset (`llama-router`, `chat-slot`) and keep `qwen35-code` / `qwen38-chat` / … as aliases, **or**
- Set `useModelName` (llama-swap) so the upstream always receives a chosen preset, independent of the request `model` field.

Until then: document that OWUI/ST model dropdown must use the **preset alias**, not the swap member id. A request with `"model":"qwen38-chat"` loads 27B.

### P2 — Ops and docs

- Never use `GET /unload` on `:9292` for diagnostics; use `POST /api/models/unload` or `inglenook ensure-free`.
- `inglenook status` after every preset change (already in `vram-budget.md`).
- Copy `deploy/systemd/*.service` if `:9293` / `:9300` should come up on boot; today only `llama-swap.service` is installed.
- Comfy `--vram-headroom 4` was in the live command line; re-check `need_mb` if that flag stays — SDXL still measured 7108 used, so chat `required_free_mb` is still the tighter constraint.

### Suggested implement order

1. Alias `comfyui` + template test (minutes, unblocks `/comfyui/`).
2. `swap-stop.sh` / pid kill so exclusive swap matches gate speed (the 3 min bug).
3. Caddy `:9293` + Comfy loopback bind (closes bypass).
4. Rename swap member or `useModelName` (stops 27B/35B mixups).
5. Re-run this report’s sequence: 35B → `/comfyui/` POST prompt → SDXL → chat alias, with wall-clock < 15 s plus model reload.

## Re-run checklist

Do not take the card unless the operator asked for a live switch.

```bash
PYTHONPATH=src python3 -m inglenook --config deploy/gate.yaml status
curl -sS http://127.0.0.1:9292/health
curl -sS http://127.0.0.1:9292/running
curl -sS http://127.0.0.1:8198/models | python3 -c \
  'import json,sys; d=json.load(sys.stdin)
print([ (i.get("id"), (i.get("status") or {}).get("value"))
        for i in d.get("data") or []
        if str((i.get("status") or {}).get("value","")).lower() in {"loaded","loading"} ])'
# Gate only (unloads current exclusive occupant):
# PYTHONPATH=src python3 -m inglenook --config deploy/gate.yaml ensure-free --backend ls_comfyui
```

Live numbers to compare against: idle+Comfy process **390–484** used; 35B Q6 **14859–14977** used; SDXL resident **7108** used; post-`/api/free` **484 / 15398**.
