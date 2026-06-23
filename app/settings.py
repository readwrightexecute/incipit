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
from urllib.parse import urlparse

from app import config

log = logging.getLogger("promptgen.settings")

# CWD-relative so it lives next to the repo checkout; override for containers.
STORE_PATH = os.environ.get("PROMPTGEN_SETTINGS_FILE", ".promptgen.json")

_FIELDS = ("base_url", "model", "api_key", "disable_thinking")
_DEFAULT_ALLOWED_BASE_URL_HOSTS = {"localhost", "127.0.0.1", "::1", "api.openai.com"}


class SettingsError(ValueError):
    """Raised when user-provided runtime settings are unsafe or invalid."""


def _hostname(value: str) -> str:
    parsed = urlparse(value if "://" in value else f"//{value}")
    return (parsed.hostname or "").lower()


def allowed_base_url_hosts() -> set[str]:
    hosts = set(_DEFAULT_ALLOWED_BASE_URL_HOSTS)
    seeded_host = _hostname(config.OPENAI_BASE_URL)
    if seeded_host:
        hosts.add(seeded_host)
    extra = os.environ.get("PROMPTGEN_ALLOWED_BASE_URL_HOSTS", "")
    hosts.update(
        host for host in (_hostname(part.strip()) for part in extra.split(",")) if host
    )
    return hosts


def normalize_base_url(base_url: str) -> str:
    """Validate and normalize a runtime-configured OpenAI-compatible endpoint."""
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        raise SettingsError("Endpoint must be an http(s) URL with a host.")
    if parsed.query or parsed.fragment:
        raise SettingsError("Endpoint must not include a query string or fragment.")
    host = parsed.hostname.lower()
    allowed_hosts = allowed_base_url_hosts()
    if host not in allowed_hosts:
        raise SettingsError(
            f"Endpoint host '{host}' is not allowed. "
            "Set PROMPTGEN_ALLOWED_BASE_URL_HOSTS to allow it."
        )
    return normalized


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
        if k not in data:
            continue
        if k == "base_url":
            try:
                current.base_url = normalize_base_url(str(data[k]))
            except SettingsError as e:
                log.warning("ignored unsafe base_url in %s: %s", STORE_PATH, e)
            continue
        setattr(current, k, data[k])
    log.info("loaded settings from %s (endpoint=%s model=%s)",
             STORE_PATH, current.base_url, current.model or "(unset)")


def save() -> None:
    try:
        with open(STORE_PATH, "w") as f:
            json.dump(asdict(current), f, indent=2)
    except OSError as e:
        log.warning("could not write %s: %s", STORE_PATH, e)
        return
    # The file holds the API key in plaintext — restrict it to the owner.
    try:
        os.chmod(STORE_PATH, 0o600)
    except OSError as e:
        log.warning("could not restrict permissions on %s: %s", STORE_PATH, e)


def update(*, base_url: str, model: str, api_key: str, disable_thinking: bool) -> None:
    current.base_url = normalize_base_url(base_url)
    current.model = model.strip()
    # A blank api_key field means "keep the existing stored key" (the UI never
    # echoes the secret back, so the field is empty on every load). Submit a
    # non-blank value to replace it. This means an empty key can't be set via
    # the form once one exists; clear PROMPTGEN_SETTINGS_FILE / env to reset.
    new_api_key = api_key.strip()
    if new_api_key:
        current.api_key = new_api_key
    current.disable_thinking = bool(disable_thinking)
    save()
