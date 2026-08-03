"""Tests for the Jira REST client (app/jira.py) and the export routes
(/api/jira/projects, /api/jira/export).

Jira HTTP is respx-mocked; the TestClient talks to the app over ASGI. No network.
"""

import asyncio
import json
import logging
import time

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import auth, config, jira, main
from app.wizard import state

_CLOUD = "cloud-123"
_REST = f"https://api.atlassian.com/ex/jira/{_CLOUD}/rest/api/3"


def _run(coro):
    return asyncio.run(coro)


# --- app/jira.py REST client -------------------------------------------------

@respx.mock
def test_list_projects_shape_and_pagination():
    def handler(request):
        start = int(request.url.params.get("startAt", "0"))
        if start == 0:
            return httpx.Response(200, json={
                "values": [{"key": "ABC", "name": "Alpha", "id": 1}],
                "isLast": False})
        return httpx.Response(200, json={
            "values": [{"key": "XYZ", "name": "Zed", "id": 2}], "isLast": True})

    respx.get(f"{_REST}/project/search").mock(side_effect=handler)
    projects = _run(jira.list_projects(_CLOUD, "tok"))
    assert [p["key"] for p in projects] == ["ABC", "XYZ"]
    assert projects[0] == {"key": "ABC", "name": "Alpha", "id": "1"}


@respx.mock
def test_list_projects_sends_bearer():
    route = respx.get(f"{_REST}/project/search").mock(
        return_value=httpx.Response(200, json={"values": [], "isLast": True}))
    _run(jira.list_projects(_CLOUD, "tok-abc"))
    assert route.calls[0].request.headers["Authorization"] == "Bearer tok-abc"


@respx.mock
def test_list_projects_non_200_raises():
    respx.get(f"{_REST}/project/search").mock(return_value=httpx.Response(403))
    with pytest.raises(jira.JiraError):
        _run(jira.list_projects(_CLOUD, "tok"))


@respx.mock
def test_create_issue_payload_and_return():
    route = respx.post(f"{_REST}/issue").mock(
        return_value=httpx.Response(201, json={"key": "ABC-7", "id": 1007}))
    adf = {"version": 1, "type": "doc", "content": []}
    out = _run(jira.create_issue(_CLOUD, "tok", project_key="ABC",
                                 summary="My summary", issue_type="Story",
                                 description_adf=adf))
    assert out == {"key": "ABC-7", "id": "1007"}
    sent = json.loads(route.calls[0].request.content.decode())
    assert sent["fields"]["project"]["key"] == "ABC"
    assert sent["fields"]["summary"] == "My summary"
    assert sent["fields"]["issuetype"]["name"] == "Story"
    assert sent["fields"]["description"] == adf


@respx.mock
def test_create_issue_error_raises():
    respx.post(f"{_REST}/issue").mock(return_value=httpx.Response(
        400, json={"errorMessages": [], "errors": {"summary": "is required"}}))
    with pytest.raises(jira.JiraError):
        _run(jira.create_issue(_CLOUD, "tok", project_key="ABC", summary="",
                               issue_type="Task", description_adf={"type": "doc"}))


@respx.mock
def test_create_issue_transport_error_is_wrapped():
    respx.post(f"{_REST}/issue").mock(side_effect=httpx.ConnectError("offline"))
    with pytest.raises(jira.JiraError, match="transport failure"):
        _run(jira.create_issue(
            _CLOUD, "tok", project_key="ABC", summary="x",
            issue_type="Task", description_adf={"type": "doc"}))


@respx.mock
def test_upload_attachment_multipart_and_header():
    route = respx.post(f"{_REST}/issue/ABC-7/attachments").mock(
        return_value=httpx.Response(200, json=[{"id": "10001", "filename": "mega-prompt.md"}]))
    out = _run(jira.upload_attachment(_CLOUD, "tok", "ABC-7", "mega-prompt.md",
                                      "# Brief\n\nbody"))
    assert out[0]["filename"] == "mega-prompt.md"
    req = route.calls[0].request
    assert req.headers["X-Atlassian-Token"] == "no-check"
    body = req.content.decode("utf-8", "replace")
    assert 'name="file"' in body
    assert "mega-prompt.md" in body
    assert "# Brief" in body


def test_browse_url():
    assert jira.browse_url("https://acme.atlassian.net/", "ABC-7") == \
        "https://acme.atlassian.net/browse/ABC-7"


# --- routes ------------------------------------------------------------------

def _atlassian_client(monkeypatch, *, expires_in=3600, refresh="rt"):
    monkeypatch.setattr(config, "ATLASSIAN_OAUTH_CLIENT_ID", "test-atl-id")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    rec = auth.create_auth()
    auth.set_provider(rec, "atlassian", access_token="atl-tok", refresh_token=refresh,
                      expires_at=time.time() + expires_in, user_id=_CLOUD,
                      user_login="Acme",
                      meta={"cloud_id": _CLOUD, "site_url": "https://acme.atlassian.net",
                            "site_name": "Acme"})
    c = TestClient(main.app)
    c.cookies.set(main.AUTH_COOKIE, main._serializer().dumps(rec.id))
    return c


def _final_session():
    s = state.create()
    s.idea = "A todo app"
    s.project_type, s.stakes, s.form_factor = "new", "serious", "web"
    s.phase = "final"
    s.sections = [state.Section(id="overview", title="Overview", instruction="",
                                content="Build it well.")]
    return s


def test_final_page_places_atlassian_login_in_fixed_action_bar(monkeypatch):
    monkeypatch.setattr(config, "ATLASSIAN_OAUTH_CLIENT_ID", "test-atl-id")
    monkeypatch.setattr(config, "ATLASSIAN_OAUTH_CLIENT_SECRET", "test-atl-secret")
    s = _final_session()
    resp = TestClient(main.app).get(f"/sessions/{s.id}")

    assert resp.status_code == 200
    action_bar = resp.text.split('<div class="action-bar">', 1)[1].split("</div>", 1)[0]
    assert "Sign in with Atlassian" in action_bar
    jira_export = resp.text.split('<div id="jira-export"', 1)[1]
    assert "Sign in with Atlassian" not in jira_export


def test_projects_route_unauthenticated_returns_401(monkeypatch):
    monkeypatch.setattr(config, "ATLASSIAN_OAUTH_CLIENT_ID", "test-atl-id")
    c = TestClient(main.app)  # no auth cookie
    resp = c.get("/api/jira/projects")
    assert resp.status_code == 401
    assert "Re-authorize" in resp.text


@respx.mock
def test_projects_route_authed_renders_form(monkeypatch):
    respx.get(f"{_REST}/project/search").mock(return_value=httpx.Response(
        200, json={"values": [{"key": "ABC", "name": "Alpha", "id": 1}], "isLast": True}))
    c = _atlassian_client(monkeypatch)
    s = _final_session()
    resp = c.get(f"/api/jira/projects?sid={s.id}")
    assert resp.status_code == 200
    assert "ABC" in resp.text
    assert 'name="project_key"' in resp.text
    assert 'name="issue_type"' in resp.text
    assert f'value="{s.id}"' in resp.text
    # The access token never leaks into the rendered form.
    assert "atl-tok" not in resp.text


@respx.mock
def test_export_creates_issue_attaches_and_confirms(monkeypatch, caplog):
    issue_route = respx.post(f"{_REST}/issue").mock(
        return_value=httpx.Response(201, json={"key": "ABC-42", "id": 4242}))
    att_route = respx.post(f"{_REST}/issue/ABC-42/attachments").mock(
        return_value=httpx.Response(200, json=[{"id": "1", "filename": "mega-prompt.md"}]))
    c = _atlassian_client(monkeypatch)
    s = _final_session()

    with caplog.at_level(logging.INFO, logger="promptgen.audit"):
        resp = c.post("/api/jira/export",
                      data={"sid": s.id, "project_key": "ABC", "issue_type": "Task"})

    assert resp.status_code == 200
    assert issue_route.called and att_route.called
    assert "ABC-42" in resp.text
    assert "https://acme.atlassian.net/browse/ABC-42" in resp.text
    # ADF description was sent (a doc node, not a raw string).
    sent = json.loads(issue_route.calls[0].request.content.decode())
    assert sent["fields"]["description"]["type"] == "doc"
    # Export was audited with the issue key.
    assert "jira_export" in caplog.text
    assert "ABC-42" in caplog.text


@respx.mock
def test_export_reports_attachment_failure_but_succeeds(monkeypatch):
    respx.post(f"{_REST}/issue").mock(
        return_value=httpx.Response(201, json={"key": "ABC-9", "id": 9}))
    respx.post(f"{_REST}/issue/ABC-9/attachments").mock(
        return_value=httpx.Response(413))  # too large
    c = _atlassian_client(monkeypatch)
    s = _final_session()
    resp = c.post("/api/jira/export",
                  data={"sid": s.id, "project_key": "ABC", "issue_type": "Task"})
    assert resp.status_code == 200
    assert "ABC-9" in resp.text
    assert "failed" in resp.text.lower()  # attachment-failed note


def test_export_unauthenticated_returns_401(monkeypatch):
    monkeypatch.setattr(config, "ATLASSIAN_OAUTH_CLIENT_ID", "test-atl-id")
    c = TestClient(main.app)
    s = _final_session()
    resp = c.post("/api/jira/export",
                  data={"sid": s.id, "project_key": "ABC", "issue_type": "Task"})
    assert resp.status_code == 401
    assert "Re-authorize" in resp.text


def test_export_attachment_timeout_reports_created_issue(monkeypatch):
    monkeypatch.setattr(config, "JIRA_EXPORT_TIMEOUT_MS", 50)

    async def _created(*a, **k):
        return {"key": "ABC-1", "id": "1"}

    async def _attachment_timeout(*a, **k):
        assert 0 < k["timeout"] <= 0.05
        raise jira.JiraError("attachment upload transport failure: timed out")

    monkeypatch.setattr(jira, "create_issue", _created)
    monkeypatch.setattr(jira, "upload_attachment", _attachment_timeout)
    c = _atlassian_client(monkeypatch)
    s = _final_session()
    resp = c.post("/api/jira/export",
                  data={"sid": s.id, "project_key": "ABC", "issue_type": "Task"})
    assert resp.status_code == 200
    assert "ABC-1" in resp.text
    assert "failed" in resp.text.lower()


def test_export_missing_project_reports(monkeypatch):
    c = _atlassian_client(monkeypatch)
    s = _final_session()
    resp = c.post("/api/jira/export",
                  data={"sid": s.id, "project_key": "", "issue_type": "Task"})
    assert resp.status_code == 200
    assert "project" in resp.text.lower()


def test_export_expired_session_reports(monkeypatch):
    c = _atlassian_client(monkeypatch)
    resp = c.post("/api/jira/export",
                  data={"sid": "nope", "project_key": "ABC", "issue_type": "Task"})
    assert resp.status_code == 200
    assert "expired" in resp.text.lower()
