"""Append-only audit log for OAuth token lifecycle events.

There's no database (single-replica, in-memory app), so "audit table" is an
append-only log line on the dedicated `promptgen.audit` logger (lowercase
namespace, matching the rest of the app's loggers). Each record carries a
timestamp, the action, the provider, and the provider account id so token
issuance / revocation can be traced (AC8 / NFR3). No tokens or secrets are ever
logged.
"""

import logging
import time

log = logging.getLogger("promptgen.audit")


def _emit(action: str, provider: str, user_id: str = "", user_login: str = "",
          **extra) -> None:
    fields = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "action": action,
        "provider": provider,
        "user_id": user_id or "-",
        "user_login": user_login or "-",
        **extra,
    }
    log.info("audit %s", " ".join(f"{k}={v}" for k, v in fields.items()))


def token_issued(provider: str, user_id: str = "", user_login: str = "",
                 **extra) -> None:
    """Record that a provider access token was issued/stored for a user."""
    _emit("token_issued", provider, user_id, user_login, **extra)


def token_refreshed(provider: str, user_id: str = "", user_login: str = "",
                    **extra) -> None:
    """Record that a provider access token was refreshed (Atlassian)."""
    _emit("token_refreshed", provider, user_id, user_login, **extra)


def token_revoked(provider: str, user_id: str = "", user_login: str = "",
                  **extra) -> None:
    """Record that a provider token was revoked / the user logged out."""
    _emit("token_revoked", provider, user_id, user_login, **extra)
