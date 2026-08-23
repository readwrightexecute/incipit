"""Tests for private-repo listing + the /api/github/repos route + the selected-
repo grounding in flow._ensure_repo_context.

GitHub HTTP is respx-mocked; the app's outbound httpx uses the real
AsyncHTTPTransport (intercepted), while the TestClient talks to the app over its
own ASGI transport (not intercepted). No network, no sleeps (backoff is patched).
"""

import asyncio

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import auth, config, main, repo
from app.wizard import flow, state

_REPOS_URL = "https://api.github.com/user/repos"


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    """Don't actually sleep on the retry-backoff path during tests."""
    async def _noslee_p(*_a, **_k):
        return None
    monkeypatch.setattr(repo.asyncio, "sleep", _noslee_p)


def _repo_json(full_name, **extra):
    owner, _, name = full_name.partition("/")
    return {"full_name": full_name, "name": name, "private": True,
            "description": extra.get("description", ""),
            "html_url": f"https://github.com/{full_name}",
            "default_branch": extra.get("default_branch", "main")}


# --- repo.list_private_repos ------------------------------------------------

@respx.mock
def test_list_private_repos_shape_single_page():
    respx.get(_REPOS_URL).mock(return_value=httpx.Response(200, json=[
        _repo_json("octocat/secret", description="hush"),
        _repo_json("octocat/other"),
    ]))
    repos = _run(repo.list_private_repos("gho_token"))
    assert [r["full_name"] for r in repos] == ["octocat/secret", "octocat/other"]
    first = repos[0]
    assert set(first) == {"full_name", "name", "private", "description",
                          "html_url", "default_branch"}
    assert first["private"] is True
    assert first["name"] == "secret"
    assert first["description"] == "hush"


@respx.mock
def test_list_private_repos_sends_bearer_and_visibility():
    route = respx.get(_REPOS_URL).mock(return_value=httpx.Response(200, json=[]))
    _run(repo.list_private_repos("gho_token"))
    req = route.calls[0].request
    assert req.headers["Authorization"] == "Bearer gho_token"
    assert req.url.params["visibility"] == "private"
    assert req.url.params["per_page"] == "100"


@respx.mock
def test_list_private_repos_paginates():
    page1 = [_repo_json(f"octocat/r{i}") for i in range(100)]
    page2 = [_repo_json("octocat/last")]

    def handler(request):
        page = request.url.params.get("page")
        return httpx.Response(200, json=page1 if page == "1" else page2)

    respx.get(_REPOS_URL).mock(side_effect=handler)
    repos = _run(repo.list_private_repos("gho_token"))
    assert len(repos) == 101
    assert repos[-1]["full_name"] == "octocat/last"


@respx.mock
def test_list_private_repos_401_raises_auth_error():
    respx.get(_REPOS_URL).mock(return_value=httpx.Response(401, json={"message": "Bad credentials"}))
    with pytest.raises(repo.GitHubAuthError):
        _run(repo.list_private_repos("expired"))


def test_list_private_repos_no_token_raises_auth_error():
    with pytest.raises(repo.GitHubAuthError):
        _run(repo.list_private_repos(""))


@respx.mock
def test_list_private_repos_retries_once_then_succeeds():
    route = respx.get(_REPOS_URL).mock(side_effect=[
        httpx.ConnectError("transient blip"),
        httpx.Response(200, json=[_repo_json("octocat/ok")]),
    ])
    repos = _run(repo.list_private_repos("gho_token"))
    assert [r["full_name"] for r in repos] == ["octocat/ok"]
    assert route.call_count == 2  # initial failure + one retry


@respx.mock
def test_list_private_repos_retry_exhausted_propagates():
    respx.get(_REPOS_URL).mock(side_effect=[
        httpx.ConnectError("blip 1"),
        httpx.ConnectError("blip 2"),
    ])
    with pytest.raises(httpx.HTTPError):
        _run(repo.list_private_repos("gho_token"))


# --- /api/github/repos route ------------------------------------------------

def _authed_client(monkeypatch, token="gho_secret"):
    # Credentials present and the flag left unset, i.e. the GitHub integration
    # resolves to available (see app/integrations.py).
    monkeypatch.setattr(config, "GITHUB_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(config, "GITHUB_OAUTH_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    rec = auth.create_auth()
    auth.set_provider(rec, "github", access_token=token, user_login="octocat",
                      user_id="1", scope="repo")
    c = TestClient(main.app)
    c.cookies.set(main.AUTH_COOKIE, main._serializer().dumps(rec.id))
    return c


def test_repos_route_unauthenticated_returns_401(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(config, "GITHUB_OAUTH_CLIENT_SECRET", "test-client-secret")
    c = TestClient(main.app)  # no auth cookie
    resp = c.get("/api/github/repos")
    assert resp.status_code == 401
    # Surfaces the re-authorize modal; never any repo data.
    assert "Re-authorize" in resp.text
    assert "selected_repos" not in resp.text


@respx.mock
def test_repos_route_authed_lists_repos_without_leaking_token(monkeypatch):
    respx.get(_REPOS_URL).mock(return_value=httpx.Response(200, json=[
        _repo_json("octocat/private-one", description="d1"),
        _repo_json("octocat/private-two"),
    ]))
    c = _authed_client(monkeypatch, token="gho_super_secret")
    resp = c.get("/api/github/repos")
    assert resp.status_code == 200
    assert "octocat/private-one" in resp.text
    assert "octocat/private-two" in resp.text
    # The token must never appear in the rendered HTML.
    assert "gho_super_secret" not in resp.text
    # Checkboxes are wired to the form field the wizard reads.
    assert 'name="selected_repos"' in resp.text


@respx.mock
def test_repos_route_auth_error_returns_401_modal(monkeypatch):
    respx.get(_REPOS_URL).mock(return_value=httpx.Response(401, json={"message": "Bad credentials"}))
    c = _authed_client(monkeypatch, token="revoked")
    resp = c.get("/api/github/repos")
    assert resp.status_code == 401
    assert "Re-authorize" in resp.text


# --- flow grounding for selected private repos ------------------------------

def test_ensure_repo_context_concatenates_selected_repos(monkeypatch):
    calls = {"selected": [], "url": None}

    async def fake_selected(full_name, token):
        calls["selected"].append((full_name, token))
        return f"CTX[{full_name}]"

    async def fake_url(url):
        calls["url"] = url
        return "CTX[url-fallback]"

    monkeypatch.setattr(flow.repo, "fetch_selected_repo_context", fake_selected)
    monkeypatch.setattr(flow.repo, "fetch_repo_context", fake_url)

    rec = auth.create_auth()
    auth.set_provider(rec, "github", access_token="tok")
    s = state.Session(id="t", created=0.0, project_type="existing",
                      selected_repos=["o/a", "o/b"], github_auth_id=rec.id,
                      repo_url="https://github.com/o/c")
    _run(flow._ensure_repo_context(s))

    # Both picked repos fetched with the server-side token, plus the URL fallback.
    assert calls["selected"] == [("o/a", "tok"), ("o/b", "tok")]
    assert calls["url"] == "https://github.com/o/c"
    assert "CTX[o/a]" in s.repo_context
    assert "CTX[o/b]" in s.repo_context
    assert "CTX[url-fallback]" in s.repo_context


def test_ensure_repo_context_respects_token_budget(monkeypatch):
    monkeypatch.setattr(config, "REPO_CONTEXT_MAX_CHARS", 10)

    async def fake_selected(full_name, token):
        return "X" * 100  # exceeds the whole budget on its own

    async def fake_url(url):  # must never be reached once the budget is spent
        raise AssertionError("repo_url fallback should not run when budget is 0")

    monkeypatch.setattr(flow.repo, "fetch_selected_repo_context", fake_selected)
    monkeypatch.setattr(flow.repo, "fetch_repo_context", fake_url)

    rec = auth.create_auth()
    auth.set_provider(rec, "github", access_token="tok")
    s = state.Session(id="t", created=0.0, project_type="existing",
                      selected_repos=["o/a"], github_auth_id=rec.id,
                      repo_url="https://github.com/o/c")
    _run(flow._ensure_repo_context(s))
    assert len(s.repo_context) <= 10


def test_ensure_repo_context_skips_when_not_existing(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("should not fetch for non-existing projects")

    monkeypatch.setattr(flow.repo, "fetch_selected_repo_context", boom)
    monkeypatch.setattr(flow.repo, "fetch_repo_context", boom)
    s = state.Session(id="t", created=0.0, project_type="new",
                      selected_repos=["o/a"], repo_url="https://github.com/o/c")
    _run(flow._ensure_repo_context(s))
    assert s.repo_context == ""
