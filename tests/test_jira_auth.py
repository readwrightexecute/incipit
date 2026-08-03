"""Tests for the Atlassian (Jira) OAuth 2.0 / 3LO login flow.

Mirrors tests/test_auth.py: all Atlassian HTTP is respx-mocked; the app's
outbound httpx uses the real AsyncHTTPTransport (intercepted), while the
Starlette TestClient talks to the app over its own ASGI transport. No network.
"""

import asyncio
import json
import logging
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import auth, config, main


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "ATLASSIAN_OAUTH_CLIENT_ID", "test-atl-id")
    monkeypatch.setattr(config, "ATLASSIAN_OAUTH_CLIENT_SECRET", "test-atl-secret")
    monkeypatch.setattr(config, "ATLASSIAN_OAUTH_REDIRECT_URL",
                        "https://app.example/auth/atlassian/callback")
    monkeypatch.setattr(config, "ATLASSIAN_OAUTH_SCOPES",
                        "read:jira-work write:jira-work read:jira-user")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    return TestClient(main.app)


def _start_login(client, return_to="/"):
    resp = client.get(f"/auth/atlassian/login?return_to={return_to}",
                      follow_redirects=False)
    state = parse_qs(urlparse(resp.headers["location"]).query)["state"][0]
    return resp, state


def _sid_from_jar(client) -> str:
    return main._serializer().loads(client.cookies[main.AUTH_COOKIE])


# --- login -------------------------------------------------------------------

def test_login_redirects_to_atlassian_authorize(client):
    resp, _ = _start_login(client, return_to="/sessions/abc")
    assert resp.status_code == 302
    loc = resp.headers["location"]
    assert loc.startswith("https://auth.atlassian.com/authorize")
    q = parse_qs(urlparse(loc).query)
    assert q["client_id"] == ["test-atl-id"]
    assert q["audience"] == ["api.atlassian.com"]
    assert q["response_type"] == ["code"]
    assert q["prompt"] == ["consent"]
    assert q["redirect_uri"] == ["https://app.example/auth/atlassian/callback"]
    assert q["state"]
    # offline_access is appended at request time (so we get a refresh token),
    # on top of the configured scopes.
    scopes = q["scope"][0].split()
    assert "offline_access" in scopes
    assert "read:jira-work" in scopes
    assert "write:jira-work" in scopes


def test_login_sets_hardened_cookie(monkeypatch):
    monkeypatch.setattr(config, "ATLASSIAN_OAUTH_CLIENT_ID", "test-atl-id")
    monkeypatch.setattr(config, "ATLASSIAN_OAUTH_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(config, "COOKIE_SECURE", True)
    c = TestClient(main.app)
    resp = c.get("/auth/atlassian/login", follow_redirects=False)
    low = resp.headers["set-cookie"].lower()
    assert "incipit_auth=" in low
    assert "httponly" in low
    assert "secure" in low
    # Lax (not Strict) so the cookie survives the cross-site OAuth callback.
    assert "samesite=lax" in low
    assert "path=/" in low


def test_login_not_configured_returns_503(monkeypatch):
    monkeypatch.setattr(config, "ATLASSIAN_OAUTH_CLIENT_ID", "test-atl-id")
    monkeypatch.setattr(config, "ATLASSIAN_OAUTH_CLIENT_SECRET", "")
    c = TestClient(main.app)
    resp = c.get("/auth/atlassian/login", follow_redirects=False)
    assert resp.status_code == 503


# --- callback ----------------------------------------------------------------

@respx.mock
def test_callback_stores_token_cloudid_and_redirects(client, caplog):
    token_route = respx.post(main.ATLASSIAN_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={
            "access_token": "atl_secret_token", "refresh_token": "atl_refresh",
            "expires_in": 3600, "scope": "read:jira-work offline_access",
            "token_type": "Bearer"}))
    res_route = respx.get(main.ATLASSIAN_RESOURCES_URL).mock(
        return_value=httpx.Response(200, json=[{
            "id": "cloud-123", "url": "https://acme.atlassian.net",
            "name": "Acme", "scopes": ["read:jira-work"]}]))

    _, state = _start_login(client, return_to="/sessions/xyz")
    with caplog.at_level(logging.INFO, logger="promptgen.audit"):
        resp = client.get(f"/auth/atlassian/callback?code=abc123&state={state}",
                          follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == "/sessions/xyz"
    assert token_route.called and res_route.called
    # No secret/token leaks into the cookie.
    assert "atl_secret_token" not in resp.headers.get("set-cookie", "")
    assert "atl_refresh" not in resp.headers.get("set-cookie", "")

    entry = auth.get_auth(_sid_from_jar(client)).provider("atlassian")
    assert entry.access_token == "atl_secret_token"
    assert entry.refresh_token == "atl_refresh"
    assert entry.expires_at > time.time() + 3000  # ~1h out
    assert entry.meta["cloud_id"] == "cloud-123"
    assert entry.meta["site_url"] == "https://acme.atlassian.net"
    assert entry.meta["site_name"] == "Acme"

    assert "token_issued" in caplog.text
    assert "atlassian" in caplog.text
    assert "atl_secret_token" not in caplog.text


@respx.mock
def test_callback_sends_authorization_code_grant_with_secret(client):
    token_route = respx.post(main.ATLASSIAN_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "t",
                                               "refresh_token": "r", "expires_in": 3600}))
    respx.get(main.ATLASSIAN_RESOURCES_URL).mock(
        return_value=httpx.Response(200, json=[{"id": "c", "url": "https://x.atlassian.net",
                                               "name": "X"}]))
    _, state = _start_login(client)
    client.get(f"/auth/atlassian/callback?code=thecode&state={state}",
               follow_redirects=False)
    sent = json.loads(token_route.calls[0].request.content.decode())
    assert sent["grant_type"] == "authorization_code"
    assert sent["client_secret"] == "test-atl-secret"
    assert sent["code"] == "thecode"
    assert sent["redirect_uri"] == "https://app.example/auth/atlassian/callback"


@respx.mock
def test_callback_rejects_empty_accessible_resources(client):
    respx.post(main.ATLASSIAN_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={
            "access_token": "t", "refresh_token": "r", "expires_in": 3600}))
    respx.get(main.ATLASSIAN_RESOURCES_URL).mock(
        return_value=httpx.Response(200, json=[]))
    _, state = _start_login(client, return_to="/sessions/xyz")
    resp = client.get(
        f"/auth/atlassian/callback?code=abc&state={state}",
        follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == (
        "/sessions/xyz?atlassian_error=No+accessible+Jira+site+was+returned+by+Atlassian."
    )
    assert auth.get_auth(_sid_from_jar(client)).provider("atlassian") is None


def test_callback_rejects_invalid_state(client):
    _start_login(client)
    resp = client.get("/auth/atlassian/callback?code=abc&state=wrong",
                      follow_redirects=False)
    assert resp.status_code == 400


def test_callback_without_session_returns_400(client):
    resp = client.get("/auth/atlassian/callback?code=abc&state=whatever",
                      follow_redirects=False)
    assert resp.status_code == 400


def test_callback_with_error_param_redirects_back(client):
    _, state = _start_login(client, return_to="/sessions/zzz")
    resp = client.get(f"/auth/atlassian/callback?error=access_denied&state={state}",
                      follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == (
        "/sessions/zzz?atlassian_error=Atlassian+sign-in+was+cancelled+or+denied."
    )


@respx.mock
def test_callback_token_failure_returns_to_origin_with_retry_message(client):
    respx.post(main.ATLASSIAN_TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"}))
    _, state = _start_login(client, return_to="/sessions/xyz")

    resp = client.get(f"/auth/atlassian/callback?code=expired&state={state}",
                      follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == (
        "/sessions/xyz?atlassian_error=Atlassian+could+not+complete+the+token+exchange."
    )


@respx.mock
def test_callback_without_accessible_site_returns_to_origin_with_retry_message(client):
    respx.post(main.ATLASSIAN_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "token"}))
    respx.get(main.ATLASSIAN_RESOURCES_URL).mock(return_value=httpx.Response(200, json=[]))
    _, state = _start_login(client, return_to="/sessions/xyz")

    resp = client.get(f"/auth/atlassian/callback?code=abc&state={state}",
                      follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == (
        "/sessions/xyz?atlassian_error=No+accessible+Jira+site+was+returned+by+Atlassian."
    )


@respx.mock
def test_callback_state_is_provider_scoped(client):
    # A state minted for github must not be accepted by the atlassian callback.
    rec = auth.create_auth()
    gh_state = auth.new_state(rec, "github", "/")
    client.cookies.set(main.AUTH_COOKIE, main._serializer().dumps(rec.id))
    resp = client.get(f"/auth/atlassian/callback?code=abc&state={gh_state}",
                      follow_redirects=False)
    assert resp.status_code == 400


# --- token refresh -----------------------------------------------------------

def _rec_with_atlassian(**over):
    rec = auth.create_auth()
    kwargs = dict(access_token="old", refresh_token="rt", scope="read:jira-work",
                  expires_at=time.time() - 10, user_id="cloud-1", user_login="Acme",
                  meta={"cloud_id": "cloud-1", "site_url": "https://acme.atlassian.net",
                        "site_name": "Acme"})
    kwargs.update(over)
    auth.set_provider(rec, "atlassian", **kwargs)
    return rec


@respx.mock
def test_refresh_mints_new_token_and_audits(client, caplog):
    route = respx.post(main.ATLASSIAN_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={
            "access_token": "fresh", "refresh_token": "rt2",
            "expires_in": 3600, "scope": "read:jira-work"}))
    rec = _rec_with_atlassian()  # already expired
    with caplog.at_level(logging.INFO, logger="promptgen.audit"):
        entry = _run(main.refresh_atlassian_token(rec))
    assert route.called
    sent = json.loads(route.calls[0].request.content.decode())
    assert sent["grant_type"] == "refresh_token"
    assert sent["refresh_token"] == "rt"
    assert entry.access_token == "fresh"
    assert entry.refresh_token == "rt2"  # rotated
    assert entry.expires_at > time.time() + 3000
    assert "token_refreshed" in caplog.text


@respx.mock
def test_refresh_skipped_when_token_still_valid(client):
    route = respx.post(main.ATLASSIAN_TOKEN_URL)
    rec = _rec_with_atlassian(expires_at=time.time() + 9999)
    entry = _run(main.refresh_atlassian_token(rec))
    assert entry.access_token == "old"
    assert not route.called  # no network when the token is fresh


def test_refresh_without_entry_raises(client):
    rec = auth.create_auth()
    with pytest.raises(main.AtlassianAuthError):
        _run(main.refresh_atlassian_token(rec))


def test_refresh_without_refresh_token_raises(client):
    rec = _rec_with_atlassian(refresh_token="")
    with pytest.raises(main.AtlassianAuthError):
        _run(main.refresh_atlassian_token(rec))


@respx.mock
def test_refresh_failure_raises_auth_error(client):
    respx.post(main.ATLASSIAN_TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"}))
    rec = _rec_with_atlassian()
    with pytest.raises(main.AtlassianAuthError):
        _run(main.refresh_atlassian_token(rec))


# --- logout ------------------------------------------------------------------

@respx.mock
def test_logout_revokes_and_audits(client, caplog):
    respx.post(main.ATLASSIAN_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "t", "refresh_token": "r",
                                               "expires_in": 3600}))
    respx.get(main.ATLASSIAN_RESOURCES_URL).mock(
        return_value=httpx.Response(200, json=[{"id": "c", "url": "https://x.atlassian.net",
                                               "name": "X"}]))
    _, state = _start_login(client)
    client.get(f"/auth/atlassian/callback?code=abc&state={state}", follow_redirects=False)
    sid = _sid_from_jar(client)
    assert auth.get_auth(sid).provider("atlassian") is not None

    with caplog.at_level(logging.INFO, logger="promptgen.audit"):
        resp = client.post("/auth/atlassian/logout")

    assert resp.status_code == 204
    assert resp.headers.get("HX-Refresh") == "true"
    assert auth.get_auth(sid).provider("atlassian") is None
    assert "token_revoked" in caplog.text
