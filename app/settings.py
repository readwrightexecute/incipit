"""Runtime-mutable settings for the OpenAI-compatible backend.

Single-user, single-replica app (see app/wizard/state.py), so settings are a
process-global object rather than per-session. Seeded from PROMPTGEN_* env
(app/config.py), overridable live from the UI, and persisted to a gitignored
JSON file so a work-PC user only configures their endpoint once.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass

from app import config

log = logging.getLogger("promptgen.settings")

# CWD-relative so it lives next to the repo checkout; override for containers.
STORE_PATH = os.environ.get("PROMPTGEN_SETTINGS_FILE", ".promptgen.json")

_FIELDS = ("base_url", "model", "api_key", "disable_thinking")


@dataclass
class Settings:
    base_url: str = config.OPENAI_BASE_URL
    model: str = config.OPENAI_MODEL
    api_key: str = config.OPENAI_API_KEY
    disable_thinking: bool = config.DISABLE_THINKING


# Process-global. Read by app/llm/openai_compat.py at generate time.
current = Settings()


def load() -> None:
    """Load persisted overrides over the env-seeded defaults, if the file exists."""
    try:
        with open(STORE_PATH) as f:
            data = json.load(f)
    except FileNotFoundError:
        return
    except (OSError, ValueError) as e:
        log.warning("could not read %s: %s", STORE_PATH, e)
        return
    for k in _FIELDS:
        if k in data:
            setattr(current, k, data[k])
    log.info("loaded settings from %s (endpoint=%s model=%s)",
             STORE_PATH, current.base_url, current.model or "(unset)")


def save() -> None:
    try:
        with open(STORE_PATH, "w") as f:
            json.dump(asdict(current), f, indent=2)
    except OSError as e:
        log.warning("could not write %s: %s", STORE_PATH, e)


def update(*, base_url: str, model: str, api_key: str, disable_thinking: bool) -> None:
    current.base_url = base_url.strip().rstrip("/")
    current.model = model.strip()
    current.api_key = api_key.strip()
    current.disable_thinking = bool(disable_thinking)
    save()
