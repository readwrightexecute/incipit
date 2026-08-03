"""In-memory, server-side auth store for per-user OAuth tokens.

A signed, opaque session id lives in the browser cookie (see the cookie
helpers in app/main.py); the *tokens themselves never leave the server*. Each
session record holds per-provider entries (`github`, and later `atlassian`)
plus the short-lived CSRF `state` values for in-flight OAuth handshakes.

Single replica, single user — like app/wizard/state.py, records are kept in a
module-level dict and TTL-swept; losing them on restart is acceptable (the user
simply logs in again). Generalized now so the Atlassian/Jira login can reuse
the same store and cookie.
"""

import asyncio
import secrets
import time
import uuid
from dataclasses import dataclass, field

from app import config


@dataclass
class ProviderEntry:
    """One provider's credentials + audit metadata, stored server-side only."""
    access_token: str
    scope: str = ""
    token_type: str = "bearer"
    # Atlassian (and any refreshable provider) populates these later.
    refresh_token: str = ""
    expires_at: float = 0.0          # epoch seconds; 0 = no expiry tracked
    # Provider account identity, used for the audit log.
    user_id: str = ""
    user_login: str = ""
    # Provider extras (e.g. Atlassian cloud_id / site_url).
    meta: dict = field(default_factory=dict)


@dataclass
class AuthRecord:
    id: str
    created: float
    providers: dict[str, ProviderEntry] = field(default_factory=dict)
    # In-flight OAuth handshakes: CSRF state token -> {provider, return_to}.
    pending: dict[str, dict] = field(default_factory=dict)
    # Atlassian rotates refresh tokens, so refreshes for one auth record must
    # be serialized to avoid submitting the same token concurrently.
    refresh_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def provider(self, name: str) -> ProviderEntry | None:
        return self.providers.get(name)


_auths: dict[str, AuthRecord] = {}


def _sweep() -> None:
    cutoff = time.time() - config.SESSION_TTL
    for sid in [k for k, v in _auths.items() if v.created < cutoff]:
        del _auths[sid]


def create_auth() -> AuthRecord:
    """Mint a fresh session record with an opaque id (the value signed into the
    cookie)."""
    _sweep()
    rec = AuthRecord(id=uuid.uuid4().hex, created=time.time())
    _auths[rec.id] = rec
    return rec


def get_auth(sid: str | None) -> AuthRecord | None:
    """Return the (non-expired) record for a session id, or None."""
    if not sid:
        return None
    rec = _auths.get(sid)
    if rec is None:
        return None
    if rec.created < time.time() - config.SESSION_TTL:
        del _auths[sid]
        return None
    return rec


def new_state(rec: AuthRecord, provider: str, return_to: str = "/") -> str:
    """Create + store an opaque CSRF `state` for an OAuth redirect."""
    state = secrets.token_urlsafe(24)
    rec.pending[state] = {"provider": provider, "return_to": return_to}
    return state


def pop_state(rec: AuthRecord, state: str, provider: str) -> dict | None:
    """Consume a CSRF `state` (single use). Returns its stored payload only if
    it exists and was issued for this provider; otherwise None."""
    if not state:
        return None
    payload = rec.pending.pop(state, None)
    if payload is None or payload.get("provider") != provider:
        return None
    return payload


def set_provider(rec: AuthRecord, provider: str, **kwargs) -> ProviderEntry:
    """Store/replace a provider's token + metadata on the record."""
    entry = ProviderEntry(**kwargs)
    rec.providers[provider] = entry
    return entry


def get_provider(sid: str | None, provider: str) -> ProviderEntry | None:
    """Convenience: resolve a session id straight to a provider entry."""
    rec = get_auth(sid)
    return rec.provider(provider) if rec else None


def revoke(rec: AuthRecord, provider: str | None = None) -> ProviderEntry | None:
    """Revoke one provider (returns the removed entry, for audit) or, when
    provider is None, drop the entire session record."""
    if provider is None:
        _auths.pop(rec.id, None)
        return None
    return rec.providers.pop(provider, None)
