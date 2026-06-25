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
session id (`HttpOnly` + `Secure` + `SameSite=Lax`). Configure the OAuth app:

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

### Optional: Sign in with Atlassian (Jira export)

On the final step you can **"Sign in with Atlassian"** (OAuth 2.0 / 3LO) and
push the assembled mega-prompt straight into a Jira issue: pick a **Project** +
**Issue type**, hit **Export to Jira**, and you get back the issue key and a
clickable link. The brief is sent as a pretty **ADF** description and the raw
`.md` is also attached. Each user authorizes their **own** Jira site — there is
no shared/admin token. Access **and** refresh tokens plus the resolved
`cloudId`/site live **server-side only**; the cookie still carries just the
opaque signed session id, and the token is auto-refreshed before it lapses.

| Env var | What |
|---|---|
| `INCIPIT_ATLASSIAN_OAUTH_CLIENT_ID` | Atlassian OAuth app client id (public; a registered default is built in) |
| `INCIPIT_ATLASSIAN_OAUTH_CLIENT_SECRET` | Atlassian OAuth app client secret — **secret**, set via env/Doppler, never commit |
| `INCIPIT_ATLASSIAN_OAUTH_REDIRECT_URL` | Callback URL registered on the app (`…/auth/atlassian/callback`) |
| `INCIPIT_ATLASSIAN_OAUTH_SCOPES` | Console scopes (default `read:jira-work write:jira-work read:jira-user`); `offline_access` is appended at request time so a refresh token is issued |
| `INCIPIT_JIRA_ISSUE_TYPES` | Comma-separated issue types for the dropdown (default `Task,Story,Bug`) |
| `INCIPIT_JIRA_DEFAULT_PROJECT_KEY` | Optional project key to pre-select |
| `INCIPIT_JIRA_EXPORT_TIMEOUT` | End-to-end export budget in ms (default `4000`) |

Export events are recorded on the `promptgen.audit` logger. Leave the Atlassian
client id/secret blank to hide the button. **`INCIPIT_ATLASSIAN_OAUTH_CLIENT_SECRET`
must be supplied via env/Doppler** for the export flow to work.

### All environment variables

One table so a Doppler (or `.env`) config can be populated end-to-end. Secrets
are flagged — never commit them.

| Env var | Purpose | Default |
|---|---|---|
| `INCIPIT_BACKEND` | LLM backend: `openai` \| `diffusion-cnv` \| `diffusion-oneshot` | `openai` |
| `INCIPIT_OPENAI_BASE_URL` | OpenAI-compatible endpoint base URL | `http://localhost:11434/v1` |
| `INCIPIT_OPENAI_MODEL` | Default model id (overridable in the UI) | _(empty)_ |
| `INCIPIT_OPENAI_API_KEY` | API key for the endpoint (**secret**) | _(empty)_ |
| `INCIPIT_REASONING_EFFORT` | `default` \| `none` \| `low` \| `medium` \| `high` | `default` |
| `INCIPIT_DISABLE_THINKING` | Back-compat: truthy → `reasoning_effort=none` | _(unset)_ |
| `INCIPIT_ALLOWED_BASE_URL_HOSTS` | Extra hosts allowed for the model endpoint (SSRF allow-list) | _(empty)_ |
| `INCIPIT_SETTINGS_FILE` | Path for persisted UI settings | `.promptgen.json` |
| `INCIPIT_MAX_TOKENS` | Max generated tokens | `2048` |
| `INCIPIT_GEN_TIMEOUT` | Generation timeout (s) | `300` |
| `INCIPIT_LOAD_TIMEOUT` | Model load timeout (s) | `600` |
| `INCIPIT_IDLE_TIMEOUT` | Idle-kill timeout for the diffusion subprocess (s) | `600` |
| `INCIPIT_CLI_BIN` | Path to `llama-diffusion-cli` (diffusion backends) | `/usr/local/bin/llama-diffusion-cli` |
| `INCIPIT_MODEL` | GGUF model path (diffusion backends) | _(see config)_ |
| `INCIPIT_NGL` / `INCIPIT_N_CPU_MOE` / `INCIPIT_THREADS` | Diffusion CLI GPU/CPU/thread knobs | `99` / `18` / `8` |
| `INCIPIT_PROMPT_MARKER` | Diffusion `-cnv` turn marker | `"\n> "` |
| `INCIPIT_DIFFUSION_ARGS` | Extra diffusion CLI args | _(see config)_ |
| `INCIPIT_SESSION_TTL` | Session + auth-record TTL (s) | `86400` |
| `INCIPIT_GITHUB_TOKEN` | Anonymous-rate-limit token for public repo grounding | _(empty)_ |
| `INCIPIT_FIRECRAWL_URL` | Firecrawl base URL for non-GitHub repo scraping | _(empty)_ |
| `INCIPIT_REPO_TIMEOUT` | Repo-fetch HTTP timeout (s) | `25` |
| `INCIPIT_REPO_CONTEXT_MAX` | Max chars of repo context injected into prompts | `6000` |
| `INCIPIT_GITHUB_OAUTH_CLIENT_ID` | GitHub OAuth app client id (public) | _(built-in default)_ |
| `INCIPIT_GITHUB_OAUTH_CLIENT_SECRET` | GitHub OAuth app client secret (**secret**) | _(empty)_ |
| `INCIPIT_GITHUB_OAUTH_REDIRECT_URL` | GitHub OAuth callback URL | `https://incipit.nexus.inmotionhosting.com/auth/github/callback` |
| `INCIPIT_GITHUB_OAUTH_SCOPES` | GitHub OAuth scopes | `repo` |
| `INCIPIT_ATLASSIAN_OAUTH_CLIENT_ID` | Atlassian OAuth app client id (public) | _(built-in default)_ |
| `INCIPIT_ATLASSIAN_OAUTH_CLIENT_SECRET` | Atlassian OAuth app client secret (**secret**) | _(empty)_ |
| `INCIPIT_ATLASSIAN_OAUTH_REDIRECT_URL` | Atlassian OAuth callback URL | `https://incipit.nexus.inmotionhosting.com/auth/atlassian/callback` |
| `INCIPIT_ATLASSIAN_OAUTH_SCOPES` | Atlassian console scopes (`offline_access` appended at request time) | `read:jira-work write:jira-work read:jira-user` |
| `INCIPIT_JIRA_ISSUE_TYPES` | Issue-type dropdown options | `Task,Story,Bug` |
| `INCIPIT_JIRA_DEFAULT_PROJECT_KEY` | Pre-selected project key | _(empty)_ |
| `INCIPIT_JIRA_EXPORT_TIMEOUT` | Export time budget (ms) | `4000` |
| `INCIPIT_SESSION_COOKIE_SECRET` | Secret for signing the session cookie (**secret**; set so cookies survive restarts) | _(ephemeral per-process)_ |
| `INCIPIT_COOKIE_SECURE` | Set the cookie `Secure` flag | `true` |

## Testing & coverage

The repo ships an offline `pytest` suite (no network, no model/subprocess) —
OAuth flows and the Jira REST client are exercised against a mocked httpx
transport (`respx`):

```bash
pip install -r requirements-dev.txt
pytest          # runs with coverage (see pytest.ini)
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the same suite
on Python 3.11. Coverage is gated at **90%** but **scoped** (in `pytest.ini`) to
the security-critical, fully-offline-testable modules — `app/auth.py`,
`app/audit.py`, `app/jira.py`, `app/markdown_adf.py` — rather than the whole
`app` package: the LLM/diffusion backends and the wizard orchestration call out
to a model/subprocess and aren't covered by the offline suite, so a 90% gate
over all of `app` is impractical. The auth + export **routes** live in
`app/main.py` alongside every wizard route (so they can't be isolated per-file
by coverage), but they are covered by `tests/test_auth.py`,
`tests/test_jira_auth.py`, and `tests/test_jira_export.py`.

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
