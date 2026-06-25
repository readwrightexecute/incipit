"""Tests for the GitHub OAuth login flow (app/main.py routes + app/auth.py store).

All GitHub HTTP is mocked with respx; the app's outbound httpx calls use the
real AsyncHTTPTransport (intercepted by respx), while the Starlette TestClient
talks to the app over its own ASGI transport (not intercepted). No network.
"""

import logging
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import auth, config, main


@pytest.fixture
def client(monkeypatch):
    # Deterministic, configured OAuth app; plain-HTTP cookies so the TestClient
    # jar round-trips them between login and callback.
    monkeypatch.setattr(config, "GITHUB_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(config, "GITHUB_OAUTH_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(config, "GITHUB_OAUTH_REDIRECT_URL",
                        "https://app.example/auth/github/callback")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    return TestClient(main.app)


def _start_login(client, return_to="/"):
    """Hit /auth/github/login, return (response, csrf_state). Leaves the signed
    cookie in the client jar."""
    resp = client.get(f"/auth/github/login?return_to={return_to}",
                      follow_redirects=False)
    state = parse_qs(urlparse(resp.headers["location"]).query)["state"][0]
    return resp, state


def _sid_from_jar(client) -> str:
    return main._serializer().loads(client.cookies[main.AUTH_COOKIE])


# --- login -------------------------------------------------------------------

def test_login_redirects_to_github_authorize(client):
    resp, _ = _start_login(client, return_to="/sessions/abc")
    assert resp.status_code == 302
    loc = resp.headers["location"]
    assert loc.startswith("https://github.com/login/oauth/authorize")
    q = parse_qs(urlparse(loc).query)
    assert q["client_id"] == ["test-client-id"]
    assert q["scope"] == ["repo"]
    assert q["redirect_uri"] == ["https://app.example/auth/github/callback"]
    assert q["state"]  # CSRF state present


def test_login_sets_hardened_cookie(monkeypatch):
    # Secure flag is on by default; assert the full flag set on the raw header.
    monkeypatch.setattr(config, "GITHUB_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(config, "COOKIE_SECURE", True)
    c = TestClient(main.app)
    resp = c.get("/auth/github/login", follow_redirects=False)
    set_cookie = resp.headers["set-cookie"]
    assert "incipit_auth=" in set_cookie
    low = set_cookie.lower()
    assert "httponly" in low
    assert "secure" in low
    assert "samesite=strict" in low
    assert "path=/" in low


def test_login_not_configured_returns_503(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_OAUTH_CLIENT_ID", "")
    c = TestClient(main.app)
    resp = c.get("/auth/github/login", follow_redirects=False)
    assert resp.status_code == 503


# --- callback ----------------------------------------------------------------

@respx.mock
def test_callback_exchanges_code_and_stores_token_server_side(client, caplog):
    token_route = respx.post(main.GITHUB_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={
            "access_token": "gho_secret_token", "scope": "repo",
            "token_type": "bearer"}))
    user_route = respx.get(main.GITHUB_USER_URL).mock(
        return_value=httpx.Response(200, json={"login": "octocat", "id": 583231}))

    _, state = _start_login(client)
    with caplog.at_level(logging.INFO, logger="promptgen.audit"):
        resp = client.get(f"/auth/github/callback?code=abc123&state={state}",
                          follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == "/"
    assert token_route.called and user_route.called
    # The secret never appears in the redirect / cookie — only the opaque sid.
    assert "gho_secret_token" not in resp.headers.get("set-cookie", "")

    # Token is retrievable only server-side, via the signed session id.
    rec = auth.get_auth(_sid_from_jar(client))
    entry = rec.provider("github")
    assert entry.access_token == "gho_secret_token"
    assert entry.user_login == "octocat"
    assert entry.user_id == "583231"

    # Audit recorded issuance with the account id, but no token value.
    assert "token_issued" in caplog.text
    assert "octocat" in caplog.text
    assert "gho_secret_token" not in caplog.text


@respx.mock
def test_callback_passes_client_secret_to_github(client):
    token_route = respx.post(main.GITHUB_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "t", "scope": "repo"}))
    respx.get(main.GITHUB_USER_URL).mock(
        return_value=httpx.Response(200, json={"login": "u", "id": 1}))
    _, state = _start_login(client)
    client.get(f"/auth/github/callback?code=abc&state={state}", follow_redirects=False)
    sent = parse_qs(token_route.calls[0].request.content.decode())
    assert sent["client_secret"] == ["test-client-secret"]
    assert sent["code"] == ["abc"]


def test_callback_rejects_invalid_state(client):
    _start_login(client)  # establishes a session, but we send a bogus state
    resp = client.get("/auth/github/callback?code=abc&state=not-the-real-state",
                      follow_redirects=False)
    assert resp.status_code == 400


def test_callback_without_session_returns_400(client):
    resp = client.get("/auth/github/callback?code=abc&state=whatever",
                      follow_redirects=False)
    assert resp.status_code == 400


def test_callback_with_error_param_redirects_back(client):
    _, state = _start_login(client, return_to="/sessions/xyz")
    resp = client.get(
        f"/auth/github/callback?error=access_denied&state={state}",
        follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/sessions/xyz"


# --- logout ------------------------------------------------------------------

@respx.mock
def test_logout_revokes_token_and_clears_cookie(client, caplog):
    respx.post(main.GITHUB_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "t", "scope": "repo"}))
    respx.get(main.GITHUB_USER_URL).mock(
        return_value=httpx.Response(200, json={"login": "octocat", "id": 7}))
    _, state = _start_login(client)
    client.get(f"/auth/github/callback?code=abc&state={state}", follow_redirects=False)
    sid = _sid_from_jar(client)
    assert auth.get_auth(sid).provider("github") is not None

    with caplog.at_level(logging.INFO, logger="promptgen.audit"):
        resp = client.post("/auth/github/logout")

    assert resp.status_code == 204
    assert resp.headers.get("HX-Refresh") == "true"
    # Cookie cleared (Max-Age=0 / past expiry).
    set_cookie = resp.headers["set-cookie"].lower()
    assert "incipit_auth=" in set_cookie
    assert "max-age=0" in set_cookie or "expires=" in set_cookie
    # Server-side token gone, revocation audited.
    assert auth.get_auth(sid).provider("github") is None
    assert "token_revoked" in caplog.text


# --- store unit --------------------------------------------------------------

def test_auth_store_state_is_single_use():
    rec = auth.create_auth()
    state = auth.new_state(rec, "github", "/x")
    assert auth.pop_state(rec, state, "github") == {"provider": "github", "return_to": "/x"}
    # Second pop fails (single use) and a wrong-provider pop fails.
    assert auth.pop_state(rec, state, "github") is None


def test_auth_store_state_rejects_wrong_provider():
    rec = auth.create_auth()
    state = auth.new_state(rec, "github", "/")
    assert auth.pop_state(rec, state, "atlassian") is None


def test_auth_store_pop_state_empty_is_none():
    rec = auth.create_auth()
    assert auth.pop_state(rec, "", "github") is None


def test_get_auth_none_and_unknown_returns_none():
    assert auth.get_auth(None) is None
    assert auth.get_auth("does-not-exist") is None


def test_get_auth_expired_is_evicted(monkeypatch):
    rec = auth.create_auth()
    # Backdate the record beyond the TTL: get_auth should evict and return None.
    rec.created = time.time() - config.SESSION_TTL - 1
    assert auth.get_auth(rec.id) is None
    assert auth.get_auth(rec.id) is None  # already removed


def test_sweep_drops_expired_records():
    rec = auth.create_auth()
    rec.created = time.time() - config.SESSION_TTL - 1
    auth.create_auth()  # triggers a sweep on insert
    assert auth.get_auth(rec.id) is None


def test_get_provider_resolves_via_session_id():
    rec = auth.create_auth()
    auth.set_provider(rec, "github", access_token="t", user_login="octocat")
    assert auth.get_provider(rec.id, "github").user_login == "octocat"
    assert auth.get_provider(rec.id, "atlassian") is None
    assert auth.get_provider(None, "github") is None


def test_revoke_whole_record_drops_session():
    rec = auth.create_auth()
    auth.set_provider(rec, "github", access_token="t")
    assert auth.revoke(rec, None) is None
    assert auth.get_auth(rec.id) is None
