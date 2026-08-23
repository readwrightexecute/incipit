"""Tests for the explicit integration enable flags (app/integrations.py) and
the way they gate the routes and templates in app/main.py.

The four states that matter for each integration are: flag on + credentials
present, flag on + credentials missing, flag off + credentials present, and
flag absent (which must reproduce the pre-flag behaviour). No network.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from app import config, integrations, main
from app.wizard import state


def _github(monkeypatch, *, flag, secret):
    monkeypatch.setattr(config, "GITHUB_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(config, "GITHUB_OAUTH_CLIENT_SECRET", secret)
    monkeypatch.setattr(config, "GITHUB_ENABLED", flag)


def _atlassian(monkeypatch, *, flag, secret):
    monkeypatch.setattr(config, "ATLASSIAN_OAUTH_CLIENT_ID", "test-atl-id")
    monkeypatch.setattr(config, "ATLASSIAN_OAUTH_CLIENT_SECRET", secret)
    monkeypatch.setattr(config, "ATLASSIAN_ENABLED", flag)


# --- config parsing ----------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("1", True), ("true", True), ("TRUE", True), ("yes", True), ("on", True),
    (" true ", True), ("0", False), ("false", False), ("no", False), ("", False),
    ("banana", False),
])
def test_bool_opt_parses_like_the_other_boolean_knobs(monkeypatch, raw, expected):
    monkeypatch.setenv("INCIPIT_TEST_FLAG", raw)
    assert config._bool_opt("INCIPIT_TEST_FLAG") is expected


def test_bool_opt_unset_is_none_not_false(monkeypatch):
    # The tri-state is the whole point: unset must be distinguishable from off.
    monkeypatch.delenv("INCIPIT_TEST_FLAG", raising=False)
    assert config._bool_opt("INCIPIT_TEST_FLAG") is None


# --- resolution --------------------------------------------------------------

@pytest.mark.parametrize("name", ["github", "atlassian"])
def test_flag_on_with_credentials_is_available(monkeypatch, name):
    _github(monkeypatch, flag=True, secret="s")
    _atlassian(monkeypatch, flag=True, secret="s")
    assert integrations.enabled(name)
    assert integrations.configured(name)
    assert integrations.available(name)
    assert not integrations.misconfigured(name)


@pytest.mark.parametrize("name", ["github", "atlassian"])
def test_flag_on_without_credentials_is_unavailable_and_misconfigured(monkeypatch, name):
    _github(monkeypatch, flag=True, secret="")
    _atlassian(monkeypatch, flag=True, secret="")
    assert integrations.enabled(name)
    assert not integrations.configured(name)
    assert not integrations.available(name)
    assert integrations.misconfigured(name)


@pytest.mark.parametrize("name", ["github", "atlassian"])
def test_flag_off_with_credentials_is_unavailable(monkeypatch, name):
    _github(monkeypatch, flag=False, secret="s")
    _atlassian(monkeypatch, flag=False, secret="s")
    assert not integrations.enabled(name)
    assert integrations.configured(name)
    assert not integrations.available(name)
    # Off on purpose is not a misconfiguration, so it must not warn.
    assert not integrations.misconfigured(name)


@pytest.mark.parametrize("name", ["github", "atlassian"])
@pytest.mark.parametrize("secret,expected", [("s", True), ("", False)])
def test_flag_absent_falls_back_to_credentials_present(monkeypatch, name,
                                                       secret, expected):
    _github(monkeypatch, flag=None, secret=secret)
    _atlassian(monkeypatch, flag=None, secret=secret)
    assert integrations.available(name) is expected


def test_openproject_flag_exists_but_can_never_be_available(monkeypatch):
    # The placeholder seam: the flag is honoured, but with no client behind it
    # the integration must never report itself usable.
    monkeypatch.setattr(config, "OPENPROJECT_ENABLED", True)
    assert integrations.enabled("openproject")
    assert not integrations.configured("openproject")
    assert not integrations.available("openproject")


def test_openproject_default_is_off(monkeypatch):
    monkeypatch.setattr(config, "OPENPROJECT_ENABLED", None)
    assert not integrations.enabled("openproject")


def test_unknown_integration_raises():
    with pytest.raises(KeyError):
        integrations.available("gitlab")


# --- startup reporting -------------------------------------------------------

def test_startup_warns_once_about_enabled_but_unconfigured(monkeypatch, caplog):
    _github(monkeypatch, flag=True, secret="")
    _atlassian(monkeypatch, flag=False, secret="s")
    monkeypatch.setattr(config, "OPENPROJECT_ENABLED", False)
    with caplog.at_level(logging.INFO, logger="promptgen.integrations"):
        integrations.log_startup_status()
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    msg = warnings[0].getMessage()
    # Actionable: names the flag and the credentials the operator must set.
    assert "INCIPIT_GITHUB_ENABLED" in msg
    assert "INCIPIT_GITHUB_OAUTH_CLIENT_SECRET" in msg


def test_status_reports_every_integration(monkeypatch):
    _github(monkeypatch, flag=True, secret="s")
    _atlassian(monkeypatch, flag=False, secret="s")
    monkeypatch.setattr(config, "OPENPROJECT_ENABLED", None)
    st = integrations.status()
    assert set(st) == {"github", "atlassian", "openproject"}
    assert st["github"] == {"enabled": True, "configured": True, "available": True}
    assert st["atlassian"]["available"] is False
    assert st["openproject"]["available"] is False


# --- route + template gating -------------------------------------------------

def test_healthz_reports_capability(monkeypatch):
    _github(monkeypatch, flag=True, secret="s")
    _atlassian(monkeypatch, flag=False, secret="s")
    body = TestClient(main.app).get("/healthz").json()
    assert body["integrations"]["github"]["available"] is True
    assert body["integrations"]["atlassian"]["available"] is False


@pytest.mark.parametrize("path", ["/auth/github/login", "/auth/github/callback",
                                  "/api/github/repos"])
def test_github_routes_503_when_flag_off(monkeypatch, path):
    _github(monkeypatch, flag=False, secret="s")
    resp = TestClient(main.app).get(path, follow_redirects=False)
    assert resp.status_code == 503
    assert "GitHub" in resp.text


@pytest.mark.parametrize("path", ["/auth/atlassian/login", "/auth/atlassian/callback",
                                  "/api/jira/projects"])
def test_atlassian_routes_503_when_flag_off(monkeypatch, path):
    _atlassian(monkeypatch, flag=False, secret="s")
    resp = TestClient(main.app).get(path, follow_redirects=False)
    assert resp.status_code == 503


def test_jira_export_503_when_flag_off(monkeypatch):
    _atlassian(monkeypatch, flag=False, secret="s")
    resp = TestClient(main.app).post(
        "/api/jira/export",
        data={"sid": "whatever", "project_key": "ABC", "issue_type": "Task"})
    assert resp.status_code == 503


def test_github_login_button_hidden_when_flag_off(monkeypatch):
    _github(monkeypatch, flag=False, secret="s")
    body = TestClient(main.app).get("/").text
    assert "Login with GitHub" not in body


def test_github_login_button_shown_when_enabled(monkeypatch):
    _github(monkeypatch, flag=True, secret="s")
    body = TestClient(main.app).get("/").text
    assert "Login with GitHub" in body


def _final_session():
    s = state.create()
    s.idea = "A todo app"
    s.project_type, s.stakes, s.form_factor = "new", "serious", "web"
    s.phase = "final"
    s.sections = [state.Section(id="overview", title="Overview", instruction="",
                                content="Build it well.")]
    return s


def test_jira_export_panel_hidden_when_flag_off(monkeypatch):
    _atlassian(monkeypatch, flag=False, secret="s")
    s = _final_session()
    body = TestClient(main.app).get(f"/sessions/{s.id}").text
    assert "Sign in with Atlassian" not in body
    assert 'id="jira-export"' not in body


def test_jira_export_panel_shown_when_enabled(monkeypatch):
    _atlassian(monkeypatch, flag=True, secret="s")
    s = _final_session()
    body = TestClient(main.app).get(f"/sessions/{s.id}").text
    assert "Sign in with Atlassian" in body
    assert 'id="jira-export"' in body
