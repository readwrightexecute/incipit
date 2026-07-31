"""Fetch a compact, token-budgeted summary of an existing repository so the
spec drafting can be grounded in the real codebase.

Strategy: GitHub REST first (public repos, no auth needed; optional
`PROMPTGEN_GITHUB_TOKEN` lifts the anonymous rate limit). For non-GitHub hosts
or API failures, fall back to homelab Firecrawl (`PROMPTGEN_FIRECRAWL_URL`) to
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


async def _github(owner: str, repo: str) -> str:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "promptgen"}
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
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
