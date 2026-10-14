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
                                 description_adf=adf, parent_key="ABC-1"))
    assert out == {"key": "ABC-7", "id": "1007"}
    sent = json.loads(route.calls[0].request.content.decode())
    assert sent["fields"]["project"]["key"] == "ABC"
    assert sent["fields"]["summary"] == "My summary"
    assert sent["fields"]["issuetype"]["name"] == "Story"
    assert sent["fields"]["description"] == adf
    assert sent["fields"]["parent"]["key"] == "ABC-1"


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
    assert resp.text.index('<div id="jira-export"') < resp.text.index(
        '<div class="section-content" id="mega-prompt"')


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
    assert 'name="issue_type"' not in resp.text
    assert f'value="{s.id}"' in resp.text
    # The access token never leaks into the rendered form.
    assert "atl-tok" not in resp.text


@respx.mock
def test_export_creates_issue_attaches_and_confirms(monkeypatch, caplog):
    issue_route = respx.post(f"{_REST}/issue").mock(
        side_effect=[
            httpx.Response(201, json={"key": "ABC-42", "id": 4242}),
            httpx.Response(201, json={"key": "ABC-43", "id": 4243}),
        ])
    att_route = respx.post(f"{_REST}/issue/ABC-42/attachments").mock(
        return_value=httpx.Response(200, json=[{"id": "1", "filename": "mega-prompt.md"}]))
    c = _atlassian_client(monkeypatch)
    s = _final_session()

    with caplog.at_level(logging.INFO, logger="incipit.audit"):
        resp = c.post("/api/jira/export",
                      data={"sid": s.id, "project_key": "ABC"})

    assert resp.status_code == 200
    assert issue_route.called and att_route.called
    assert "ABC-42" in resp.text
    assert "ABC-43" in resp.text
    assert "https://acme.atlassian.net/browse/ABC-42" in resp.text
    assert "https://acme.atlassian.net/browse/ABC-43" in resp.text
    # The Epic and child Story are both ADF-backed Jira issues.
    epic = json.loads(issue_route.calls[0].request.content.decode())
    story = json.loads(issue_route.calls[1].request.content.decode())
    assert epic["fields"]["issuetype"]["name"] == "Epic"
    assert epic["fields"]["summary"] == "A todo app"
    assert not epic["fields"]["summary"].startswith("Incipit brief:")
    assert epic["fields"]["description"]["type"] == "doc"
    assert story["fields"]["issuetype"]["name"] == "Story"
    assert story["fields"]["parent"]["key"] == "ABC-42"
    assert story["fields"]["description"]["type"] == "doc"
    # Export was audited with the issue key.
    assert "jira_export" in caplog.text
    assert "ABC-42" in caplog.text


@respx.mock
def test_export_reports_attachment_failure_but_succeeds(monkeypatch):
    respx.post(f"{_REST}/issue").mock(
        side_effect=[
            httpx.Response(201, json={"key": "ABC-9", "id": 9}),
            httpx.Response(201, json={"key": "ABC-10", "id": 10}),
        ])
    respx.post(f"{_REST}/issue/ABC-9/attachments").mock(
        return_value=httpx.Response(413))  # too large
    c = _atlassian_client(monkeypatch)
    s = _final_session()
    resp = c.post("/api/jira/export",
                  data={"sid": s.id, "project_key": "ABC"})
    assert resp.status_code == 200
    assert "ABC-9" in resp.text
    assert "ABC-10" in resp.text
    assert "failed" in resp.text.lower()  # attachment-failed note


@respx.mock
def test_export_reports_partial_story_failure_without_losing_epic(monkeypatch, caplog):
    issue_route = respx.post(f"{_REST}/issue").mock(
        side_effect=[
            httpx.Response(201, json={"key": "ABC-20", "id": 20}),
            httpx.Response(201, json={"key": "ABC-21", "id": 21}),
            httpx.Response(400, json={"errors": {"parent": "cannot link story"}}),
        ])
    respx.post(f"{_REST}/issue/ABC-20/attachments").mock(
        return_value=httpx.Response(200, json=[{"id": "1"}]))
    c = _atlassian_client(monkeypatch)
    s = _final_session()
    s.sections = [state.Section(
        id="requirements",
        title="Functional Requirements",
        instruction="",
        content="FR1: Create the first story.\nFR2: Create the second story.",
    )]

    with caplog.at_level(logging.INFO, logger="incipit.audit"):
        resp = c.post("/api/jira/export", data={"sid": s.id, "project_key": "ABC"})

    assert resp.status_code == 200
    assert issue_route.call_count == 3
    assert "ABC-20" in resp.text
    assert "ABC-21" in resp.text
    assert "1 child story was not created" in resp.text
    assert "check Jira before retrying" in resp.text
    assert "jira_export" in caplog.text
    assert "ABC-20" in caplog.text


@respx.mock
def test_export_reports_partial_story_failure_mid_list(monkeypatch):
    """Failure on a non-last story must report the correct not-created count."""
    issue_route = respx.post(f"{_REST}/issue").mock(
        side_effect=[
            httpx.Response(201, json={"key": "ABC-40", "id": 40}),  # Epic
            httpx.Response(201, json={"key": "ABC-41", "id": 41}),  # Story 1
            httpx.Response(400, json={"errors": {"summary": "bad"}}),  # Story 2 fails
        ])
    respx.post(f"{_REST}/issue/ABC-40/attachments").mock(
        return_value=httpx.Response(200, json=[{"id": "1"}]))
    c = _atlassian_client(monkeypatch)
    s = _final_session()
    s.sections = [state.Section(
        id="requirements",
        title="Functional Requirements",
        instruction="",
        content="FR1: First story.\nFR2: Second story.\nFR3: Third story.",
    )]

    resp = c.post("/api/jira/export", data={"sid": s.id, "project_key": "ABC"})

    assert resp.status_code == 200
    # Epic + 1 story created + 1 story failed = 3 calls; story 3 never attempted.
    assert issue_route.call_count == 3
    assert "ABC-41" in resp.text
    # 2 stories not created (the failed one + the untried one).
    assert "2 child stories were not created" in resp.text
    assert "check Jira before retrying" in resp.text


@respx.mock
def test_export_normalizes_fallback_story_summary(monkeypatch):
    issue_route = respx.post(f"{_REST}/issue").mock(
        side_effect=[
            httpx.Response(201, json={"key": "ABC-30", "id": 30}),
            httpx.Response(201, json={"key": "ABC-31", "id": 31}),
        ])
    respx.post(f"{_REST}/issue/ABC-30/attachments").mock(
        return_value=httpx.Response(200, json=[{"id": "1"}]))
    c = _atlassian_client(monkeypatch)
    s = _final_session()
    s.idea = "Line one\n\nLine two"

    resp = c.post("/api/jira/export", data={"sid": s.id, "project_key": "ABC"})

    assert resp.status_code == 200
    story = json.loads(issue_route.calls[1].request.content.decode())
    assert story["fields"]["summary"] == "Line one Line two"


@respx.mock
def test_export_normalizes_requirement_id_in_story_summary(monkeypatch):
    issue_route = respx.post(f"{_REST}/issue").mock(
        side_effect=[
            httpx.Response(201, json={"key": "ABC-50", "id": 50}),
            httpx.Response(201, json={"key": "ABC-51", "id": 51}),
        ])
    respx.post(f"{_REST}/issue/ABC-50/attachments").mock(
        return_value=httpx.Response(200, json=[{"id": "1"}]))
    c = _atlassian_client(monkeypatch)
    s = _final_session()
    s.sections = [state.Section(
        id="requirements",
        title="Functional Requirements",
        instruction="",
        content="FR-1: Preserve mapped acceptance criteria.",
    )]

    resp = c.post("/api/jira/export", data={"sid": s.id, "project_key": "ABC"})

    assert resp.status_code == 200
    story = json.loads(issue_route.calls[1].request.content.decode())
    assert story["fields"]["summary"].startswith("FR1: ")


def test_export_recomputes_budget_after_child_story_failure(monkeypatch):
    clock = {"now": 100.0}
    calls = []
    uploads = []

    class FakeLoop:
        def time(self):
            return clock["now"]

    async def _create_issue(*args, **kwargs):
        calls.append(kwargs)
        if kwargs["issue_type"] == "Epic":
            clock["now"] += 1.0
            return {"key": "ABC-60", "id": "60"}
        clock["now"] += 0.75
        raise jira.JiraError("story creation timed out")

    async def _upload_attachment(*args, **kwargs):
        uploads.append(kwargs)

    monkeypatch.setattr(main.asyncio, "get_running_loop", lambda: FakeLoop())
    monkeypatch.setattr(jira, "create_issue", _create_issue)
    monkeypatch.setattr(jira, "upload_attachment", _upload_attachment)

    story = main.flow.JiraStoryDraft(
        key="FR1",
        summary="Create a story.",
        description="Create a story.",
        acceptance_criteria=[],
    )

    result = _run(main._export_to_jira(
        _CLOUD,
        "tok",
        "https://acme.atlassian.net",
        "ABC",
        "Epic summary",
        {"version": 1, "type": "doc", "content": []},
        "# Brief",
        [story],
        timeout=2.0,
    ))

    assert calls[0]["timeout"] == 2.0
    assert calls[1]["timeout"] == 1.0
    assert result["failed_stories"] == 1
    assert result["attached"] is False
    assert uploads == []


def test_export_unauthenticated_returns_401(monkeypatch):
    monkeypatch.setattr(config, "ATLASSIAN_OAUTH_CLIENT_ID", "test-atl-id")
    c = TestClient(main.app)
    s = _final_session()
    resp = c.post("/api/jira/export",
                  data={"sid": s.id, "project_key": "ABC"})
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
                  data={"sid": s.id, "project_key": "ABC"})
    assert resp.status_code == 200
    assert "ABC-1" in resp.text
    assert "failed" in resp.text.lower()


def test_export_missing_project_reports(monkeypatch):
    c = _atlassian_client(monkeypatch)
    s = _final_session()
    resp = c.post("/api/jira/export",
                  data={"sid": s.id, "project_key": ""})
    assert resp.status_code == 200
    assert "project" in resp.text.lower()


def test_export_expired_session_reports(monkeypatch):
    c = _atlassian_client(monkeypatch)
    resp = c.post("/api/jira/export",
                  data={"sid": "nope", "project_key": "ABC"})
    assert resp.status_code == 200
    assert "expired" in resp.text.lower()
