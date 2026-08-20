# API workflows

Put Comfy **API Format** JSON here. These files are what OpenWebUI and SillyTavern POST to `/prompt`.

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
