"""Offline tests for route handlers in app/main.py (no network, no LLM).

Handlers are driven directly with a minimal fake Request; background work is
suppressed by pre-setting the relevant status so _spawn is never reached.
"""

import asyncio

from app import main
from app.wizard import state
from app.wizard.state import QA


class _FakeRequest:
    """Stand-in for starlette.Request: the handlers under test only call
    .form(); template rendering merely stores the request in the context."""

    def __init__(self, form: dict | None = None):
        self._form = form or {}

    async def form(self) -> dict:
        return self._form


def test_party_questions_persists_typed_answers():
    """Convening the question-review party must save the answers submitted
    with the form — the personas review them and the form re-renders from
    s.qas, so ignoring them both hides them from the party and wipes the
    user's typed text."""
    s = state.create()
    s.qas = [QA(question="Q1", assumption="A1"),
             QA(question="Q2", assumption="A2")]
    s.party_status = "running"  # already running -> handler skips _spawn
    req = _FakeRequest({"answer_0": "  my answer  ", "answer_1": ""})
    asyncio.run(main.party_questions_start(req, s.id))
    assert s.qas[0].answer == "my answer"
    assert s.qas[1].answer == ""


def test_party_questions_tolerates_missing_fields():
    """A POST without answer fields (e.g. a stale client) must not clobber
    previously saved answers."""
    s = state.create()
    s.qas = [QA(question="Q1", assumption="A1", answer="kept")]
    s.party_status = "running"
    asyncio.run(main.party_questions_start(_FakeRequest(), s.id))
    assert s.qas[0].answer == "kept"
