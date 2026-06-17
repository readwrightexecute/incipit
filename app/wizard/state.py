"""In-memory session store. Single replica, single user — losing in-flight
wizards on pod restart is an accepted trade-off (final output is downloadable)."""

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from app import config


@dataclass
class QA:
    question: str
    assumption: str
    answer: str = ""  # empty → assumption stands


@dataclass
class Section:
    id: str
    title: str
    instruction: str
    content: str = ""
    status: str = "pending"  # pending | generating | done | error
    history: list[str] = field(default_factory=list)


@dataclass
class PartyMessage:
    """One bubble in the party-mode group chat."""
    persona_id: str
    name: str
    emoji: str
    role: str
    text: str
    kind: str = "persona"  # persona | facilitator | system


@dataclass
class PartyChange:
    """A consensus edit the user can approve/deny. Applied via the refine pipeline."""
    id: str
    section_id: str
    section_title: str
    instruction: str
    rationale: str = ""
    status: str = "pending"  # pending | applying | applied | denied


@dataclass
class PartyQAChange:
    """A round-table suggestion about the clarifying questions (step 2). Either a
    new question to add, or a proposed answer to an existing one."""
    id: str
    kind: str           # add_question | suggest_answer
    rationale: str = ""
    status: str = "pending"  # pending | applied | denied
    # add_question:
    question: str = ""
    assumption: str = ""
    # suggest_answer:
    target: int = -1    # 0-based index into Session.qas
    answer: str = ""


@dataclass
class Session:
    id: str
    created: float
    idea: str = ""
    project_type: str = ""
    stakes: str = ""
    form_factor: str = ""
    repo_url: str = ""       # existing projects: link to the codebase
    repo_context: str = ""   # fetched repo summary injected into drafting prompts
    qas: list[QA] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    phase: str = "idea"  # idea | clarify | sections | final
    # Party mode (round-table review on the final spec).
    auto_party: bool = False  # set by "Submit & Party": convene the round table once the draft lands
    party_status: str = "idle"  # idle | running | ready | error
    party_messages: list[PartyMessage] = field(default_factory=list)
    party_changes: list[PartyChange] = field(default_factory=list)
    # Question-review party (step 2): suggested new questions / answers.
    party_qa_changes: list[PartyQAChange] = field(default_factory=list)
    # Post-processing QA (final page): on-demand LLM critique of the spec.
    qa_review: list = field(default_factory=list)  # [{id, severity, category, text, fix_status, verify}]
    qa_review_status: str = "idle"  # idle | running | ready | error
    qa_fix_status: str = "idle"  # idle | running | ready | error — "implement fixes"
    qa_verify_status: str = "idle"  # idle | running | ready | error — "verify fixes"
    # SSE fan-out: one queue per open /events connection. A single shared
    # queue silently splits events between stale and live connections.
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    error: str = ""

    def section(self, sid: str) -> Section | None:
        return next((s for s in self.sections if s.id == sid), None)

    def party_change(self, cid: str) -> "PartyChange | None":
        return next((c for c in self.party_changes if c.id == cid), None)

    def party_qa_change(self, cid: str) -> "PartyQAChange | None":
        return next((c for c in self.party_qa_changes if c.id == cid), None)

    def qa_finding(self, fid: str) -> dict | None:
        return next((f for f in self.qa_review if f.get("id") == fid), None)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self.subscribers:
            self.subscribers.remove(q)

    def publish(self, event: str, data: str = "") -> None:
        for q in self.subscribers:
            q.put_nowait({"event": event, "data": data})


_sessions: dict[str, Session] = {}


def create() -> Session:
    _sweep()
    s = Session(id=uuid.uuid4().hex[:12], created=time.time())
    _sessions[s.id] = s
    return s


def get(session_id: str) -> Session | None:
    return _sessions.get(session_id)


def _sweep() -> None:
    cutoff = time.time() - config.SESSION_TTL
    for sid in [k for k, v in _sessions.items() if v.created < cutoff]:
        del _sessions[sid]
