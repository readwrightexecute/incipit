# Incipit

*"here begins"* — a BMAD-style **mega-prompt wizard**. It takes a rough software
idea through a compressed elicitation flow and assembles one structured spec (a
"mega-prompt") you paste into a coding agent. Instead of hoping you remembered to
specify everything, Incipit interrogates the idea for you, QA's the result, and
helps you converge it before you ship it to the agent.

- **Bring your own model.** Talks to any OpenAI-compatible `/v1` endpoint —
  Ollama, LM Studio, llama.cpp `llama-server`, vLLM, or OpenAI itself.
- **UI:** FastAPI + HTMX, server-rendered, no build step. Set your endpoint and
  model from the in-app **⚙ Model settings** panel (or via env).
- **Tested with** `qwen3.6:35b` served over an OpenAI-compatible endpoint
  (llama-swap); any reasonably capable instruct model works.

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

Example endpoints (set the base URL in the settings panel):

| Runtime | Base URL | API key |
|---|---|---|
| Ollama | `http://localhost:11434/v1` | — |
| LM Studio | `http://localhost:1234/v1` | — |
| llama.cpp `llama-server` | `http://localhost:8080/v1` | — |
| llama-swap (tested: `qwen3.6:35b`) | `http://<host>:<port>/v1` | bearer |
| OpenAI | `https://api.openai.com/v1` | required |

Runtime endpoint changes are restricted to localhost, `api.openai.com`, and the
host from `INCIPIT_OPENAI_BASE_URL` by default. For another trusted host, set
`INCIPIT_ALLOWED_BASE_URL_HOSTS=host.example.com` before starting the app.

> **"Disable thinking" toggle:** local reasoning models (Qwen, etc.) can burn the
> whole token budget on a hidden think channel and return empty content. Turning
> this on sends `chat_template_kwargs.enable_thinking=false`. Leave it **off** for
> OpenAI and most hosted APIs — they reject the parameter.

## The flow

The wizard is fully async — each step kicks off a background generation and
streams progress over SSE while you keep interacting. The final mega-prompt is
assembled **deterministically** (string concat, no LLM call) and is downloadable
as Markdown.

1. **Brain dump** — describe what you want to build and why. Pick only whether
   it's a **new** project or an **existing** codebase (paste a repo link and
   Incipit folds the README + structure into drafting). The **form factor /
   platform is inferred from your idea**, not asked — so a stale dropdown choice
   can't contradict the spec.
2. **Clarify** — the model asks the handful of questions that actually matter,
   each with an `[ASSUMPTION]` default. Answer what you care about; blanks fall
   back to the assumption.
3. **Draft** — six spec sections are drafted sequentially (each sees the prior
   done sections):
   1. Goals & Background
   2. Functional Requirements
   3. Non-Functional Requirements
   4. Tech Constraints & Stack
   5. Acceptance Criteria
   6. Out of Scope

   Click any section to hand-edit it, or use the per-section **Refine** menu to
   have the model redo it (critique, identify risks, expand, simplify).
4. **🎉 Party review** *(optional)* — convene a BMAD-style round table of personas
   + a facilitator that debate the spec (or, at step 2, your clarifying
   questions) to consensus and propose changes you approve or deny.
5. **Finish** — copy or download the assembled mega-prompt.

> An automated QA / fix / verify pass is being reworked on the `qa-flow` branch
> and is intentionally not part of this flow right now.

**🌙 Shoot the Moon** runs the whole thing hands-off from just the idea: it
infers the platform and details, takes the generated assumptions as answers,
drafts the full spec, convenes the round table, and applies the consensus
automatically. You can still edit and refine afterward.

To change *what* the spec contains, edit `app/wizard/sections.yaml` (section list
+ order); the per-section refine menu is `app/wizard/elicitation.yaml`; prompt
wording lives in `app/wizard/prompts/*.md.j2`.

## Configuration

All config is environment variables (`INCIPIT_*`) — see [`.env.example`](.env.example).
A local `.env` is auto-loaded if present. Anything you save in the **⚙ Model
settings** panel is written to `.promptgen.json` (gitignored) and takes precedence
on the next run, so you configure your endpoint once.

The app has no login of its own — run it on localhost or a trusted network. The
optional **"Login with GitHub"** flow (see below) is a per-user OAuth grant used
only to read your private repos for grounding; it does not gate the app.

### Optional: Login with GitHub (private-repo grounding)

For existing-codebase specs you can sign in with GitHub so the wizard can read
your **private** repos. The user's access token is stored **server-side only**
(in-memory, `app/auth.py`); the browser cookie carries just a signed, opaque
session id (`HttpOnly` + `Secure` + `SameSite=Strict`). Configure the OAuth app:

| Env var | What |
|---|---|
| `INCIPIT_GITHUB_OAUTH_CLIENT_ID` | OAuth app client id (public; a registered default is built in) |
| `INCIPIT_GITHUB_OAUTH_CLIENT_SECRET` | OAuth app client secret — **secret**, set via env/Doppler, never commit |
| `INCIPIT_GITHUB_OAUTH_REDIRECT_URL` | Callback URL registered on the OAuth app (`…/auth/github/callback`) |
| `INCIPIT_GITHUB_OAUTH_SCOPES` | Requested scopes (default `repo`) |
| `INCIPIT_SESSION_COOKIE_SECRET` | Secret used to sign the session cookie (set it so cookies survive restarts) |
| `INCIPIT_COOKIE_SECURE` | Set the cookie `Secure` flag (default `true`; set `false` for local plain HTTP) |

Token issuance/revocation is recorded on the `promptgen.audit` logger (no
tokens are ever logged). Leave the client id/secret blank to disable the button.

There's no test suite or build step for the app itself. For a fast dev loop,
point it at any running endpoint and run `uvicorn` as above. The repo does ship
an offline `pytest` suite (`pip install -r requirements-dev.txt && pytest`).

---

## Advanced: DiffusionGemma backend (GPU)

Incipit was originally built around **DiffusionGemma 26B-A4B-it** run through
`llama-diffusion-cli` (llama.cpp PR #24423, which has no HTTP server yet — the
app drives a persistent `-cnv` subprocess over stdin/stdout). This path requires
building llama.cpp from a pinned PR and a GPU, and is selected with
`INCIPIT_BACKEND=diffusion-cnv` (or `diffusion-oneshot`). It is **not** needed
for the OpenAI-compatible path above.

```bash
# model (one-time, ~16G):
hf download unsloth/diffusiongemma-26B-A4B-it-GGUF diffusiongemma-26B-A4B-it-Q4_K_M.gguf \
  --local-dir /path/to/models/diffusiongemma-26B-A4B-it-GGUF

# build the image (compiles llama-diffusion-cli from the pinned PR; CUDA, sm_120):
podman build -t localhost/promptgen:v3 .
```

Backends (`INCIPIT_BACKEND`):

| Value | What |
|---|---|
| `openai` (default) | any OpenAI-compatible endpoint |
| `diffusion-cnv` | persistent `llama-diffusion-cli -cnv` subprocess |
| `diffusion-oneshot` | one CLI process per call (model reload each call) |

See `docs/multi-gpu-diffusiongemma.md` for the multi-GPU writeup, and the
`Containerfile` header / `patches/` for the pinned-PR build and carried patches.
The diffusion CLI protocol the `-cnv` backend depends on (turn marker, one line
per turn, `/clear` between calls) is documented in `app/llm/diffusion_cnv.py`;
re-pin the PR SHA deliberately.
