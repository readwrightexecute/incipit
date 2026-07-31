# Incipit web app

A local FastAPI + HTMX wizard that walks a rough software idea through the Incipit
elicitation flow against your own model endpoint, and assembles a structured
Implementation Brief you can download as Markdown.

This is a self-contained implementation of the flow. If you just want the flow
inside your coding agent, use the skills in [`../skills/`](../skills/) instead —
they need no server and no model endpoint.

- **Bring your own model.** Talks to any OpenAI-compatible `/v1` endpoint —
  Ollama, LM Studio, llama.cpp `llama-server`, vLLM, or OpenAI itself.
- **UI:** FastAPI + HTMX, server-rendered, no build step. Set your endpoint and
  model from the in-app **⚙ Model settings** panel (or via env).
- **Tested with** `qwen3.6:35b` served over an OpenAI-compatible endpoint
  (llama-swap); any reasonably capable instruct model works.

## Quickstart

Run everything from this directory.

```bash
cd webapp
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8911
```

Open <http://localhost:8911>, click **⚙ Model settings**, set your endpoint and
model, then start dumping your idea. Defaults assume a local **Ollama** at
`http://localhost:11434/v1` — click **Test / list models** in the panel to pull
the list of models your endpoint exposes.

Example endpoints (set the base URL in the settings panel):

| Runtime | Base URL | API key |
|---|---|---|
| Ollama | `http://localhost:11434/v1` | — |
| LM Studio | `http://localhost:1234/v1` | — |
| llama.cpp `llama-server` | `http://localhost:8080/v1` | — |
| llama-swap (tested: `qwen3.6:35b`) | `http://<host>:<port>/v1` | bearer |
| OpenAI | `https://api.openai.com/v1` | required |

Runtime endpoint changes are restricted to localhost, `api.openai.com`, and the
host from `PROMPTGEN_OPENAI_BASE_URL` by default. For another trusted host, set
`PROMPTGEN_ALLOWED_BASE_URL_HOSTS=host.example.com` before starting the app.

> **Reasoning effort:** local reasoning models (Qwen, etc.) can burn the whole
> token budget on a hidden think channel and return empty content. Setting the
> effort to **Off** sends `reasoning_effort: "none"` (plus
> `chat_template_kwargs.enable_thinking=false` for llama.cpp). Leave it on
> **Default** for OpenAI and most hosted APIs — they reject the parameter.

## The flow

The wizard is fully async — each step kicks off a background generation and
streams progress over SSE while you keep interacting. The final brief is assembled
**deterministically** (string concat, no LLM call) and is downloadable as Markdown.

1. **Brain dump** — describe what you want to build and why. Pick only whether
   it's a **new** project or an **existing** codebase (paste a repo link and
   Incipit folds the README + structure into drafting). The **form factor /
   platform is inferred from your idea**, not asked — so a stale dropdown choice
   can't contradict the spec.
2. **Clarify** — the model asks the handful of questions that actually matter,
   each with an `[ASSUMPTION]` default. Answer what you care about; blanks fall
   back to the assumption.
3. **Draft** — six spec sections are drafted sequentially, each seeing the prior
   done sections: Goals & Background, Functional Requirements, Non-Functional
   Requirements, Tech Constraints & Stack, Acceptance Criteria, Out of Scope.
   Click any section to hand-edit it, or use the per-section **Refine** menu to
   have the model redo it (critique, identify risks, expand, simplify).
4. **🎉 Party review** *(optional)* — convene a round table of personas plus a
   facilitator that debate the spec (or, at step 2, your clarifying questions) to
   consensus and propose changes you approve or deny.
5. **Finish** — copy or download the assembled brief.

**🌙 Shoot the Moon** runs the whole thing hands-off from just the idea: it infers
the platform and details, takes the generated assumptions as answers, drafts the
full spec, convenes the round table, and applies the consensus automatically. You
can still edit and refine afterward.

To change what the spec contains **in this app**, edit `app/wizard/sections.yaml`
(section list + order); the per-section refine menu is
`app/wizard/elicitation.yaml`; prompt wording lives in
`app/wizard/prompts/*.md.j2`. These are the app's own copies, deliberately forked
from the skills — a change to the *flow itself* belongs in `../skills/src/`.

## Configuration

All config is environment variables (`PROMPTGEN_*`) — see [`.env.example`](.env.example).
A local `.env` is auto-loaded if present. Anything you save in the **⚙ Model
settings** panel is written to `.promptgen.json` (gitignored) and takes precedence
on the next run, so you configure your endpoint once.

There is **no authentication** — run it on localhost or a trusted network only.

## Tests

Offline: no network, no LLM, no subprocess.

```bash
pip install -r requirements-dev.txt
pytest
```

There is no build step or linter. For a fast dev loop, point the app at any
running endpoint and run `uvicorn` as above.

## Advanced: DiffusionGemma backend (GPU)

Incipit was originally built around **DiffusionGemma 26B-A4B-it** run through
`llama-diffusion-cli` (llama.cpp PR #24423, which has no HTTP server yet — the
app drives a persistent `-cnv` subprocess over stdin/stdout). This path requires
building llama.cpp from a pinned PR and a GPU, and is selected with
`PROMPTGEN_BACKEND=diffusion-cnv` (or `diffusion-oneshot`). It is **not** needed
for the OpenAI-compatible path above.

```bash
# model (one-time, ~16G):
hf download unsloth/diffusiongemma-26B-A4B-it-GGUF diffusiongemma-26B-A4B-it-Q4_K_M.gguf \
  --local-dir /path/to/models/diffusiongemma-26B-A4B-it-GGUF

# build the image from this directory (compiles llama-diffusion-cli from the
# pinned PR; CUDA, sm_120):
podman build -t localhost/promptgen:v3 .
```

Backends (`PROMPTGEN_BACKEND`):

| Value | What |
|---|---|
| `openai` (default) | any OpenAI-compatible endpoint |
| `diffusion-cnv` | persistent `llama-diffusion-cli -cnv` subprocess |
| `diffusion-oneshot` | one CLI process per call (model reload each call) |

See [`docs/multi-gpu-diffusiongemma.md`](docs/multi-gpu-diffusiongemma.md) for the
multi-GPU writeup, and the `Containerfile` header and `patches/` for the pinned-PR
build and carried patches. The diffusion CLI protocol the `-cnv` backend depends
on (turn marker, one line per turn, `/clear` between calls) is documented in
`app/llm/diffusion_cnv.py`; re-pin the PR SHA deliberately.
