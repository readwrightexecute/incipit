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
class Session:
    id: str
    created: float
    idea: str = ""
    stakes: str = ""
    form_factor: str = ""
    qas: list[QA] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    phase: str = "idea"  # idea | calibrate | clarify | sections | final
    # Party mode (round-table review on the final spec).
    party_status: str = "idle"  # idle | running | ready | error
    party_messages: list[PartyMessage] = field(default_factory=list)
    party_changes: list[PartyChange] = field(default_factory=list)
    # SSE fan-out: one queue per open /events connection. A single shared
    # queue silently splits events between stale and live connections.
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    error: str = ""

    def section(self, sid: str) -> Section | None:
        return next((s for s in self.sections if s.id == sid), None)

    def party_change(self, cid: str) -> "PartyChange | None":
        return next((c for c in self.party_changes if c.id == cid), None)

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
