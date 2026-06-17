"""Wizard orchestration: background jobs that call the LLM and push SSE events
onto the session queue. The UI listens on /sessions/{id}/events."""

import asyncio
import html
import logging
import re
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

from app import config, repo
from app.llm.base import GenerationError, get_backend
from app.wizard import state
from app.wizard.state import QA, PartyChange, PartyMessage, PartyQAChange, Section, Session

log = logging.getLogger("promptgen.flow")

_here = Path(__file__).parent
_jinja = Environment(loader=FileSystemLoader(_here / "prompts"), autoescape=False)

SECTIONS_SCHEMA = yaml.safe_load((_here / "sections.yaml").read_text())["sections"]
ELICITATION = yaml.safe_load((_here / "elicitation.yaml").read_text())["methods"]
_PERSONAS_DOC = yaml.safe_load((_here / "personas.yaml").read_text())
FACILITATOR = _PERSONAS_DOC["facilitator"]
PERSONAS = _PERSONAS_DOC["personas"]

# Party-mode bounds (safety caps on the consensus loop).
PARTY_MAX_ROUNDS = 3              # facilitator convergence rounds after the opening
PARTY_MAX_SPEAKERS_PER_ROUND = 3  # how many people the facilitator can re-summon per round
PARTY_MAX_TURNS = 22             # hard cap on total persona/facilitator calls

# Clickable example chips under each section's free-text refine box.
REFINE_EXAMPLES = [
    "Identify risks", "Expand on security",
    "Critique & tighten", "Simplify for the stakes",
]

STAKES_HINTS = {
    "hobby": "personal/hobby project — keep it lean, minimal rigor",
    "internal": "internal tool — moderate rigor, a few users depend on it",
    "serious": "serious/production project — full rigor, real users and stakes",
}
PROJECT_TYPE_HINTS = {
    "new": "greenfield — no existing code; free to choose structure and stack",
    "existing": "existing codebase — must integrate with current architecture and "
                "conventions; prefer additive, non-breaking changes",
}
N_QUESTIONS = {"hobby": 5, "internal": 6, "serious": 8}

backend = get_backend()
SYSTEM = _jinja.get_template("system.md.j2").render().strip()


def _ctx(s: Session) -> dict:
    return {
        "idea": s.idea,
        "stakes": s.stakes,
        "stakes_hint": STAKES_HINTS.get(s.stakes, ""),
        "form_factor": s.form_factor,
        "project_type": s.project_type,
        "project_type_hint": PROJECT_TYPE_HINTS.get(s.project_type, ""),
        "repo_url": s.repo_url,
        "repo_context": s.repo_context,
    }


async def _ensure_repo_context(s: Session) -> None:
    """For existing projects with a repo link, fetch a compact codebase summary
    once and cache it on the session so it can ground clarify + drafting."""
    if s.repo_context or s.project_type != "existing" or not s.repo_url:
        return
    await _emit(s, "progress",
                '<span class="spinner" data-anim="pulse"></span> Reading the repo…')
    s.repo_context = await repo.fetch_repo_context(s.repo_url)
    await _emit(s, "progress", "")


async def _emit(s: Session, event: str, data: str = "") -> None:
    s.publish(event, data)


async def _generate(s: Session, prompt: str, max_tokens: int = 2048,
                    label: str = "Working") -> str:
    """One LLM call with a contextual progress/model-loading heartbeat."""
    notify_task = asyncio.create_task(_heartbeat(s, label))
    try:
        return await backend.generate(prompt, system=SYSTEM, max_tokens=max_tokens)
    finally:
        notify_task.cancel()
        # _heartbeat swallows CancelledError and returns, so awaiting it here
        # completes cleanly and guarantees no late "(Ns)" tick can land after
        # the clear below. The status bar is a persistent element fed only by
        # these events, so without an explicit clear the last tick lingers
        # (e.g. "Thinking up the right questions… (5s)" stuck after questions
        # already rendered).
        try:
            await notify_task
        except asyncio.CancelledError:
            pass
        await _emit(s, "progress", "")


def _anim_for(label: str) -> str:
    """Pick a spinner.js theme from the activity label, for a bit of personality."""
    l = label.lower()
    if "draft" in l:
        return "bars"
    if "refin" in l:
        return "diamonds"
    if "question" in l:
        return "stars"
    if "repo" in l or "read" in l:
        return "pulse"
    return "stars"


async def _heartbeat(s: Session, label: str) -> None:
    """Emit a live status line ('<label>… (Ns)') so the user always sees what
    is being generated and for how long — fires immediately, then every 5s."""
    try:
        anim = _anim_for(label)
        start = asyncio.get_event_loop().time()
        while True:
            elapsed = int(asyncio.get_event_loop().time() - start)
            status = getattr(backend, "status", "ready")
            if status in ("cold", "loading"):
                await _emit(s, "model_loading",
                            f'<span class="spinner" data-anim="pulse"></span> Loading model '
                            f'(cold start, can take a minute)… ({elapsed}s)')
            else:
                await _emit(s, "progress",
                            f'<span class="spinner" data-anim="{anim}"></span> {label}… ({elapsed}s)')
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        pass


QA_RE = re.compile(r"^\s*(\d+)[.)]\s*(.+)$")


def parse_questions(text: str) -> list[QA]:
    """Parse 'N. question / [ASSUMPTION] default' pairs from model output."""
    qas: list[QA] = []
    current: QA | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = QA_RE.match(line)
        if m and "[ASSUMPTION]" not in line:
            current = QA(question=m.group(2).strip(), assumption="")
            qas.append(current)
        elif "[ASSUMPTION]" in line and current is not None:
            current.assumption = line.split("[ASSUMPTION]", 1)[1].strip(" :-")
    return [q for q in qas if q.question]


async def run_clarify(s: Session) -> None:
    try:
        await _emit(s, "job_started", "clarify")
        await _ensure_repo_context(s)
        tmpl = _jinja.get_template("clarify.md.j2")
        prompt = tmpl.render(n_questions=N_QUESTIONS.get(s.stakes, 6), **_ctx(s))
        text = await _generate(s, prompt, max_tokens=1536,
                               label="Thinking up the right questions")
        s.qas = parse_questions(text)
        if not s.qas:
            raise GenerationError(f"could not parse questions from model output: {text[:200]}")
        s.phase = "clarify"
        await _emit(s, "questions_ready")
    except Exception as e:
        log.exception("clarify failed")
        s.error = str(e)
        await _emit(s, "error", str(e))


def init_sections(s: Session) -> None:
    """Called synchronously before rendering step 4, so the page always has
    placeholder cards regardless of background-task scheduling."""
    s.sections = [
        Section(id=row["id"], title=row["title"], instruction=row["instruction"])
        for row in SECTIONS_SCHEMA
    ]
    s.phase = "sections"


async def run_sections(s: Session) -> None:
    tmpl = _jinja.get_template("section.md.j2")
    qas = [
        {"question": q.question, "answer": q.answer or f"(assumed) {q.assumption}"}
        for q in s.qas
    ]
    total = len(s.sections)
    for i, sec in enumerate(s.sections, 1):
        try:
            sec.status = "generating"
            await _emit(s, "section_started", sec.id)
            prior = [
                {"title": p.title, "content": p.content}
                for p in s.sections
                if p.status == "done"
            ]
            prompt = tmpl.render(
                qas=qas, prior_sections=prior,
                instruction=sec.instruction, title=sec.title, **_ctx(s),
            )
            sec.content = await _generate(s, prompt, label=f"Drafting {i}/{total}: {sec.title}")
            sec.status = "done"
            await _emit(s, "section_done", sec.id)
        except Exception as e:
            log.exception("section %s failed", sec.id)
            sec.status = "error"
            sec.content = f"_Generation failed: {e}_"
            await _emit(s, "section_error", sec.id)
    await _emit(s, "job_done", "sections")
    if s.auto_party:
        # "Submit & Party" from the clarify step: review the fresh draft.
        s.auto_party = False
        await run_party(s)


async def run_single_section(s: Session, sid: str) -> None:
    """Re-draft one section (retry after a failed generation)."""
    sec = s.section(sid)
    if sec is None:
        return
    tmpl = _jinja.get_template("section.md.j2")
    qas = [
        {"question": q.question, "answer": q.answer or f"(assumed) {q.assumption}"}
        for q in s.qas
    ]
    try:
        sec.status = "generating"
        await _emit(s, "section_started", sec.id)
        prior = [
            {"title": p.title, "content": p.content}
            for p in s.sections
            if p.status == "done" and p.id != sec.id
        ]
        prompt = tmpl.render(
            qas=qas, prior_sections=prior,
            instruction=sec.instruction, title=sec.title, **_ctx(s),
        )
        sec.content = await _generate(s, prompt, label=f"Re-drafting: {sec.title}")
        sec.status = "done"
        await _emit(s, "section_done", sec.id)
    except Exception as e:
        log.exception("retry of section %s failed", sid)
        sec.status = "error"
        sec.content = f"_Generation failed: {e}_"
        await _emit(s, "section_error", sec.id)


async def refine_section(s: Session, sec: Section, instruction: str) -> bool:
    """Re-draft one section per a free-text instruction. Pushes the current
    content onto history (undo) and restores it on failure. Returns success.
    Shared by manual refine and party-mode change application."""
    try:
        sec.history.append(sec.content)
        sec.status = "generating"
        await _emit(s, "section_started", sec.id)
        tmpl = _jinja.get_template("refine.md.j2")
        prompt = tmpl.render(
            title=sec.title, content=sec.history[-1],
            method_instruction=instruction, **_ctx(s),
        )
        sec.content = await _generate(s, prompt, label=f"Refining: {sec.title}")
        sec.status = "done"
        await _emit(s, "section_done", sec.id)
        return True
    except Exception as e:
        log.exception("refine of section %s failed", sec.id)
        sec.content = sec.history.pop() if sec.history else sec.content
        sec.status = "done"
        await _emit(s, "section_done", sec.id)
        await _emit(s, "error", f"Refinement failed, kept previous version: {e}")
        return False


async def run_refine(s: Session, sid: str, instruction: str) -> None:
    sec = s.section(sid)
    instruction = (instruction or "").strip()
    if sec is None or not instruction:
        if sec is not None:
            sec.status = "done"  # undo the handler's optimistic flip
        await _emit(s, "error", "empty or invalid refine instruction")
        return
    await refine_section(s, sec, instruction)


# ----------------------------------------------------------------------------
# Party mode: a facilitated round-table review that converges to consensus.
# Each persona is its own model call and sees the running transcript, so later
# speakers can contradict earlier ones; the facilitator passes the mic back
# until it declares consensus, then synthesizes approvable changes.
# ----------------------------------------------------------------------------

def _persona_by_id(pid: str) -> dict | None:
    return next((p for p in PERSONAS if p["id"] == pid), None)


def _party_transcript(s: Session) -> str:
    return "\n\n".join(
        f"{m.name} ({m.role}): {m.text}"
        for m in s.party_messages
        if m.kind in ("persona", "facilitator")
    )


async def _party_gen(prompt: str, max_tokens: int) -> str:
    # system=None: openai gets a pure in-character prompt; the diffusion cnv
    # backend keeps whatever system it was spawned with (no costly respawn).
    return (await backend.generate(prompt, system=None, max_tokens=max_tokens)).strip()


def _bubble_html(m: PartyMessage) -> str:
    """Render one chat bubble. Mirrors partials/party_chat.html so live
    sse-swap appends look identical to the server-rendered initial list."""
    text = html.escape(m.text)
    if m.kind == "system":
        return f'<div class="bubble system"><div class="msg">{text}</div></div>'
    who = (f'{html.escape(m.emoji)} {html.escape(m.name)} '
           f'<small>· {html.escape(m.role)}</small>')
    return (f'<div class="bubble {m.kind}"><div class="who">{who}</div>'
            f'<div class="msg">{text}</div></div>')


async def _say(s: Session, msg: PartyMessage) -> None:
    s.party_messages.append(msg)
    # Send the rendered bubble so the chat appends instantly via sse-swap
    # (the vendored sse.js only fires sse-swap, not hx-trigger="sse:...").
    await _emit(s, "party_msg", _bubble_html(msg))


async def _persona_turn(s: Session, p: dict, spec: str, focus: str = "",
                        persona_template: str = "party_persona.md.j2") -> None:
    await _emit(s, "party_turn", f"{p['emoji']} {p['name']} ({p['role']}) is speaking…")
    prompt = _jinja.get_template(persona_template).render(
        voice=p["voice"].strip(), name=p["name"], role=p["role"],
        spec=spec, transcript=_party_transcript(s), focus=focus.strip(),
        idea=s.idea,
    )
    text = await _party_gen(prompt, max_tokens=512)
    await _say(s, PartyMessage(p["id"], p["name"], p["emoji"], p["role"], text, "persona"))
    await _emit(s, "party_turn", "")


def _parse_facilitator(raw: str) -> tuple[str, str, list[str]]:
    """Returns (spoken_text, action, next_ids). action is NEXT or CONSENSUS."""
    say_lines, action_line = [], None
    for ln in raw.splitlines():
        if ln.strip().upper().startswith("ACTION:"):
            action_line = ln.strip()
        else:
            say_lines.append(ln)
    say = "\n".join(say_lines).strip()
    if not action_line:
        return say, "CONSENSUS", []
    body = action_line.split(":", 1)[1].strip()
    if body.upper().startswith("NEXT"):
        rest = body[len("NEXT"):].strip(" :")
        ids = [x.strip().lower() for x in re.split(r"[,\s]+", rest) if x.strip()]
        ids = [i for i in ids if _persona_by_id(i)]
        return (say, "NEXT", ids) if ids else (say, "CONSENSUS", [])
    return say, "CONSENSUS", []


async def _facilitator_turn(s: Session, spec: str,
                            facilitator_template: str = "party_facilitator.md.j2"
                            ) -> tuple[str, str, list[str]]:
    await _emit(s, "party_turn", f"{FACILITATOR['emoji']} {FACILITATOR['name']} is reading the room…")
    prompt = _jinja.get_template(facilitator_template).render(
        voice=FACILITATOR["voice"].strip(), spec=spec,
        transcript=_party_transcript(s), personas=PERSONAS, idea=s.idea,
    )
    raw = await _party_gen(prompt, max_tokens=400)
    say, action, next_ids = _parse_facilitator(raw)
    await _say(s, PartyMessage(FACILITATOR["id"], FACILITATOR["name"], FACILITATOR["emoji"],
                               FACILITATOR["role"], say or raw, "facilitator"))
    await _emit(s, "party_turn", "")
    return say, action, next_ids


def _resolve_section(raw_id: str, sections: list[Section]) -> str | None:
    if not raw_id:
        return None
    key = raw_id.strip().lower()
    for sec in sections:
        if key == sec.id:
            return sec.id
    for sec in sections:
        if key == sec.title.lower() or key in sec.title.lower() or sec.title.lower() in key:
            return sec.id
    for sec in sections:
        if sec.id in key or key in sec.id:
            return sec.id
    return None


def _parse_changes(s: Session, raw: str) -> list[PartyChange]:
    if "NO CHANGES" in raw.upper():
        return []
    changes: list[PartyChange] = []
    for i, block in enumerate(re.split(r"^\s*-{3,}\s*$", raw, flags=re.M)):
        sec_id = change = None
        why = ""
        for ln in block.splitlines():
            l = ln.strip()
            if l.upper().startswith("SECTION:"):
                sec_id = l.split(":", 1)[1].strip()
            elif l.upper().startswith("CHANGE:"):
                change = l.split(":", 1)[1].strip()
            elif l.upper().startswith("WHY:"):
                why = l.split(":", 1)[1].strip()
        if not change:
            continue
        sid = _resolve_section(sec_id, s.sections)
        if sid is None:
            continue
        title = s.section(sid).title
        changes.append(PartyChange(id=f"c{i}", section_id=sid, section_title=title,
                                   instruction=change, rationale=why))
    return changes


async def _round_table(s: Session, subject: str,
                       persona_template: str = "party_persona.md.j2",
                       facilitator_template: str = "party_facilitator.md.j2") -> None:
    """Shared deliberation loop: opening round (everyone speaks once) →
    facilitator-driven mic-passing until consensus or the turn cap. Appends
    bubbles to s.party_messages; callers do their own synthesis afterward."""
    turns = 0
    for p in PERSONAS:
        await _persona_turn(s, p, subject, persona_template=persona_template)
        turns += 1
    for _ in range(PARTY_MAX_ROUNDS):
        if turns >= PARTY_MAX_TURNS:
            break
        say, action, next_ids = await _facilitator_turn(s, subject,
                                                         facilitator_template=facilitator_template)
        turns += 1
        if action == "CONSENSUS" or not next_ids:
            break
        for pid in next_ids[:PARTY_MAX_SPEAKERS_PER_ROUND]:
            if turns >= PARTY_MAX_TURNS:
                break
            p = _persona_by_id(pid)
            if p:
                await _persona_turn(s, p, subject, focus=say,
                                    persona_template=persona_template)
                turns += 1


async def run_party(s: Session) -> None:
    """Orchestrate the round table: opening round → facilitator-driven
    mic-passing until consensus → synthesize approvable changes."""
    try:
        s.party_status = "running"
        s.party_messages = []
        s.party_changes = []
        await _emit(s, "party_started")
        spec = assemble_final(s)
        await _say(s, PartyMessage("system", "", "", "",
            "🎤 Round table convened. Each reviewer speaks once, then the facilitator "
            "passes the mic back to resolve any disagreements until the group reaches "
            "consensus. Then you'll approve or deny the agreed changes.", "system"))

        await _round_table(s, spec)

        # Synthesis: facilitator distills the consensus into approvable changes.
        await _emit(s, "party_turn", f"{FACILITATOR['emoji']} {FACILITATOR['name']} is summarizing the consensus…")
        prompt = _jinja.get_template("party_synthesis.md.j2").render(
            voice=FACILITATOR["voice"].strip(), spec=spec,
            transcript=_party_transcript(s), sections=s.sections,
        )
        raw = await _party_gen(prompt, max_tokens=1200)
        s.party_changes = _parse_changes(s, raw)
        s.party_status = "ready"
        await _emit(s, "party_turn", "")
        n = len(s.party_changes)
        await _say(s, PartyMessage("system", "", "", "",
            f"✅ Consensus reached — {n} proposed change{'' if n == 1 else 's'}. "
            "Review them below." if n else
            "✅ The group reviewed the spec and proposed no changes.", "system"))
        await _emit(s, "party_ready")
    except Exception as e:
        log.exception("party mode failed")
        s.party_status = "error"
        s.error = str(e)
        await _emit(s, "error", f"Party mode failed: {e}")
        await _emit(s, "party_ready")


async def apply_party_change(s: Session, cid: str) -> None:
    """Approve a change: re-draft its section through the refine pipeline."""
    ch = s.party_change(cid)
    if ch is None or ch.status == "applied":
        return
    sec = s.section(ch.section_id)
    if sec is None:
        ch.status = "denied"
        await _emit(s, "party_changed", cid)
        return
    ch.status = "applying"
    await _emit(s, "party_changed", cid)
    ok = await refine_section(s, sec, ch.instruction)
    ch.status = "applied" if ok else "pending"
    await _emit(s, "party_changed", cid)
    await _emit(s, "mega_updated")
    await _emit(s, "sections_updated")  # refresh the section cards on step 3


async def apply_party_changes(s: Session, cids: list[str]) -> None:
    """Apply approved changes one at a time (each refines the live section,
    so sequential application lets later changes build on earlier ones)."""
    for cid in cids:
        await apply_party_change(s, cid)


# ----------------------------------------------------------------------------
# Question-review party (step 2): the same round table reviews the clarifying
# QUESTIONS instead of the drafted spec, and proposes new questions / answers.
# ----------------------------------------------------------------------------

def _qa_subject(s: Session) -> str:
    """Render the current Q&A list as the subject the personas review."""
    lines = []
    for i, qa in enumerate(s.qas, 1):
        ans = qa.answer.strip() if qa.answer.strip() else f"(assumption) {qa.assumption}"
        lines.append(f"{i}. {qa.question}\n   current answer: {ans}")
    return "\n".join(lines)


def _parse_qa_changes(s: Session, raw: str) -> list[PartyQAChange]:
    """Parse the QA-synthesis output into add_question / suggest_answer items."""
    if "NO CHANGES" in raw.upper():
        return []
    changes: list[PartyQAChange] = []
    n_qas = len(s.qas)
    for i, block in enumerate(re.split(r"^\s*-{3,}\s*$", raw, flags=re.M)):
        fields: dict[str, str] = {}
        for ln in block.splitlines():
            l = ln.strip()
            for key in ("ADD_QUESTION:", "ASSUMPTION:", "SUGGEST_ANSWER:", "ANSWER:", "WHY:"):
                if l.upper().startswith(key):
                    fields[key.rstrip(":")] = l.split(":", 1)[1].strip()
        why = fields.get("WHY", "")
        if "ADD_QUESTION" in fields and fields["ADD_QUESTION"]:
            changes.append(PartyQAChange(
                id=f"q{i}", kind="add_question", rationale=why,
                question=fields["ADD_QUESTION"],
                assumption=fields.get("ASSUMPTION", "")))
        elif "SUGGEST_ANSWER" in fields and fields.get("ANSWER"):
            m = re.search(r"\d+", fields["SUGGEST_ANSWER"])
            if not m:
                continue
            idx = int(m.group()) - 1  # 1-based in the prompt → 0-based index
            if 0 <= idx < n_qas:
                changes.append(PartyQAChange(
                    id=f"q{i}", kind="suggest_answer", rationale=why,
                    target=idx, answer=fields["ANSWER"]))
    return changes


async def run_party_questions(s: Session) -> None:
    """Round-table review of the clarifying questions: personas suggest missing
    questions and better answers, distilled into approvable PartyQAChanges."""
    try:
        s.party_status = "running"
        s.party_messages = []
        s.party_qa_changes = []
        await _emit(s, "party_started")
        subject = _qa_subject(s)
        await _say(s, PartyMessage("system", "", "", "",
            "🎤 Round table convened to pressure-test your clarifying questions. "
            "Each reviewer weighs in, the facilitator settles disagreements, then "
            "you'll approve or deny suggested new questions and answers.", "system"))

        await _round_table(s, subject, persona_template="party_qa_persona.md.j2",
                           facilitator_template="party_qa_facilitator.md.j2")

        await _emit(s, "party_turn",
                    f"{FACILITATOR['emoji']} {FACILITATOR['name']} is collecting the suggestions…")
        prompt = _jinja.get_template("party_qa_synthesis.md.j2").render(
            voice=FACILITATOR["voice"].strip(), spec=subject,
            transcript=_party_transcript(s), idea=s.idea, n_qas=len(s.qas),
        )
        raw = await _party_gen(prompt, max_tokens=1200)
        s.party_qa_changes = _parse_qa_changes(s, raw)
        s.party_status = "ready"
        await _emit(s, "party_turn", "")
        n = len(s.party_qa_changes)
        await _say(s, PartyMessage("system", "", "", "",
            f"✅ Done — {n} suggestion{'' if n == 1 else 's'} for your questions. "
            "Review them below." if n else
            "✅ The group reviewed your questions and had nothing to add.", "system"))
        await _emit(s, "party_ready")
    except Exception as e:
        log.exception("question-review party failed")
        s.party_status = "error"
        s.error = str(e)
        await _emit(s, "error", f"Question review failed: {e}")
        await _emit(s, "party_ready")


async def apply_qa_change(s: Session, cid: str) -> bool:
    """Approve a QA suggestion: append a new question, or set a suggested answer."""
    ch = s.party_qa_change(cid)
    if ch is None or ch.status != "pending":
        return False
    if ch.kind == "add_question":
        s.qas.append(QA(question=ch.question, assumption=ch.assumption or "(no default)", answer=""))
    elif ch.kind == "suggest_answer" and 0 <= ch.target < len(s.qas):
        s.qas[ch.target].answer = ch.answer
    else:
        ch.status = "denied"
        return False
    ch.status = "applied"
    return True


# ----------------------------------------------------------------------------
# Shoot the Moon: run the entire pipeline autonomously from just the idea —
# infer calibration, accept the generated assumptions as answers, draft all
# sections, run the party, and auto-apply the consensus changes.
# ----------------------------------------------------------------------------

_MOON_FORM_FACTORS = ["web app", "CLI tool", "API/service", "mobile app"]


async def _infer_calibration(s: Session) -> tuple[str, str, str]:
    """Pick stakes + form factor + project type from the idea (defaults on miss)."""
    prompt = (
        "Classify this software idea.\n\nIDEA: " + s.idea +
        "\n\nChoose STAKES from: hobby, internal, serious.\n"
        "Choose FORM from: web app, CLI tool, API/service, mobile app.\n"
        "Choose PROJECT from: new, existing.\n"
        "Output exactly three lines:\nSTAKES: <one>\nFORM: <one>\nPROJECT: <one>"
    )
    stakes, form_factor, project_type = "internal", "web app", "new"
    try:
        raw = await _party_gen(prompt, max_tokens=48)
    except Exception:
        return stakes, form_factor, project_type
    for ln in raw.splitlines():
        u = ln.strip().upper()
        if u.startswith("STAKES:"):
            v = ln.split(":", 1)[1].strip().lower()
            if v in ("hobby", "internal", "serious"):
                stakes = v
        elif u.startswith("FORM:"):
            v = ln.split(":", 1)[1].strip().lower()
            for opt in _MOON_FORM_FACTORS:
                if opt.lower() in v:
                    form_factor = opt
        elif u.startswith("PROJECT:"):
            v = ln.split(":", 1)[1].strip().lower()
            if "exist" in v:
                project_type = "existing"
            elif "new" in v:
                project_type = "new"
    return stakes, form_factor, project_type


async def run_moonshot(s: Session) -> None:
    """One-click full run: idea → calibration → assumptions → sections →
    party → auto-applied consensus → final. Best-effort; sub-steps that fail
    log an error event but the run still lands the user on the final page."""
    try:
        s.phase = "moonshot"
        await _emit(s, "moon", "🌙 Reading your idea…")
        # Honor whatever the user picked on step 1; infer only the blanks.
        if not (s.stakes and s.form_factor and s.project_type):
            i_stakes, i_form, i_proj = await _infer_calibration(s)
            s.stakes = s.stakes or i_stakes
            s.form_factor = s.form_factor or i_form
            s.project_type = s.project_type or i_proj
        await _emit(s, "moon",
                    f"🎯 Treating this as a {s.stakes} {s.form_factor} ({s.project_type} project).")

        await _emit(s, "moon", "❓ Drafting clarifying questions and accepting the smart defaults…")
        await run_clarify(s)  # answers left blank → each [ASSUMPTION] stands

        init_sections(s)
        await _emit(s, "moon", "✍️ Drafting the spec sections…")
        await run_sections(s)

        await _emit(s, "moon", "🎉 Convening the BMAD round table…")
        await run_party(s)

        pending = [c.id for c in s.party_changes if c.status == "pending"]
        if pending:
            await _emit(s, "moon", f"🛠️ Applying {len(pending)} consensus change(s)…")
            await apply_party_changes(s, pending)

        s.phase = "final"
        await _emit(s, "moon", "✅ Done — opening your mega-prompt.")
    except Exception as e:
        log.exception("moonshot failed")
        s.error = str(e)
        await _emit(s, "error", f"Shoot the Moon failed: {e}")
        if s.sections:
            s.phase = "final"  # land on whatever we produced
    finally:
        await _emit(s, "moonshot_done")


def assemble_final(s: Session) -> str:
    """Deterministic mega-prompt assembly — no LLM."""
    parts = [
        "# Implementation Brief",
        "",
        "You are implementing the following project. Treat every requirement and "
        "constraint below as binding. Ask before deviating from the Tech "
        "Constraints; do not add anything listed under Out of Scope.",
        "",
        f"**Project idea (verbatim from the author):** {s.idea}",
        f"**Project type:** {s.project_type} — {PROJECT_TYPE_HINTS.get(s.project_type, '')}",
        f"**Stakes:** {s.stakes} — {STAKES_HINTS.get(s.stakes, '')}",
        f"**Form factor:** {s.form_factor}",
    ]
    if s.project_type == "existing" and s.repo_url:
        parts.append(f"**Existing repository:** {s.repo_url} — integrate with the "
                     "current codebase; prefer additive, non-breaking changes.")
    parts.append("")
    for sec in s.sections:
        parts += [f"## {sec.title}", "", sec.content, ""]
    return "\n".join(parts)


# ----------------------------------------------------------------------------
# Post-processing QA: a free deterministic lint (always shown on the final page)
# plus an on-demand LLM critique pass.
# ----------------------------------------------------------------------------

_PLACEHOLDER_PATTERNS = [
    (r"\bTODO\b", "a TODO marker"),
    (r"\bTBD\b", "a TBD marker"),
    (r"\bFIXME\b", "a FIXME marker"),
    (r"\bXXX\b", "an XXX marker"),
    (r"\[(?:placeholder|fill in|insert|your .*?here)\]", "placeholder text"),
    (r"\blorem ipsum\b", "lorem ipsum filler"),
]


def lint_spec(s: Session) -> list[dict]:
    """Deterministic, no-LLM checks over the assembled spec. Returns findings
    as {severity: error|warn|info, message}."""
    findings: list[dict] = []
    if not s.sections:
        return [{"severity": "error", "message": "No sections were drafted."}]

    for sec in s.sections:
        content = (sec.content or "").strip()
        if sec.status == "error" or content.startswith("_Generation failed"):
            findings.append({"severity": "error",
                             "message": f"{sec.title}: generation failed — re-draft this section."})
            continue
        if len(content) < 40:
            findings.append({"severity": "warn",
                             "message": f"{sec.title}: very short ({len(content)} chars) — likely underspecified."})
        for pat, label in _PLACEHOLDER_PATTERNS:
            if re.search(pat, content, re.I):
                findings.append({"severity": "warn",
                                 "message": f"{sec.title}: contains {label}."})
                break

    # Contradiction heuristic: an out-of-scope bullet restated in requirements.
    oos = next((x for x in s.sections if "scope" in x.id or "out" in x.id), None)
    reqs = " ".join(x.content.lower() for x in s.sections
                    if "requirement" in x.id or "functional" in x.id)
    if oos and reqs:
        for line in oos.content.splitlines():
            item = line.strip(" -*•\t").strip().lower()
            if len(item) >= 12 and item in reqs:
                findings.append({"severity": "warn",
                                 "message": f"Possible contradiction: out-of-scope item “{item[:60]}” also appears in the requirements."})

    if not findings:
        findings.append({"severity": "info", "message": "No issues found by the automated lint."})
    return findings


_QA_LINE_RE = re.compile(r"^\s*\[\s*(high|med|medium|low)\s*\]\s*(.+)$", re.I)


def _parse_qa_review(raw: str) -> list[dict]:
    # Don't short-circuit on a substring match for "NO ISSUES" — it can appear
    # inside a finding. Just parse the bracketed lines; none → treat as clean.
    out: list[dict] = []
    for ln in raw.splitlines():
        m = _QA_LINE_RE.match(ln)
        if not m:
            continue
        sev = m.group(1).lower()
        sev = "med" if sev == "medium" else sev
        body = m.group(2).strip()
        category, _, text = body.partition(":")
        # id + fix_status drive the per-finding "Fix" control on the QA panel.
        item = {"id": f"qf{len(out)}", "fix_status": "idle", "severity": sev}
        if text:
            item["category"], item["text"] = category.strip(), text.strip()
        else:
            item["category"], item["text"] = "", body
        out.append(item)
    return out


async def run_qa_review(s: Session) -> None:
    """On-demand LLM critique of the assembled spec."""
    try:
        s.qa_review_status = "running"
        s.qa_review = []
        await _emit(s, "qa_review_started")
        prompt = _jinja.get_template("qa_review.md.j2").render(spec=assemble_final(s))
        raw = await _generate(s, prompt, max_tokens=900, label="Running QA review")
        s.qa_review = _parse_qa_review(raw)
        s.qa_review_status = "ready"
        await _emit(s, "progress", "✓ QA review complete — findings below.")
        await _emit(s, "qa_review_ready")
    except Exception as e:
        log.exception("qa review failed")
        s.qa_review_status = "error"
        s.error = str(e)
        await _emit(s, "qa_review_ready")


async def run_qa_fix(s: Session) -> None:
    """Implement all QA-review findings, one at a time, so each finding card
    visibly transitions fixing → fixed in turn (same path as a single-item
    fix). Already-fixed findings are skipped."""
    try:
        s.qa_fix_status = "running"
        for f in list(s.qa_review):
            if f.get("fix_status") == "done":
                continue
            await run_qa_fix_item(s, f)  # sets f running→done|noop|error, emits per-item
        s.qa_fix_status = "ready"
        await _emit(s, "qa_fix_ready")
    except Exception as e:
        log.exception("qa fix failed")
        s.qa_fix_status = "error"
        s.error = str(e)
        await _emit(s, "qa_fix_ready")


async def run_qa_fix_item(s: Session, finding: dict) -> None:
    """Implement a single QA-review finding: turn just that finding into
    per-section edits and apply them through the refine pipeline. Mutates
    finding['fix_status'] in place (running → done | noop | error)."""
    try:
        finding["fix_status"] = "running"
        one = (f"- [{finding.get('severity', '')}] "
               f"{finding.get('category', '')}: {finding.get('text', '')}")
        prompt = _jinja.get_template("qa_fix.md.j2").render(
            spec=assemble_final(s), sections=s.sections, findings=one)
        raw = await _generate(s, prompt, max_tokens=900, label="Fixing QA finding")
        changes = _parse_changes(s, raw)
        applied = 0
        for ch in changes:
            sec = s.section(ch.section_id)
            if sec is not None and await refine_section(s, sec, ch.instruction):
                applied += 1
        finding["fix_status"] = "done" if applied else "noop"
        if applied:
            await _emit(s, "mega_updated")
            await _emit(s, "sections_updated")  # refresh the edited section cards
            await _emit(s, "progress", "✓ Fix applied — section updated above.")
        await _emit(s, "qa_item_fixed", finding.get("id", ""))
    except Exception as e:
        log.exception("qa item fix failed")
        finding["fix_status"] = "error"
        s.error = str(e)
        await _emit(s, "qa_item_fixed", finding.get("id", ""))
