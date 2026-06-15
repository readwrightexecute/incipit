"""Environment-driven settings. Every knob has a PROMPTGEN_* env override."""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()  # load a local .env if present; real env vars still win
except ImportError:
    pass


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


# Backend selection: openai | diffusion-cnv | diffusion-oneshot
# Default is `openai` so a fresh clone runs against any OpenAI-compatible
# endpoint (Ollama by default) with no GPU / llama.cpp build. The diffusion
# backends are the opt-in "advanced" path (see README).
BACKEND = os.environ.get("PROMPTGEN_BACKEND", "openai")

# llama-diffusion-cli settings
CLI_BIN = os.environ.get("PROMPTGEN_CLI_BIN", "/usr/local/bin/llama-diffusion-cli")
MODEL_PATH = os.environ.get(
    "PROMPTGEN_MODEL",
    "/models/diffusiongemma-26B-A4B-it-GGUF/diffusiongemma-26B-A4B-it-Q4_K_M.gguf",
)
N_GPU_LAYERS = os.environ.get("PROMPTGEN_NGL", "99")
N_CPU_MOE = os.environ.get("PROMPTGEN_N_CPU_MOE", "18")
THREADS = os.environ.get("PROMPTGEN_THREADS", "8")
MAX_TOKENS = _int("PROMPTGEN_MAX_TOKENS", 2048)
PROMPT_MARKER = os.environ.get("PROMPTGEN_PROMPT_MARKER", "\n> ")

DIFFUSION_ARGS = os.environ.get(
    "PROMPTGEN_DIFFUSION_ARGS",
    "--diffusion-eb auto --diffusion-eb-max-steps 48 "
    "--diffusion-eb-t-max 0.8 --diffusion-eb-t-min 0.4 "
    "--diffusion-eb-entropy-bound 0.1 --diffusion-eb-confidence 0.005 "
    "--diffusion-kv-cache auto --diffusion-gpu-sampling auto",
).split()

# Timeouts (seconds)
GEN_TIMEOUT = _int("PROMPTGEN_GEN_TIMEOUT", 300)
LOAD_TIMEOUT = _int("PROMPTGEN_LOAD_TIMEOUT", 600)
IDLE_TIMEOUT = _int("PROMPTGEN_IDLE_TIMEOUT", 600)

# OpenAI-compatible endpoint (the default backend). Defaults target a local
# Ollama install; override for LM Studio, llama-server, vLLM, or OpenAI proper.
# These seed the runtime settings (app/settings.py), which the UI can override.
OPENAI_BASE_URL = os.environ.get("PROMPTGEN_OPENAI_BASE_URL", "http://localhost:11434/v1")
OPENAI_MODEL = os.environ.get("PROMPTGEN_OPENAI_MODEL", "")
OPENAI_API_KEY = os.environ.get("PROMPTGEN_OPENAI_API_KEY", "")

# Send `chat_template_kwargs.enable_thinking=false` to suppress reasoning output.
# Works on llama.cpp/Qwen-style servers; OpenAI proper rejects it, so default
# OFF for portability. Enable for local reasoning models that burn the token
# budget on a hidden think channel.
DISABLE_THINKING = os.environ.get("PROMPTGEN_DISABLE_THINKING", "").lower() in ("1", "true", "yes")

# Session housekeeping
SESSION_TTL = _int("PROMPTGEN_SESSION_TTL", 24 * 3600)
