import asyncio
import html
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import config, settings
from app.llm.base import GenerationError
from app.wizard import flow, state

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("promptgen")

app = FastAPI(title="promptgen")
_here = Path(__file__).parent
app.mount("/static", StaticFiles(directory=_here / "static"), name="static")
templates = Jinja2Templates(directory=_here / "templates")
templates.env.globals["personas"] = flow.PERSONAS
templates.env.globals["facilitator"] = flow.FACILITATOR

FORM_FACTORS = ["web app", "CLI tool", "API/service", "mobile app"]
PROJECT_TYPES = [
    ("new", "New project", "Greenfield — starting from scratch"),
    ("existing", "Existing codebase", "Adding to / changing something that exists"),
]
# Stakes is no longer asked — every spec is calibrated as production-grade.
DEFAULT_STAKES = "serious"


def _calibration_ctx() -> dict:
    """Option lists for the calibration controls on step 1."""
    return {"form_factors": FORM_FACTORS, "project_types": PROJECT_TYPES}


def _render(name: str, request: Request, headers: dict | None = None, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request, name, ctx, headers=headers)


def _html(name: str, **ctx) -> str:
    """Render a partial to a string (for concatenating OOB swaps in one response)."""
    return templates.env.get_template(name).render(**ctx)


def _push(s) -> dict:
    """HX-Push-Url header so refresh/back lands on the session resume route."""
    return {"HX-Push-Url": f"/sessions/{s.id}"}


@app.on_event("startup")
async def startup():
    # Load persisted endpoint/model settings over the env-seeded defaults.
    settings.load()


@app.get("/healthz")
async def healthz() -> dict:
    # Must not touch the LLM — stays Ready while the model is cold.
    return {"ok": True, "backend": config.BACKEND,
            "llm_status": getattr(flow.backend, "status", "unknown")}


@app.get("/settings", response_class=HTMLResponse)
async def settings_panel(request: Request):
    return _render("partials/settings.html", request, cfg=settings.current,
                   openai=config.BACKEND == "openai")


@app.post("/settings", response_class=HTMLResponse)
async def settings_save(request: Request, base_url: str = Form(""),
                        model: str = Form(""), api_key: str = Form(""),
                        disable_thinking: bool = Form(False)):
    settings.update(base_url=base_url, model=model, api_key=api_key,
                    disable_thinking=disable_thinking)
    return _render("partials/settings.html", request, cfg=settings.current,
                   openai=config.BACKEND == "openai", saved=True)


@app.get("/settings/models", response_class=HTMLResponse)
async def settings_models(request: Request, base_url: str = "", api_key: str = ""):
    from app.llm.openai_compat import list_models
    try:
        models = await list_models(base_url, api_key)
    except GenerationError as e:
        return _render("partials/model_options.html", request, models=[], error=str(e))
    return _render("partials/model_options.html", request, models=models, error="")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return _render("step1_idea.html", request, **_calibration_ctx())


@app.get("/sessions/{sid}", response_class=HTMLResponse)
async def resume(request: Request, sid: str):
    """Re-enter a session at its current phase (page refresh, shared link)."""
    s = state.get(sid)
    if s is None:
        return _render("resume.html", request, body="expired.html", s=None)
    if s.phase == "clarify":
        return _render("resume.html", request, body="step3_clarify.html", s=s)
    if s.phase == "sections":
        return _render("resume.html", request, body="step4_sections.html",
                       s=s, examples=flow.REFINE_EXAMPLES, auto_party=s.auto_party)
    if s.phase == "moonshot":
        return _render("resume.html", request, body="step_moonshot.html", s=s)
    if s.phase == "final":
        return _render("step6_final.html", request, s=s,
                       mega_prompt=flow.assemble_final(s))
    return _render("step1_idea.html", request, **_calibration_ctx())


@app.post("/sessions", response_class=HTMLResponse)
async def create_session(request: Request, idea: str = Form(...),
                         project_type: str = Form(...), form_factor: str = Form(...),
                         repo_url: str = Form("")):
    s = state.create()
    s.idea = idea.strip()
    s.project_type, s.form_factor, s.stakes = project_type, form_factor, DEFAULT_STAKES
    s.repo_url = repo_url.strip() if project_type == "existing" else ""
    s.phase = "clarify"
    asyncio.create_task(flow.run_clarify(s))
    return _render("step3_clarify.html", request, headers=_push(s), s=s)


@app.post("/moonshot", response_class=HTMLResponse)
async def moonshot(request: Request, idea: str = Form(...),
                   project_type: str = Form(""), form_factor: str = Form(""),
                   repo_url: str = Form("")):
    s = state.create()
    s.idea = idea.strip()
    # Honor any explicit calibration the user set on step 1; run_moonshot
    # infers whatever's left blank. Stakes is fixed to the default.
    s.project_type, s.form_factor, s.stakes = project_type, form_factor, DEFAULT_STAKES
    s.repo_url = repo_url.strip() if project_type == "existing" else ""
    s.phase = "moonshot"
    asyncio.create_task(flow.run_moonshot(s))
    return _render("step_moonshot.html", request, headers=_push(s), s=s)


@app.get("/sessions/{sid}/moon/status")
async def moon_status(sid: str):
    s = state.get(sid)
    if s is None:
        return Response(status_code=404)
    # When the run lands (or errors out with partial output), tell htmx to
    # navigate to the assembled result.
    if s.phase == "final" or (s.error and s.phase != "moonshot"):
        return Response(status_code=204, headers={"HX-Redirect": f"/sessions/{sid}"})
    return Response(status_code=204)


@app.get("/sessions/{sid}/questions", response_class=HTMLResponse)
async def questions_partial(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    return _render("partials/question_list.html", request, s=s)


@app.post("/sessions/{sid}/answers", response_class=HTMLResponse)
async def answers(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    form = await request.form()
    for i, qa in enumerate(s.qas):
        qa.answer = str(form.get(f"answer_{i}", "")).strip()
    # "Submit & Party" sets party=1: convene the round table once the draft lands.
    s.auto_party = bool(form.get("party"))
    flow.init_sections(s)
    asyncio.create_task(flow.run_sections(s))
    return _render("step4_sections.html", request, headers=_push(s), s=s,
                   examples=flow.REFINE_EXAMPLES, auto_party=s.auto_party)


@app.get("/sessions/{sid}/sections/{section_id}", response_class=HTMLResponse)
async def section_partial(request: Request, sid: str, section_id: str):
    s = state.get(sid)
    sec = s.section(section_id) if s else None
    if s is None or sec is None:
        return HTMLResponse("<div class='card error'>Unknown section</div>")
    return _render("partials/section_card.html", request, s=s, sec=sec,
                   examples=flow.REFINE_EXAMPLES)


@app.post("/sessions/{sid}/sections/{section_id}/retry", response_class=HTMLResponse)
async def retry_section(request: Request, sid: str, section_id: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    sec = s.section(section_id)
    if sec is not None:
        sec.status = "generating"  # render the self-refreshing waiting card
    asyncio.create_task(flow.run_single_section(s, section_id))
    return _render("partials/section_card.html", request, s=s, sec=sec,
                   examples=flow.REFINE_EXAMPLES)


@app.get("/sessions/{sid}/sections/{section_id}/edit", response_class=HTMLResponse)
async def section_edit_form(request: Request, sid: str, section_id: str):
    s = state.get(sid)
    sec = s.section(section_id) if s else None
    if s is None or sec is None:
        return HTMLResponse("<div class='card error'>Unknown section</div>")
    return _render("partials/section_editor.html", request, s=s, sec=sec)


@app.post("/sessions/{sid}/sections/{section_id}/edit", response_class=HTMLResponse)
async def section_edit_save(request: Request, sid: str, section_id: str,
                            content: str = Form("")):
    s = state.get(sid)
    sec = s.section(section_id) if s else None
    if s is None or sec is None:
        return _render("expired.html", request)
    sec.history.append(sec.content)  # manual edits are undoable too
    sec.content = content.strip()
    sec.status = "done"
    return _render("partials/section_card.html", request, s=s, sec=sec,
                   examples=flow.REFINE_EXAMPLES)


@app.post("/sessions/{sid}/sections/{section_id}/refine", response_class=HTMLResponse)
async def refine(request: Request, sid: str, section_id: str,
                 instruction: str = Form(...)):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    sec = s.section(section_id)
    if sec is not None and sec.status == "done":
        # Flip status before rendering so the response is the self-refreshing
        # waiting card, not the inert done card (the task hasn't started yet).
        sec.status = "generating"
    asyncio.create_task(flow.run_refine(s, section_id, instruction))
    return _render("partials/section_card.html", request, s=s, sec=sec,
                   examples=flow.REFINE_EXAMPLES)


# ---- Party mode (round-table review on the final spec) ----

@app.post("/sessions/{sid}/party", response_class=HTMLResponse)
async def party_start(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    if s.party_status != "running":
        asyncio.create_task(flow.run_party(s))
    return _render("partials/party_panel.html", request, s=s)


@app.get("/sessions/{sid}/party", response_class=HTMLResponse)
async def party_panel(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    return _render("partials/party_panel.html", request, s=s)


@app.get("/sessions/{sid}/party-when-ready", response_class=HTMLResponse)
async def party_when_ready(request: Request, sid: str):
    """Poller target for the clarify-step 'Submit & Party' path: returns the
    party panel once the round table is active, otherwise the waiting card
    (which keeps polling). hx-trigger='sse:...' is inert in the vendored sse.js,
    so the panel can't appear via SSE — this 3s poll swaps it in instead."""
    s = state.get(sid)
    if s is None:
        return HTMLResponse("")
    if s.party_status != "idle":
        return _render("partials/party_panel.html", request, s=s)
    return _render("partials/party_waiting.html", request, s=s)


@app.get("/sessions/{sid}/party/chat", response_class=HTMLResponse)
async def party_chat(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return HTMLResponse("")
    return _render("partials/party_chat.html", request, s=s)


@app.get("/sessions/{sid}/party/changes", response_class=HTMLResponse)
async def party_changes(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return HTMLResponse("")
    return _render("partials/party_changes.html", request, s=s)


@app.get("/sessions/{sid}/party/changes/{cid}", response_class=HTMLResponse)
async def party_change_card(request: Request, sid: str, cid: str):
    s = state.get(sid)
    ch = s.party_change(cid) if s else None
    if s is None or ch is None:
        return HTMLResponse("")
    return _render("partials/party_change_card.html", request, s=s, ch=ch)


@app.post("/sessions/{sid}/party/changes/{cid}/approve", response_class=HTMLResponse)
async def party_change_approve(request: Request, sid: str, cid: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    ch = s.party_change(cid)
    if ch is not None and ch.status == "pending":
        ch.status = "applying"  # so the returned card is the self-refreshing state
        asyncio.create_task(flow.apply_party_change(s, cid))
    return _render("partials/party_change_card.html", request, s=s, ch=ch)


@app.post("/sessions/{sid}/party/changes/{cid}/deny", response_class=HTMLResponse)
async def party_change_deny(request: Request, sid: str, cid: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    ch = s.party_change(cid)
    if ch is not None and ch.status == "pending":
        ch.status = "denied"
    return _render("partials/party_change_card.html", request, s=s, ch=ch)


@app.post("/sessions/{sid}/party/approve-all", response_class=HTMLResponse)
async def party_approve_all(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    pending = [ch.id for ch in s.party_changes if ch.status == "pending"]
    for ch in s.party_changes:
        if ch.status == "pending":
            ch.status = "applying"
    if pending:
        asyncio.create_task(flow.apply_party_changes(s, pending))
    return _render("partials/party_changes.html", request, s=s)


# ---- Question-review party (step 2) ----

@app.post("/sessions/{sid}/party-questions", response_class=HTMLResponse)
async def party_questions_start(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    if s.party_status != "running":
        asyncio.create_task(flow.run_party_questions(s))
    return _render("partials/party_qa_panel.html", request, s=s)


@app.get("/sessions/{sid}/party-questions/panel", response_class=HTMLResponse)
async def party_questions_panel(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return HTMLResponse("")
    return _render("partials/party_qa_panel.html", request, s=s)


@app.get("/sessions/{sid}/party-questions/changes", response_class=HTMLResponse)
async def party_questions_changes(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return HTMLResponse("")
    return _render("partials/party_qa_changes.html", request, s=s)


@app.post("/sessions/{sid}/party-questions/changes/{cid}/approve", response_class=HTMLResponse)
async def party_qa_approve(request: Request, sid: str, cid: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    await flow.apply_qa_change(s, cid)
    # Updated card (primary swap) + an out-of-band refresh of the questions form
    # so the new question / filled answer shows immediately.
    card = _html("partials/party_qa_change_card.html", s=s, ch=s.party_qa_change(cid))
    qlist = _html("partials/question_list.html", s=s, oob=True)
    return HTMLResponse(card + qlist)


@app.post("/sessions/{sid}/party-questions/changes/{cid}/deny", response_class=HTMLResponse)
async def party_qa_deny(request: Request, sid: str, cid: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    ch = s.party_qa_change(cid)
    if ch is not None and ch.status == "pending":
        ch.status = "denied"
    return _render("partials/party_qa_change_card.html", request, s=s, ch=ch)


@app.post("/sessions/{sid}/party-questions/approve-all", response_class=HTMLResponse)
async def party_qa_approve_all(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    for ch in list(s.party_qa_changes):
        if ch.status == "pending":
            await flow.apply_qa_change(s, ch.id)
    changes = _html("partials/party_qa_changes.html", s=s)
    qlist = _html("partials/question_list.html", s=s, oob=True)
    return HTMLResponse(changes + qlist)


# ---- Post-processing QA (final page) ----

@app.get("/sessions/{sid}/sections-fragment", response_class=HTMLResponse)
async def sections_fragment(request: Request, sid: str):
    """All section cards as a group — refetched after a background pass
    (Implement fixes / party) rewrites sections, so the page updates without a reload."""
    s = state.get(sid)
    if s is None:
        return HTMLResponse("")
    return _render("partials/sections_list.html", request, s=s,
                   examples=flow.REFINE_EXAMPLES)


@app.get("/sessions/{sid}/qa", response_class=HTMLResponse)
async def qa_panel(request: Request, sid: str):
    """QA panel shown at the end of step 3 — lint report + deeper-review trigger.
    Loaded on page load and refreshed on sse:job_done (once drafting finishes)."""
    s = state.get(sid)
    if s is None:
        return HTMLResponse("")
    return _render("partials/qa_panel.html", request, s=s, lint=flow.lint_spec(s))


@app.post("/sessions/{sid}/qa-review", response_class=HTMLResponse)
async def qa_review_start(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    if s.qa_review_status != "running":
        # Flip to running synchronously so the returned partial renders the
        # spinner + self-refresh attrs; otherwise the background task hasn't set
        # the status yet and the panel comes back blank and inert.
        s.qa_review_status = "running"
        s.qa_review = []
        asyncio.create_task(flow.run_qa_review(s))
    return _render("partials/qa_review.html", request, s=s)


@app.get("/sessions/{sid}/qa-review", response_class=HTMLResponse)
async def qa_review_panel(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return HTMLResponse("")
    return _render("partials/qa_review.html", request, s=s)


@app.post("/sessions/{sid}/qa-fix", response_class=HTMLResponse)
async def qa_fix_start(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    if s.qa_fix_status != "running":
        s.qa_fix_status = "running"  # set synchronously so the partial shows progress
        asyncio.create_task(flow.run_qa_fix(s))
    return _render("partials/qa_fix.html", request, s=s)


@app.get("/sessions/{sid}/qa-fix", response_class=HTMLResponse)
async def qa_fix_panel(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return HTMLResponse("")
    return _render("partials/qa_fix.html", request, s=s)


@app.get("/sessions/{sid}/megaprompt", response_class=HTMLResponse)
async def megaprompt(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return HTMLResponse("")
    # Escaped: rendered into a pre-wrap div, shown as literal text.
    return HTMLResponse(html.escape(flow.assemble_final(s)))


@app.get("/sessions/{sid}/events")
async def events(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return Response(status_code=404)
    q = s.subscribe()

    async def stream():
        try:
            while True:
                if await request.is_disconnected():
                    return
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                payload = json.dumps(ev["data"]) if not isinstance(ev["data"], str) else ev["data"]
                # SSE requires one `data:` field per line; encode multiline
                # payloads (e.g. error text) so newlines survive intact.
                data = "".join(f"data: {line}\n" for line in payload.split("\n"))
                yield f"event: {ev['event']}\n{data}\n"
        finally:
            s.unsubscribe(q)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/sessions/{sid}/final", response_class=HTMLResponse)
async def final(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    s.phase = "final"
    return _render("step6_final.html", request, s=s,
                   mega_prompt=flow.assemble_final(s))


@app.get("/sessions/{sid}/download.md")
async def download(sid: str):
    s = state.get(sid)
    if s is None:
        return Response(status_code=404)
    return PlainTextResponse(
        flow.assemble_final(s),
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="mega-prompt.md"'},
    )


@app.on_event("shutdown")
async def shutdown():
    await flow.backend.shutdown()
