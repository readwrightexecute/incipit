# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A BMAD-style "mega-prompt" wizard: a FastAPI + HTMX web app that walks a rough
software idea through a compressed elicitation flow and assembles a single
structured spec ("mega-prompt") to paste into a coding agent.

**Default backend is `openai`** — any OpenAI-compatible `/v1` endpoint (Ollama,
LM Studio, llama-server, vLLM, OpenAI). Endpoint/model/key are runtime-settable
in the UI (⚙ Model settings) and persisted to `.promptgen.json`; see
`app/settings.py`. This is the public "bring your own model" path and runs on
vanilla Python with no GPU.

The **DiffusionGemma** backends (`diffusion-cnv` / `diffusion-oneshot`) are the
opt-in advanced path: a GGUF model run through `llama-diffusion-cli` (llama.cpp
PR #24423, no HTTP server — driven as a persistent `-cnv` subprocess). Used in
the homelab deploy (single pod, `aistack` namespace, NodePort 30090). No auth by
design — trusted LAN / localhost only.

## Run & develop

There is no test suite, linter, or build step for the Python app. The fast dev
loop avoids spawning the GPU model by pointing at an OpenAI-compatible endpoint:

```bash
PROMPTGEN_BACKEND=openai \
PROMPTGEN_OPENAI_BASE_URL=http://<llm-server>:<port>/v1 \
PROMPTGEN_OPENAI_API_KEY=<key> \
python3 -m uvicorn app.main:app --port 8911
```

All configuration is environment variables (`PROMPTGEN_*`) read in
`app/config.py` — there is no config file. Container CMD runs uvicorn on
`:8000`.

### Container build / deploy

`podman build` → `podman save` (oci-archive) → `sudo ctr -n k8s.io images
import` → `kubectl apply -f ~/homelab-gitops/apps/aistack/promptgen.yaml`
(`imagePullPolicy: Never`). See README for exact commands. The Containerfile
compiles `llama-diffusion-cli` from a **pinned** llama.cpp PR SHA (`PR_SHA`
build arg) for Blackwell (sm_120, `CMAKE_CUDA_ARCHITECTURES=120`) and applies
two carried patches (below). Re-pin the SHA deliberately; never build from the
moving PR head, and re-run the README smoke test after a bump.

## Architecture

Request/orchestration flow is fully async and event-driven:

- **`app/main.py`** — FastAPI routes. POST handlers mutate session state, kick
  off background work with `asyncio.create_task(flow.run_*)`, and immediately
  return an HTMX partial. They never block on the LLM. `/sessions/{sid}/events`
  is the SSE endpoint the browser subscribes to for progress.
- **`app/wizard/flow.py`** — the orchestration layer. Each `run_*` coroutine
  renders a Jinja prompt, calls `backend.generate(...)`, mutates the `Session`,
  and `publish()`es SSE events (`questions_ready`, `section_started`,
  `section_done`, `error`, …). The frontend swaps DOM partials in response.
  `assemble_final()` builds the mega-prompt deterministically (string concat,
  **no LLM call**).
- **`app/wizard/state.py`** — in-memory `Session`/`QA`/`Section` dataclasses and
  a module-level `_sessions` dict (TTL-swept). **Single replica, single user:**
  in-flight wizards are lost on pod restart by design. SSE uses **one queue per
  open connection** (`subscribers` list) — a shared queue would split events
  between stale and live tabs.
- **`app/llm/`** — backend abstraction behind the `LLMBackend` Protocol
  (`base.py`). `get_backend()` selects by `PROMPTGEN_BACKEND`. Everything above
  this boundary is backend-agnostic.

### Wizard phases

`idea → calibrate → clarify → sections → final` (the `Session.phase` field).
`GET /sessions/{sid}` re-renders the right step for that phase, so browser
refresh / shared links resume a session (handlers set `HX-Push-Url`).

- **clarify** — model emits `N. question` / `[ASSUMPTION] default` pairs;
  `flow.parse_questions()` parses them with a regex. Empty answers fall back to
  the assumption.
- **sections** — six spec sections defined declaratively in
  `app/wizard/sections.yaml` (order = draft + assembly order). Drafted
  sequentially, each prompt given the prior *done* sections as context.
- Per-section **refine** menu is `app/wizard/elicitation.yaml` (critique,
  identify-risks, expand, simplify). Refine pushes the old content onto
  `Section.history` and restores it on failure.

To change what the spec contains, edit the YAML — not the code. Prompt wording
lives in `app/wizard/prompts/*.md.j2`; the system prompt is loaded once at
import (`flow.SYSTEM`).

### Backends (`PROMPTGEN_BACKEND`)

- **`openai`** (default, `app/llm/openai_compat.py`) — any OpenAI-compatible
  endpoint. Reads endpoint/model/key from `app/settings.py` (the runtime
  settings object, seeded from `config.*`, overridable in the UI) at generate
  time. `chat_template_kwargs.enable_thinking=false` is only sent when the
  `disable_thinking` setting is on (OpenAI proper rejects it). `get_backend()`
  imports lazily, so this path pulls in **no** diffusion/GPU code.
- **`diffusion-cnv`** (`app/llm/diffusion_cnv.py`) — drives a single
  **persistent** `llama-diffusion-cli -cnv` subprocess over stdin/stdout. This
  is the load-bearing/fragile part. The CLI has no HTTP server; the wrapper
  speaks a brittle pipe protocol (see module docstring): turn marker is
  `"\n> "` on stdout; input is read line-by-line with `getline`, so **prompts
  are flattened to literal `\n`** before sending (the system prompt tells the
  model to treat `\n` as a line break); `/clear` resets history between calls
  but keeps the `-sys` system prompt. Process is spawned lazily and idle-killed
  after `IDLE_TIMEOUT` (600s) to release ~14GB VRAM. A changed system prompt
  forces a respawn. `_read_until_marker` waits for the marker + a settle window
  rather than parsing a fixed protocol.
- **`diffusion-oneshot`** — one CLI process per call via `-f` file (full model
  reload each time). Fallback if the cnv stdin protocol breaks after a re-pin.
- **`openai`** — any OpenAI-compatible endpoint (homelab llama-swap qwen).
  Quality fallback + the fast local dev path.

All diffusion output goes through `clean_output` (strip ANSI / resolve `\r`
overwrites) and channel-thought stripping (`<channel|>` / `<think>`), since
DiffusionGemma emits a hidden thought channel before the answer.

### Why diffusion shapes the UX

Diffusion models denoise whole blocks — there is **no token streaming**.
Sections arrive whole, so the UI shows per-section "generating…" cards with an
elapsed-time heartbeat (SSE `progress`/`model_loading` events from
`flow._heartbeat`) rather than a streaming cursor.

## Carried llama.cpp patches (`patches/`, applied in Containerfile)

Both are **private carried patches — do NOT upstream** (llama.cpp AGENTS.md
policy forbids it):

1. **`DIFFUSION_NO_THINK`** — a one-line `sed` gating the model's hidden thought
   channel behind an env var (the diffusion example exposes no
   `--reasoning`/`--chat-template-kwargs` flag). Thinking on is ~6× slower.
2. **`patches/multi-gpu-diffusion.patch`** — enables the PR's single-device
   diffusion features across both RTX 5060 Ti GPUs (per-layer-device prompt-KV
   store, output-device `sc_dev`/`sc_embT` with VRAM fallback, CUDA sampler on
   the logits-owning device, last-row-only prefill logits). Validated bit-exact
   via the PR's `DG_SC_CHECK` / `DG_DEVSAMPLE_CHECK`. Background:
   `docs/multi-gpu-diffusiongemma.md`.

## Homelab deployment constraints

- Manifest lives in the **separate** gitops repo:
  `~/homelab-gitops/apps/aistack/promptgen.yaml`.
- **Mutually exclusive with a hot llama-swap model** on the same node — whichever
  loads second OOMs. Both idle out after 10 min (or `GET /unload` on llama-swap).
- Model runs fully in VRAM across both GPUs (`-ngl 99 -sm layer -ts 7,3`); `-n`
  is capped (n_ubatch growth drives reserve buffer size; too high OOMs).
- `/healthz` must **not** touch the LLM — it reports cached backend status so the
  pod stays Ready while the model is cold.
