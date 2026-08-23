"""Which third-party integrations this deployment offers, and why.

One place answers "is GitHub on?" for the routes, the templates and the health
endpoint, so the three can never disagree. Two independent inputs decide it:

  * the explicit enable flag (`INCIPIT_<NAME>_ENABLED`, see app/config.py), and
  * whether the integration's credentials are actually configured.

An integration is *available* only when it is enabled AND configured. A flag
turned on without credentials is a deployment mistake, so it is reported once at
startup (`log_startup_status`) instead of surfacing as a confusing 503 the first
time somebody clicks the button.

Everything reads `config` at call time rather than caching, so tests (and a
future config reload) can monkeypatch a single attribute and see it take effect.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app import config

log = logging.getLogger("promptgen.integrations")


def _github_credentials() -> bool:
    return bool(config.GITHUB_OAUTH_CLIENT_ID and config.GITHUB_OAUTH_CLIENT_SECRET)


def _atlassian_credentials() -> bool:
    return bool(config.ATLASSIAN_OAUTH_CLIENT_ID and config.ATLASSIAN_OAUTH_CLIENT_SECRET)


def _openproject_credentials() -> bool:
    """Placeholder seam — there is no OpenProject client yet.

    Returning False keeps `available("openproject")` False even when the flag is
    on, so nothing can route to a client that doesn't exist. Wiring OpenProject
    up later means adding its `INCIPIT_OPENPROJECT_*` credentials to config and
    checking them here; every consumer below then works unchanged.
    """
    return False


@dataclass(frozen=True)
class Integration:
    """Static description of one integration: label, flag, credential check."""
    name: str
    label: str
    flag_env: str
    flag_attr: str
    credentials: Callable[[], bool]
    # Human-readable list of what a deployment must set for `credentials()` to
    # pass. Used verbatim in the startup misconfiguration warning.
    requires: str


GITHUB = Integration(
    name="github", label="GitHub",
    flag_env="INCIPIT_GITHUB_ENABLED", flag_attr="GITHUB_ENABLED",
    credentials=_github_credentials,
    requires="INCIPIT_GITHUB_OAUTH_CLIENT_ID and INCIPIT_GITHUB_OAUTH_CLIENT_SECRET",
)
ATLASSIAN = Integration(
    name="atlassian", label="Atlassian (Jira)",
    flag_env="INCIPIT_ATLASSIAN_ENABLED", flag_attr="ATLASSIAN_ENABLED",
    credentials=_atlassian_credentials,
    requires="INCIPIT_ATLASSIAN_OAUTH_CLIENT_ID and INCIPIT_ATLASSIAN_OAUTH_CLIENT_SECRET",
)
OPENPROJECT = Integration(
    name="openproject", label="OpenProject",
    flag_env="INCIPIT_OPENPROJECT_ENABLED", flag_attr="OPENPROJECT_ENABLED",
    credentials=_openproject_credentials,
    requires="an OpenProject client, which is not implemented yet",
)

REGISTRY: dict[str, Integration] = {i.name: i for i in (GITHUB, ATLASSIAN, OPENPROJECT)}


def _spec(name: str) -> Integration:
    try:
        return REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown integration {name!r}") from None


def enabled(name: str) -> bool:
    """Whether the operator has turned this integration on.

    An unset flag falls back to "enabled iff credentials are configured", which
    is the behaviour that predates the flags.
    """
    spec = _spec(name)
    flag = getattr(config, spec.flag_attr)
    return spec.credentials() if flag is None else flag


def configured(name: str) -> bool:
    """Whether the integration's credentials are present."""
    return _spec(name).credentials()


def available(name: str) -> bool:
    """Whether the integration can actually be used: enabled AND configured."""
    return enabled(name) and configured(name)


def misconfigured(name: str) -> bool:
    """Explicitly enabled but missing its credentials."""
    return enabled(name) and not configured(name)


def status() -> dict[str, dict[str, bool]]:
    """Capability report for /healthz and any other status surface."""
    return {
        name: {
            "enabled": enabled(name),
            "configured": configured(name),
            "available": available(name),
        }
        for name in REGISTRY
    }


def log_startup_status() -> None:
    """Log each integration's resolved state once, and warn about the
    actionable failure mode: a flag turned on with no credentials behind it."""
    for name, spec in REGISTRY.items():
        if misconfigured(name):
            log.warning(
                "%s integration is enabled (%s) but not configured: set %s, "
                "or set %s=false to disable it. It stays unavailable until then.",
                spec.label, spec.flag_env, spec.requires, spec.flag_env)
        elif available(name):
            log.info("%s integration enabled", spec.label)
        else:
            log.info("%s integration disabled (%s)", spec.label, spec.flag_env)
