"""Jira Cloud REST v3 client for the per-user export-to-Jira flow.

Every call targets ``https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/…``
with the signed-in user's OAuth Bearer token. This module is a *pure* REST
client — the access token + cloudId come in, results go out. The auth store and
token-refresh live in app/main.py (so jira.py never imports main.py and there's
no circular dependency).
"""

import logging

import httpx

from app import config

log = logging.getLogger("promptgen.jira")

API_BASE = "https://api.atlassian.com/ex/jira"
_PROJECT_PAGE = 50
_MAX_PROJECT_PAGES = 20  # safety cap: up to 1000 projects


class JiraError(Exception):
    """A Jira REST call failed (non-2xx response or transport error)."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _base(cloud_id: str) -> str:
    return f"{API_BASE}/{cloud_id}/rest/api/3"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _timeout(timeout_s: float | None) -> float:
    return timeout_s if timeout_s is not None else float(config.REPO_TIMEOUT)


def browse_url(site_url: str, key: str) -> str:
    """The human-facing issue URL ({site}/browse/KEY)."""
    return f"{(site_url or '').rstrip('/')}/browse/{key}"


async def list_projects(cloud_id: str, token: str, *,
                        timeout: float | None = None) -> list[dict]:
    """Return the user's projects (paginated via project/search) for the picker.
    Each item is {key, name, id}. Raises JiraError on a non-200 response."""
    url = f"{_base(cloud_id)}/project/search"
    projects: list[dict] = []
    async with httpx.AsyncClient(timeout=_timeout(timeout),
                                 headers=_headers(token)) as c:
        start = 0
        for _ in range(_MAX_PROJECT_PAGES):
            try:
                r = await c.get(
                    url, params={"startAt": start, "maxResults": _PROJECT_PAGE})
            except httpx.HTTPError as e:
                raise JiraError(f"project/search transport failure: {e}") from e
            if r.status_code != 200:
                raise JiraError(
                    f"project/search returned {r.status_code}",
                    status_code=r.status_code)
            try:
                data = r.json()
            except ValueError as e:
                raise JiraError("project/search returned invalid JSON") from e
            values = data.get("values", []) or []
            for p in values:
                projects.append({"key": p.get("key", ""),
                                 "name": p.get("name", ""),
                                 "id": str(p.get("id", ""))})
            if data.get("isLast", True) or not values:
                break
            start += len(values)
    return projects


async def create_issue(cloud_id: str, token: str, *, project_key: str,
                       summary: str, issue_type: str, description_adf: dict,
                       timeout: float | None = None) -> dict:
    """Create an issue with an ADF description. Returns {key, id}. Raises
    JiraError on a non-2xx response."""
    url = f"{_base(cloud_id)}/issue"
    payload = {"fields": {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
        "description": description_adf,
    }}
    headers = {**_headers(token), "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=_timeout(timeout), headers=headers) as c:
            r = await c.post(url, json=payload)
    except httpx.HTTPError as e:
        raise JiraError(f"create issue transport failure: {e}") from e
    if r.status_code not in (200, 201):
        raise JiraError(
            f"create issue failed ({r.status_code}): {_error_text(r)}",
            status_code=r.status_code)
    try:
        data = r.json()
    except ValueError as e:
        raise JiraError("create issue returned invalid JSON") from e
    return {"key": data.get("key", ""), "id": str(data.get("id", ""))}


async def upload_attachment(cloud_id: str, token: str, issue_key: str,
                            filename: str, content: str | bytes,
                            timeout: float | None = None) -> list:
    """Attach a file to an issue (multipart `file`). Jira requires the
    X-Atlassian-Token: no-check header for attachment uploads. Raises JiraError
    on a non-2xx response."""
    url = f"{_base(cloud_id)}/issue/{issue_key}/attachments"
    headers = {**_headers(token), "X-Atlassian-Token": "no-check"}
    blob = content.encode("utf-8") if isinstance(content, str) else content
    files = {"file": (filename, blob, "text/markdown")}
    try:
        async with httpx.AsyncClient(timeout=_timeout(timeout), headers=headers) as c:
            r = await c.post(url, files=files)
    except httpx.HTTPError as e:
        raise JiraError(f"attachment upload transport failure: {e}") from e
    if r.status_code not in (200, 201):
        raise JiraError(
            f"attachment upload failed ({r.status_code}): {_error_text(r)}",
            status_code=r.status_code)
    try:
        return r.json()
    except ValueError as e:
        raise JiraError("attachment upload returned invalid JSON") from e


def _error_text(r: httpx.Response) -> str:
    """A short, log-safe snippet of a Jira error body (no secrets involved)."""
    try:
        data = r.json()
    except ValueError:
        return r.text[:200]
    msgs = data.get("errorMessages") or []
    errs = data.get("errors") or {}
    parts = list(msgs) + [f"{k}: {v}" for k, v in errs.items()]
    return "; ".join(parts)[:300] or r.text[:200]
