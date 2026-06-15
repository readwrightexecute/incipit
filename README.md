# Incipit

*"here begins"* — a BMAD-style **mega-prompt wizard**. Takes a rough idea through a compressed
elicitation flow (brain dump → stakes/form-factor calibration → one batch of
clarifying questions with `[ASSUMPTION]` defaults → six drafted spec sections
with per-section refinement) and assembles a single structured "mega-prompt" you
paste into a coding agent.

- **Bring your own model.** Talks to any OpenAI-compatible `/v1` endpoint —
  Ollama, LM Studio, llama.cpp `llama-server`, vLLM, or OpenAI itself.
- UI: FastAPI + HTMX, server-rendered, no build step. Set your endpoint and
  model from the in-app **⚙ Model settings** panel (or via env).

## Quickstart (bring your own model)

```bash
git clone <this-repo> promptgen && cd promptgen
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8911
```

Open <http://localhost:8911>, click **⚙ Model settings**, set your endpoint and
model, then start dumping your idea. Defaults assume a local **Ollama** at
`http://localhost:11434/v1` — click **Test / list models** in the panel to pull
the list of models your endpoint exposes.

Examples of endpoints (set base URL in the settings panel):

| Runtime | Base URL | API key |
|---|---|---|
| Ollama | `http://localhost:11434/v1` | — |
| LM Studio | `http://localhost:1234/v1` | — |
| llama.cpp `llama-server` | `http://localhost:8080/v1` | — |
| OpenAI | `https://api.openai.com/v1` | required |

> **"Disable thinking" toggle:** local reasoning models (Qwen, etc.) can burn
> the whole token budget on a hidden think channel and return empty content.
> Turning this on sends `chat_template_kwargs.enable_thinking=false`. Leave it
> **off** for OpenAI and most hosted APIs — they reject the parameter.

## Configuration

All config is environment variables (`PROMPTGEN_*`) — see [`.env.example`](.env.example).
A local `.env` is auto-loaded if present. Anything you save in the **⚙ Model
settings** panel is written to `.promptgen.json` (gitignored) and takes
precedence on the next run, so you only configure your endpoint once.

There is **no authentication** — run it on localhost or a trusted network only.

## How it works

The wizard is fully async: each step kicks off a background generation and
streams progress over SSE while you keep interacting. The final mega-prompt is
assembled deterministically (no LLM call) and downloadable as Markdown. Section
structure lives in `app/wizard/sections.yaml`; the per-section refinement menu in
`app/wizard/elicitation.yaml`; prompt wording in `app/wizard/prompts/*.md.j2`.

There is no test suite or build step for the app itself. For a fast dev loop,
point it at any running endpoint and run `uvicorn` as above.

---

## Advanced: DiffusionGemma backend (GPU)

promptgen was originally built around **DiffusionGemma 26B-A4B-it** run through
`llama-diffusion-cli` (llama.cpp PR #24423, which has no HTTP server yet — the
app drives a persistent `-cnv` subprocess over stdin/stdout). This path requires
building llama.cpp from a pinned PR and a GPU, and is selected with
`PROMPTGEN_BACKEND=diffusion-cnv` (or `diffusion-oneshot`). It is **not** needed
for the OpenAI-compatible path above.

```bash
# model (one-time, ~16G):
hf download unsloth/diffusiongemma-26B-A4B-it-GGUF diffusiongemma-26B-A4B-it-Q4_K_M.gguf \
  --local-dir /path/to/models/diffusiongemma-26B-A4B-it-GGUF

# build the image (compiles llama-diffusion-cli from the pinned PR; CUDA, sm_120):
podman build -t localhost/promptgen:v3 .
```

Backends (`PROMPTGEN_BACKEND`):

| Value | What |
|---|---|
| `openai` (default) | any OpenAI-compatible endpoint |
| `diffusion-cnv` | persistent `llama-diffusion-cli -cnv` subprocess |
| `diffusion-oneshot` | one CLI process per call (model reload each call) |

See `docs/multi-gpu-diffusiongemma.md` for the multi-GPU writeup, and the
`Containerfile` header / `patches/` for the pinned-PR build and carried patches.
The diffusion CLI protocol the `-cnv` backend depends on (turn marker, one line
per turn, `/clear` between calls) is documented in
`app/llm/diffusion_cnv.py`; re-pin the PR SHA deliberately.
