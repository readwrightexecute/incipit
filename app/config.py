"""Environment-driven settings. Every knob has a INCIPIT_* env override."""

import logging
import os
import shlex

try:
    from dotenv import load_dotenv

    load_dotenv()  # load a local .env if present; real env vars still win
except ImportError:
    pass

log = logging.getLogger("promptgen.config")


def _int(name: str, default: int) -> int:
    """Parse an int env override, falling back to default on a bad value so a
    typo in one env var can't crash the process at import time."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        log.warning("invalid integer for %s=%r; using default %d", name, raw, default)
        return default


def _bool(name: str, default: bool) -> bool:
    """Parse a boolean env override. Truthy: 1/true/yes/on (case-insensitive)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Backend selection: openai | diffusion-cnv | diffusion-oneshot
# Default is `openai` so a fresh clone runs against any OpenAI-compatible
# endpoint (Ollama by default) with no GPU / llama.cpp build. The diffusion
# backends are the opt-in "advanced" path (see README).
BACKEND = os.environ.get("INCIPIT_BACKEND", "openai")

# llama-diffusion-cli settings
CLI_BIN = os.environ.get("INCIPIT_CLI_BIN", "/usr/local/bin/llama-diffusion-cli")
MODEL_PATH = os.environ.get(
    "INCIPIT_MODEL",
    "/models/diffusiongemma-26B-A4B-it-GGUF/diffusiongemma-26B-A4B-it-Q4_K_M.gguf",
)
N_GPU_LAYERS = os.environ.get("INCIPIT_NGL", "99")
N_CPU_MOE = os.environ.get("INCIPIT_N_CPU_MOE", "18")
THREADS = os.environ.get("INCIPIT_THREADS", "8")
MAX_TOKENS = _int("INCIPIT_MAX_TOKENS", 2048)
PROMPT_MARKER = os.environ.get("INCIPIT_PROMPT_MARKER", "\n> ")

DIFFUSION_ARGS = os.environ.get(
    "INCIPIT_DIFFUSION_ARGS",
    "--diffusion-eb auto --diffusion-eb-max-steps 48 "
    "--diffusion-eb-t-max 0.8 --diffusion-eb-t-min 0.4 "
    "--diffusion-eb-entropy-bound 0.1 --diffusion-eb-confidence 0.005 "
    "--diffusion-kv-cache auto --diffusion-gpu-sampling auto",
)
# shlex (not .split()) so an override with quoted/space-bearing values tokenizes
# correctly before being passed to subprocess_exec.
DIFFUSION_ARGS = shlex.split(DIFFUSION_ARGS)

# Timeouts (seconds)
GEN_TIMEOUT = _int("INCIPIT_GEN_TIMEOUT", 300)
LOAD_TIMEOUT = _int("INCIPIT_LOAD_TIMEOUT", 600)
IDLE_TIMEOUT = _int("INCIPIT_IDLE_TIMEOUT", 600)

# OpenAI-compatible endpoint (the default backend). Defaults target a local
# Ollama install; override for LM Studio, llama-server, vLLM, or OpenAI proper.
# These seed the runtime settings (app/settings.py), which the UI can override.
OPENAI_BASE_URL = os.environ.get("INCIPIT_OPENAI_BASE_URL", "http://localhost:11434/v1")
OPENAI_MODEL = os.environ.get("INCIPIT_OPENAI_MODEL", "")
OPENAI_API_KEY = os.environ.get("INCIPIT_OPENAI_API_KEY", "")

# Reasoning effort sent to the OpenAI-compatible endpoint. One of:
#   default          - omit the field entirely (the model decides)
#   none             - reasoning_effort="none" (+ enable_thinking=false for llama.cpp)
#   low | medium | high - reasoning_effort=<level>
# Seeds the runtime setting (app/settings.py); the UI can override it live.
# Only the OpenAI-compatible backend reads this; the diffusion backends ignore it.
# Back-compat: the older INCIPIT_DISABLE_THINKING boolean maps truthy -> "none".
_REASONING_EFFORTS = ("default", "none", "low", "medium", "high")


def _reasoning_effort_default() -> str:
    val = os.environ.get("INCIPIT_REASONING_EFFORT", "").strip().lower()
    if val in _REASONING_EFFORTS:
        return val
    if val:
        return "default"  # unrecognized explicit value -> safe default
    if os.environ.get("INCIPIT_DISABLE_THINKING", "").lower() in ("1", "true", "yes"):
        return "none"
    return "default"


REASONING_EFFORT = _reasoning_effort_default()

# Session housekeeping
SESSION_TTL = _int("INCIPIT_SESSION_TTL", 24 * 3600)

# Existing-project repo grounding (Workstream F). For "existing" projects the
# wizard fetches a compact repo summary and injects it into the drafting prompts.
# GITHUB_TOKEN is optional (lifts the 60 req/h anonymous rate limit). FIRECRAWL_URL
# is the homelab Firecrawl base (e.g. http://firecrawl.default.svc:3002) used as a
# fallback for non-GitHub hosts or API failures; blank disables the fallback.
GITHUB_TOKEN = os.environ.get("INCIPIT_GITHUB_TOKEN", "")
FIRECRAWL_URL = os.environ.get("INCIPIT_FIRECRAWL_URL", "")
REPO_TIMEOUT = _int("INCIPIT_REPO_TIMEOUT", 25)
REPO_CONTEXT_MAX_CHARS = _int("INCIPIT_REPO_CONTEXT_MAX", 6000)

# --- GitHub OAuth login (per-user "Login with GitHub") ---------------------
# Lets a signed-in user ground the spec in their own private repos. The user's
# access token is stored server-side only (app/auth.py); the browser cookie
# carries just a signed, opaque session id. The CLIENT_ID below is the public,
# registered OAuth-app id (not a secret); the CLIENT_SECRET must come from the
# environment (Doppler/Vault) and must never be committed. Blank client
# id/secret simply disables the login button.
GITHUB_OAUTH_CLIENT_ID = os.environ.get(
    "INCIPIT_GITHUB_OAUTH_CLIENT_ID", "Ov23liQTAZncU8NnfMS4")
GITHUB_OAUTH_CLIENT_SECRET = os.environ.get("INCIPIT_GITHUB_OAUTH_CLIENT_SECRET", "")
GITHUB_OAUTH_REDIRECT_URL = os.environ.get(
    "INCIPIT_GITHUB_OAUTH_REDIRECT_URL",
    "https://incipit.nexus.inmotionhosting.com/auth/github/callback")
GITHUB_OAUTH_SCOPES = os.environ.get("INCIPIT_GITHUB_OAUTH_SCOPES", "repo")

# Secret used to sign the opaque session-id cookie (itsdangerous). If unset we
# generate an ephemeral per-process secret: cookies then work within a single
# run but don't survive a restart — acceptable for the single-replica design,
# but set this in any real deploy so sessions persist across restarts.
SESSION_COOKIE_SECRET = os.environ.get("INCIPIT_SESSION_COOKIE_SECRET", "")
if not SESSION_COOKIE_SECRET:
    import secrets as _secrets

    SESSION_COOKIE_SECRET = _secrets.token_urlsafe(32)
    log.warning("INCIPIT_SESSION_COOKIE_SECRET not set; using an ephemeral "
                "per-process secret (auth cookies won't survive a restart)")

# Set the Secure flag on auth cookies (HTTPS only). Default true; set false for
# local plain-HTTP development.
COOKIE_SECURE = _bool("INCIPIT_COOKIE_SECURE", True)
