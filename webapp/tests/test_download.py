"""Route-level contracts for markdown export endpoints."""

import asyncio

from app import main
from app.wizard import state
from app.wizard.state import Section


def test_download_md_still_returns_flat_implementation_brief():
    s = state.create()
    s.idea = "A todo app"
    s.project_type = "new"
    s.stakes = "internal"
    s.form_factor = "web app"
    s.sections = [
        Section(
            id="functional_requirements",
            title="Functional Requirements",
            instruction="",
            content="FR1: Users can create todos.",
        ),
        Section(
            id="acceptance_criteria",
            title="Acceptance Criteria",
            instruction="",
            content="AC-FR1: Given a todo, when saved, then it appears in the list.",
        ),
    ]

    response = asyncio.run(main.download(s.id))
    body = response.body.decode()

    assert response.media_type == "text/markdown"
    assert response.headers["content-disposition"] == 'attachment; filename="mega-prompt.md"'
    assert body.startswith("# Implementation Brief")
    assert "## Planning Summary" in body
    assert "## Functional Requirements" in body
    assert "- FR1: Users can create todos." in body
    assert "# Jira Export" not in body
    assert "## Epic" not in body
    assert "## Child Stories" not in body


def test_download_jira_md_returns_jira_export():
    s = state.create()
    s.idea = "A todo app"
    s.project_type = "new"
    s.stakes = "internal"
    s.form_factor = "web app"
    s.sections = [
        Section(
            id="functional_requirements",
            title="Functional Requirements",
            instruction="",
            content="1. **FR1:** Users can create todos.",
        ),
        Section(
            id="acceptance_criteria",
            title="Acceptance Criteria",
            instruction="",
            content="- **AC-FR1:** Given a todo, when saved, then it appears in the list.",
        ),
    ]

    response = asyncio.run(main.download_jira(s.id))
    body = response.body.decode()

    assert response.media_type == "text/markdown"
    assert response.headers["content-disposition"] == 'attachment; filename="jira-export.md"'
    assert body.startswith("# Jira Export")
    assert "## Epic" in body
    assert "## Child Stories" in body
    assert "### Story FR1" in body
    assert "Title: Users can create todos." in body
    assert "Covers: [FR1]" in body
    assert "- **Story summary:** Users can create todos." in body
    assert "Users can create todos." in body
    assert "AC-FR1: Given a todo" in body
    assert "# Implementation Brief" not in body


def test_download_jira_md_unknown_session_returns_404():
    response = asyncio.run(main.download_jira("missing-session"))

    assert response.status_code == 404
