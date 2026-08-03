"""Fetch a compact, token-budgeted summary of an existing repository so the
spec drafting can be grounded in the real codebase.

Strategy: GitHub REST first (public repos, no auth needed; optional
`INCIPIT_GITHUB_TOKEN` lifts the anonymous rate limit). For non-GitHub hosts
or API failures, fall back to homelab Firecrawl (`INCIPIT_FIRECRAWL_URL`) to
scrape the repo page. Best-effort throughout — a fetch failure never blocks
drafting; it returns a short note instead.
"""

import asyncio
import base64
import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

import httpx

from app import config

log = logging.getLogger("promptgen.repo")

# owner/repo from https://github.com/owner/repo(.git)(/...) or git@github.com:owner/repo
_GITHUB_RE = re.compile(r"github\.com[/:]+([^/\s]+)/([^/\s#?]+)", re.I)

GITHUB_API = "https://api.github.com"

# Listing private repos for a signed-in user is interactive (NFR2): keep it
# snappy with a tight timeout, and retry once after a short backoff to ride out
# a transient blip rather than failing the whole picker.
_REPOS_TIMEOUT = 3.0   # 3000ms
_REPOS_BACKOFF = 1.5   # 1500ms
_REPOS_MAX_PAGES = 10  # safety cap: up to 1000 private repos


class GitHubAuthError(Exception):
    """Raised when GitHub returns 401 for an authenticated request (token
    missing, expired, or lacking scope) so callers can surface a re-auth modal
    instead of a generic 500."""


async def fetch_repo_context(url: str) -> str:
    """Return a compact repo summary for prompt injection, or a short note on
    failure. Never raises."""
    url = (url or "").strip()
    if not url:
        return ""
    try:
        m = _GITHUB_RE.search(url)
        if m:
            owner = m.group(1)
            repo = m.group(2)
            if repo.endswith(".git"):
                repo = repo[:-4]
            return await _github(owner, repo)
        # SSRF guard: only http(s) URLs reach the scraper. Blocks file://,
        # gopher://, etc. from being forwarded to the Firecrawl service.
        if not re.match(r"https?://", url, re.I):
            return f"(Won't fetch non-http(s) URL for repo context: {url})"
        # SSRF guard: resolve the host and reject private / loopback /
        # link-local / reserved targets before forwarding to Firecrawl, so the
        # scraper can't be pointed at internal services.
        if not await _host_is_public(url):
            return (f"(Won't fetch repo context from a private or unresolvable "
                    f"host: {url})")
        return await _firecrawl(url)
    except Exception as e:  # noqa: BLE001 — best-effort; surface as context note
        log.warning("repo fetch failed for %s: %s", url, e)
        return f"(Could not fetch repo context from {url}: {e})"


def _clip(text: str) -> str:
    return text[: config.REPO_CONTEXT_MAX_CHARS]


async def _host_is_public(url: str) -> bool:
    """Resolve url's host and return False if any resolved address is private,
    loopback, link-local, reserved, multicast, or unspecified (RFC1918,
    127.0.0.0/8, 169.254.0.0/16, ::1, fc00::/7, etc.) — i.e. an SSRF target."""
    host = urlparse(url).hostname
    if not host:
        return False
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.run_in_executor(None, socket.getaddrinfo, host, None)
    except socket.gaierror:
        return False  # unresolvable → don't forward
    for info in infos:
        raw_ip = info[4][0].split("%")[0]  # strip any IPv6 zone id
        try:
            addr = ipaddress.ip_address(raw_ip)
        except ValueError:
            return False
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False
    return True


async def fetch_selected_repo_context(full_name: str, token: str = "") -> str:
    """Compact summary for one private repo the user picked (owner/name), using
    their OAuth token. Best-effort: never raises, so one bad repo can't block
    drafting."""
    try:
        owner, _, name = (full_name or "").strip().partition("/")
        if not owner or not name:
            return ""
        return await _github(owner, name, token=token)
    except Exception as e:  # noqa: BLE001 — best-effort; surface as a context note
        log.warning("selected repo fetch failed for %s: %s", full_name, e)
        return f"(Could not fetch repo context for {full_name}: {e})"


async def list_private_repos(token: str) -> list[dict]:
    """Return the signed-in user's private repos (paginated). Raises
    GitHubAuthError on 401 so the route can answer 401 and the UI can prompt a
    re-authorize. Retries once after a short backoff on a transient error."""
    if not token:
        raise GitHubAuthError("no GitHub token for the current session")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "incipit",
        "Authorization": f"Bearer {token}",
    }
    repos: list[dict] = []
    async with httpx.AsyncClient(timeout=_REPOS_TIMEOUT, headers=headers,
                                 follow_redirects=True) as c:
        for page in range(1, _REPOS_MAX_PAGES + 1):
            params = {"visibility": "private", "per_page": 100, "page": page,
                      "sort": "updated"}
            batch = await _get_repos_page(c, params)
            for r in batch:
                repos.append({
                    "full_name": r.get("full_name", ""),
                    "name": r.get("name", ""),
                    "private": bool(r.get("private")),
                    "description": r.get("description") or "",
                    "html_url": r.get("html_url", ""),
                    "default_branch": r.get("default_branch", "main"),
                })
            if len(batch) < 100:  # last page
                break
    return repos


async def _get_repos_page(c: httpx.AsyncClient, params: dict) -> list:
    """One GET /user/repos page with retry-once + backoff. 401 → GitHubAuthError."""
    url = f"{GITHUB_API}/user/repos"
    try:
        return await _repos_request(c, url, params)
    except GitHubAuthError:
        raise  # an auth failure won't fix itself on retry
    except httpx.HTTPError:
        await asyncio.sleep(_REPOS_BACKOFF)
        return await _repos_request(c, url, params)  # retry once; may raise


async def _repos_request(c: httpx.AsyncClient, url: str, params: dict) -> list:
    r = await c.get(url, params=params)
    if r.status_code == 401:
        raise GitHubAuthError("GitHub rejected the token (401)")
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


async def _github(owner: str, repo: str, token: str = "") -> str:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "promptgen"}
    # A per-user OAuth token (private-repo grounding) takes precedence over the
    # optional anonymous-rate-limit token from config.
    auth_token = token or config.GITHUB_TOKEN
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    base = f"https://api.github.com/repos/{owner}/{repo}"
    async with httpx.AsyncClient(timeout=config.REPO_TIMEOUT, headers=headers,
                                 follow_redirects=True) as c:
        meta_r = await c.get(base)
        meta = meta_r.json() if meta_r.status_code == 200 else {}
        if "full_name" not in meta:
            # private / not found / rate-limited → try scraping the web page
            return await _firecrawl(f"https://github.com/{owner}/{repo}")

        default_branch = meta.get("default_branch", "main")

        langs: list[str] = []
        lr = await c.get(base + "/languages")
        if lr.status_code == 200:
            langs = list(lr.json().keys())

        readme = ""
        rr = await c.get(base + "/readme")
        if rr.status_code == 200:
            try:
                readme = base64.b64decode(rr.json().get("content", "")).decode(
                    "utf-8", "replace")
            except Exception:  # noqa: BLE001
                readme = ""

        paths: list[str] = []
        tr = await c.get(base + f"/git/trees/{default_branch}?recursive=1")
        if tr.status_code == 200:
            paths = [n["path"] for n in tr.json().get("tree", [])
                     if n.get("type") == "blob"]

    return _summarize(owner, repo, meta, langs, paths, readme)


def _summarize(owner: str, repo: str, meta: dict, langs: list[str],
               paths: list[str], readme: str) -> str:
    top = sorted({p.split("/")[0] for p in paths})
    parts = [
        f"Repository: {owner}/{repo}",
        f"Description: {meta.get('description') or '(none)'}",
        f"Primary language(s): {', '.join(langs[:6]) or 'unknown'}",
        f"Topics: {', '.join(meta.get('topics', [])) or '(none)'}",
        f"Top-level entries: {', '.join(top[:40]) or '(unknown)'}",
        "Files (sample):",
        "\n".join(paths[:120]),
    ]
    if readme:
        parts += ["", "README (excerpt):", readme[:3000]]
    return _clip("\n".join(parts))


async def _firecrawl(url: str) -> str:
    if not config.FIRECRAWL_URL:
        return (f"(No structured fetch available for {url}; the downstream "
                f"coding agent should read the repo directly.)")
    endpoint = config.FIRECRAWL_URL.rstrip("/") + "/v1/scrape"
    async with httpx.AsyncClient(timeout=config.REPO_TIMEOUT * 2) as c:
        r = await c.post(endpoint, json={"url": url, "formats": ["markdown"]})
        r.raise_for_status()  # 5xx often returns HTML → guard before .json()
        data = r.json()
        md = (data.get("data") or {}).get("markdown") or data.get("markdown") or ""
    return _clip(f"Repository page: {url}\n\n{md}")
