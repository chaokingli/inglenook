# API workflows

Put Comfy **API Format** JSON here. These files are templates for OpenWebUI and SillyTavern to POST to `/prompt`.

Drop files into:

| Directory | Use |
|-----------|-----|
| `image/` | txt2img / i2i |
| `video/` | t2v / i2v |
| `incoming/` | scratch; move into image/ or video/ after checking |

Upload over the LAN (split proxy → gate):

```bash
curl -sS http://<GPU-LAN-IP>:9293/inglenook/workflows \
  -H 'Content-Type: application/json' \
  -d '{"kind":"image","name":"my-t2i","workflow":{ ... API JSON ... }}'
curl -sS http://<GPU-LAN-IP>:9293/inglenook/workflows
```

Localhost: `http://127.0.0.1:9300/v1/workflows`. Graphs must not contain LLM / llama nodes.

| File | Used by |
|------|---------|
| `image.json` | OpenWebUI Images (txt2img) |
| `image-edit.json` | OpenWebUI image edit |
| `video-t2v.json` | OpenWebUI video Tool + SillyTavern |
| `video-i2v.json` | optional img2vid |

Rules:

- No LLM / llama nodes on these graphs. Prompt expansion happens in OWUI/ST against `:9292/v1` *before* `/prompt`.
- SillyTavern copies should replace injectable fields with `%prompt%`, `%negative_prompt%`, `%seed%`, and so on.
- Video graphs must write an output Comfy records as `images` or `gifs` (VHS / SaveVideo) so the file lands in chat.

The hand-tuned graphs with LLM rewrite stay in the Comfy web UI for local debugging only.
