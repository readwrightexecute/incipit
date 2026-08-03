"""Tests for app/repo.py: the SSRF host check (_host_is_public), the GitHub URL
regex routing (_GITHUB_RE), and the routing decisions in fetch_repo_context.

All network is mocked: socket.getaddrinfo is monkeypatched to return chosen
addresses, and _github / _firecrawl are replaced with recording stubs. Nothing
in this file makes a real DNS or HTTP call.
"""

import asyncio
import base64
import socket

import httpx
import pytest
import respx

from app import config, repo


def _run(coro):
    return asyncio.run(coro)


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _addrinfo(*ips):
    """Build a getaddrinfo-shaped result for the given IP strings."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in ips]


# --- _GITHUB_RE -------------------------------------------------------------

@pytest.mark.parametrize(
    "url,owner,repo_name",
    [
        ("https://github.com/owner/repo", "owner", "repo"),
        ("https://github.com/owner/repo/tree/main", "owner", "repo"),
        ("git@github.com:owner/repo", "owner", "repo"),
        ("https://github.com/owner/repo.git", "owner", "repo.git"),  # .git stripped later
        ("http://www.github.com/Foo/Bar", "Foo", "Bar"),
    ],
)
def test_github_regex_extracts_owner_repo(url, owner, repo_name):
    m = repo._GITHUB_RE.search(url)
    assert m is not None
    assert m.group(1) == owner
    assert m.group(2) == repo_name


def test_github_regex_does_not_match_non_github():
    assert repo._GITHUB_RE.search("https://gitlab.com/owner/repo") is None
    assert repo._GITHUB_RE.search("https://example.com/foo/bar") is None


# --- _host_is_public --------------------------------------------------------

@pytest.mark.parametrize("public_ip", ["8.8.8.8", "1.1.1.1", "93.184.216.34"])
def test_host_is_public_allows_public_ipv4(monkeypatch, public_ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo(public_ip))
    assert _run(repo._host_is_public("https://example.com")) is True


@pytest.mark.parametrize(
    "private_ip",
    [
        "10.0.0.1",       # RFC1918
        "192.168.1.1",    # RFC1918
        "172.16.0.1",     # RFC1918
        "127.0.0.1",      # loopback
        "169.254.0.1",    # link-local
        "0.0.0.0",        # unspecified
        "224.0.0.1",      # multicast
        "240.0.0.1",      # reserved
    ],
)
def test_host_is_public_rejects_non_public_ipv4(monkeypatch, private_ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo(private_ip))
    assert _run(repo._host_is_public("https://internal.example")) is False


def test_host_is_public_rejects_ipv6_loopback(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("::1"))
    assert _run(repo._host_is_public("https://example.com")) is False


def test_host_is_public_strips_ipv6_zone_id(monkeypatch):
    # A link-local IPv6 with a zone id should still be parsed and rejected.
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("fe80::1%eth0"))
    assert _run(repo._host_is_public("https://example.com")) is False


def test_host_is_public_rejects_if_any_address_is_private(monkeypatch):
    # DNS rebinding-style: one public + one private answer → reject.
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("8.8.8.8", "10.0.0.1"))
    assert _run(repo._host_is_public("https://example.com")) is False


def test_host_is_public_rejects_unresolvable(monkeypatch):
    def boom(*a, **k):
        raise socket.gaierror("name resolution failed")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    assert _run(repo._host_is_public("https://nope.invalid")) is False


def test_host_is_public_rejects_url_without_host(monkeypatch):
    # No host in the URL → False without even resolving.
    called = False

    def tracker(*a, **k):
        nonlocal called
        called = True
        return _addrinfo("8.8.8.8")

    monkeypatch.setattr(socket, "getaddrinfo", tracker)
    assert _run(repo._host_is_public("not-a-url")) is False
    assert called is False


# --- fetch_repo_context routing ---------------------------------------------

@pytest.fixture
def routing_spies(monkeypatch):
    """Replace the network-touching helpers with recording stubs so we can
    assert which path fetch_repo_context takes."""
    calls = {"github": None, "firecrawl": None}

    async def fake_github(owner, repo_name):
        calls["github"] = (owner, repo_name)
        return f"GITHUB:{owner}/{repo_name}"

    async def fake_firecrawl(url):
        calls["firecrawl"] = url
        return f"FIRECRAWL:{url}"

    monkeypatch.setattr(repo, "_github", fake_github)
    monkeypatch.setattr(repo, "_firecrawl", fake_firecrawl)
    return calls


def test_fetch_empty_url_returns_empty(routing_spies):
    assert _run(repo.fetch_repo_context("")) == ""
    assert _run(repo.fetch_repo_context("   ")) == ""
    assert routing_spies["github"] is None
    assert routing_spies["firecrawl"] is None


def test_fetch_github_url_routes_to_github(routing_spies):
    out = _run(repo.fetch_repo_context("https://github.com/owner/repo"))
    assert out == "GITHUB:owner/repo"
    assert routing_spies["github"] == ("owner", "repo")
    assert routing_spies["firecrawl"] is None


def test_fetch_github_url_strips_dot_git(routing_spies):
    _run(repo.fetch_repo_context("https://github.com/owner/repo.git"))
    assert routing_spies["github"] == ("owner", "repo")


def test_fetch_git_ssh_url_routes_to_github(routing_spies):
    _run(repo.fetch_repo_context("git@github.com:owner/repo"))
    assert routing_spies["github"] == ("owner", "repo")


def test_fetch_non_http_scheme_blocked(routing_spies):
    out = _run(repo.fetch_repo_context("ftp://example.com/repo"))
    assert "Won't fetch non-http(s) URL" in out
    assert routing_spies["firecrawl"] is None


def test_fetch_public_non_github_routes_to_firecrawl(routing_spies, monkeypatch):
    async def public(url):
        return True

    monkeypatch.setattr(repo, "_host_is_public", public)
    out = _run(repo.fetch_repo_context("https://gitlab.com/owner/repo"))
    assert out == "FIRECRAWL:https://gitlab.com/owner/repo"
    assert routing_spies["firecrawl"] == "https://gitlab.com/owner/repo"


def test_fetch_private_host_blocked(routing_spies, monkeypatch):
    async def private(url):
        return False

    monkeypatch.setattr(repo, "_host_is_public", private)
    out = _run(repo.fetch_repo_context("https://internal.example/repo"))
    assert "private or unresolvable host" in out
    assert routing_spies["firecrawl"] is None


def test_fetch_never_raises_on_internal_error(monkeypatch):
    # fetch_repo_context must be best-effort: any exception is caught and
    # surfaced as a context note, never propagated.
    async def boom(owner, repo_name):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(repo, "_github", boom)
    out = _run(repo.fetch_repo_context("https://github.com/owner/repo"))
    assert "Could not fetch repo context" in out
    assert "kaboom" in out


# --- _github / _firecrawl end-to-end (mocked HTTP) --------------------------
#
# These drive the real httpx code paths in app/repo.py against a respx-mocked
# transport — no DNS, no sockets. They cover the full GitHub
# meta→languages→readme→tree→_summarize path and the private-repo→Firecrawl
# fallback, complementing the routing tests above (which stub _github/_firecrawl
# entirely).

_GH_BASE = "https://api.github.com/repos/owner/repo"


def _mock_github_full():
    """Register the four GitHub REST endpoints for a healthy public repo."""
    respx.get(_GH_BASE).mock(return_value=httpx.Response(200, json={
        "full_name": "owner/repo",
        "default_branch": "main",
        "description": "A test repository",
        "topics": ["python", "cli"],
    }))
    respx.get(_GH_BASE + "/languages").mock(return_value=httpx.Response(200, json={
        "Python": 12000, "Shell": 800,
    }))
    respx.get(_GH_BASE + "/readme").mock(return_value=httpx.Response(200, json={
        "content": _b64("# Owner Repo\n\nA sample project README body."),
    }))
    respx.get(_GH_BASE + "/git/trees/main", params={"recursive": "1"}).mock(
        return_value=httpx.Response(200, json={"tree": [
            {"path": "app", "type": "tree"},
            {"path": "app/main.py", "type": "blob"},
            {"path": "README.md", "type": "blob"},
            {"path": "tests/test_main.py", "type": "blob"},
        ]}))


@respx.mock
def test_github_full_path_summarizes(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_TOKEN", "")
    _mock_github_full()
    out = _run(repo._github("owner", "repo"))
    assert "Repository: owner/repo" in out
    assert "Description: A test repository" in out
    # Languages preserved in order, capped at 6.
    assert "Python" in out and "Shell" in out
    assert "Topics: python, cli" in out
    # Top-level entries derived from blob paths' first segment.
    assert "app" in out and "README.md" in out and "tests" in out
    # File sample lists blobs (not trees).
    assert "app/main.py" in out
    assert "tests/test_main.py" in out
    # README excerpt is decoded from base64 and included.
    assert "A sample project README body." in out


@respx.mock
def test_github_sends_bearer_token_when_configured(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_TOKEN", "ghp_secret")
    _mock_github_full()
    _run(repo._github("owner", "repo"))
    # The meta request must carry the Authorization header derived from the token.
    meta_call = respx.calls[0]
    assert meta_call.request.headers["Authorization"] == "Bearer ghp_secret"


@respx.mock
def test_github_handles_missing_languages_readme_tree(monkeypatch):
    # meta succeeds, but the follow-up calls fail — _summarize degrades cleanly.
    monkeypatch.setattr(config, "GITHUB_TOKEN", "")
    respx.get(_GH_BASE).mock(return_value=httpx.Response(200, json={
        "full_name": "owner/repo", "default_branch": "main",
    }))
    respx.get(_GH_BASE + "/languages").mock(return_value=httpx.Response(403))
    respx.get(_GH_BASE + "/readme").mock(return_value=httpx.Response(404))
    respx.get(_GH_BASE + "/git/trees/main", params={"recursive": "1"}).mock(
        return_value=httpx.Response(404))
    out = _run(repo._github("owner", "repo"))
    assert "Repository: owner/repo" in out
    assert "Primary language(s): unknown" in out
    assert "Top-level entries: (unknown)" in out
    # No README section appended when the readme call failed.
    assert "README (excerpt):" not in out


@respx.mock
def test_github_private_falls_back_to_firecrawl(monkeypatch):
    # Private/not-found repo: meta lacks full_name → scrape the web page.
    monkeypatch.setattr(config, "GITHUB_TOKEN", "")
    monkeypatch.setattr(config, "FIRECRAWL_URL", "https://firecrawl.example")
    respx.get(_GH_BASE).mock(return_value=httpx.Response(404, json={
        "message": "Not Found",
    }))
    scrape = respx.post("https://firecrawl.example/v1/scrape").mock(
        return_value=httpx.Response(200, json={
            "data": {"markdown": "# owner/repo\nScraped page content."}}))
    out = _run(repo._github("owner", "repo"))
    assert scrape.called
    # The fallback scrapes the canonical github.com page for the repo.
    sent = scrape.calls[0].request
    assert b"https://github.com/owner/repo" in sent.content
    assert "Repository page: https://github.com/owner/repo" in out
    assert "Scraped page content." in out


@respx.mock
def test_github_private_without_firecrawl_returns_note(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_TOKEN", "")
    monkeypatch.setattr(config, "FIRECRAWL_URL", "")
    respx.get(_GH_BASE).mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
    out = _run(repo._github("owner", "repo"))
    assert "No structured fetch available" in out
    assert "github.com/owner/repo" in out


@respx.mock
def test_fetch_repo_context_github_url_end_to_end(monkeypatch):
    # Full public path through the entry point fetch_repo_context (URL → regex
    # → _github → _summarize), exercising real httpx with no stubs.
    monkeypatch.setattr(config, "GITHUB_TOKEN", "")
    _mock_github_full()
    out = _run(repo.fetch_repo_context("https://github.com/owner/repo"))
    assert "Repository: owner/repo" in out
    assert "A sample project README body." in out


@respx.mock
def test_firecrawl_reads_top_level_markdown_key(monkeypatch):
    # Some Firecrawl responses put markdown at the top level rather than under data.
    monkeypatch.setattr(config, "FIRECRAWL_URL", "https://firecrawl.example/")
    respx.post("https://firecrawl.example/v1/scrape").mock(
        return_value=httpx.Response(200, json={"markdown": "top-level md"}))
    out = _run(repo._firecrawl("https://gitlab.com/owner/repo"))
    assert "Repository page: https://gitlab.com/owner/repo" in out
    assert "top-level md" in out


@respx.mock
def test_firecrawl_raises_on_5xx(monkeypatch):
    # A 5xx (often an HTML error page) must raise before .json() is attempted.
    monkeypatch.setattr(config, "FIRECRAWL_URL", "https://firecrawl.example")
    respx.post("https://firecrawl.example/v1/scrape").mock(
        return_value=httpx.Response(502, text="<html>bad gateway</html>"))
    with pytest.raises(httpx.HTTPStatusError):
        _run(repo._firecrawl("https://gitlab.com/owner/repo"))


def test_firecrawl_no_url_returns_note(monkeypatch):
    monkeypatch.setattr(config, "FIRECRAWL_URL", "")
    out = _run(repo._firecrawl("https://gitlab.com/owner/repo"))
    assert "No structured fetch available" in out
