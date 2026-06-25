import asyncio
import html
import json
import logging
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import (
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app import audit, auth, config, jira, markdown_adf, repo, settings
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

PROJECT_TYPES = [
    ("new", "New project", "Greenfield — starting from scratch"),
    ("existing", "Existing codebase", "Adding to / changing something that exists"),
]
# Stakes is no longer asked — every spec is calibrated as production-grade.
# Form factor is no longer asked either — it's inferred from the idea (see
# flow.run_clarify / _infer_calibration) so it can't contradict the spec.
DEFAULT_STAKES = "serious"

# Server-side cap on free-text inputs (idea / refine instruction / answers) so a
# pathological payload can't blow up prompt size or memory. Inputs longer than
# this are silently truncated.
MAX_INPUT_CHARS = 20_000


def _cap(text: str) -> str:
    """Truncate a free-text input to MAX_INPUT_CHARS."""
    return text[:MAX_INPUT_CHARS]


# (value, human label) for the settings reasoning-effort <select>. Values must
# stay in sync with settings.REASONING_EFFORTS.
REASONING_EFFORT_OPTIONS = [
    ("default", "Default (model decides)"),
    ("none", "Off (none)"),
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
]


def _calibration_ctx() -> dict:
    """Option lists for the calibration controls on step 1."""
    return {"project_types": PROJECT_TYPES}


def _settings_ctx(**extra) -> dict:
    """Context for the settings panel that never echoes the stored API key.

    Render an empty key field with a masked 'key set' hint instead, so the
    secret is not reflected into the HTML. `extra` carries one-shot flags such
    as error / saved."""
    key = settings.current.api_key or ""
    last4 = key[-4:] if len(key) >= 4 else ("•" * len(key))
    return {
        "cfg": settings.current,
        "openai": config.BACKEND == "openai",
        "has_api_key": bool(key),
        "api_key_hint": last4,
        "efforts": REASONING_EFFORT_OPTIONS,
        **extra,
    }


def _render(name: str, request: Request, headers: dict | None = None, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request, name, ctx, headers=headers)


def _html(name: str, **ctx) -> str:
    """Render a partial to a string (for concatenating OOB swaps in one response)."""
    return templates.env.get_template(name).render(**ctx)


def _push(s) -> dict:
    """HX-Push-Url header so refresh/back lands on the session resume route."""
    return {"HX-Push-Url": f"/sessions/{s.id}"}


# ---- Auth-session cookie (opaque, signed; tokens stay server-side) ----------
# The cookie carries ONLY a signed session id (itsdangerous). The GitHub /
# Atlassian access tokens live in app/auth.py and never reach the browser.
AUTH_COOKIE = "incipit_auth"
_COOKIE_SALT = "incipit-auth"


def _serializer() -> URLSafeTimedSerializer:
    # Built per call so a rotated SESSION_COOKIE_SECRET (or a test monkeypatch)
    # takes effect without re-importing the module.
    return URLSafeTimedSerializer(config.SESSION_COOKIE_SECRET, salt=_COOKIE_SALT)


def _read_sid(request: Request) -> str | None:
    """Return the verified session id from the request cookie, or None if the
    cookie is missing, tampered with, or older than the session TTL."""
    raw = request.cookies.get(AUTH_COOKIE)
    if not raw:
        return None
    try:
        return _serializer().loads(raw, max_age=config.SESSION_TTL)
    except (BadSignature, SignatureExpired):
        return None


def _set_auth_cookie(response: Response, sid: str) -> None:
    """Attach the signed session-id cookie with the hardened flags
    (HttpOnly + Secure unless explicitly disabled for dev).

    SameSite is Lax, not Strict: the OAuth callbacks (/auth/*/callback) are
    reached via a top-level cross-site redirect from github.com /
    auth.atlassian.com, and a Strict cookie is NOT sent on that navigation, so
    the server could not recover the session id to validate the OAuth `state`.
    Lax is sent on top-level cross-site GETs while still being withheld from
    cross-site subrequests, so it preserves the CSRF protection that matters
    here (the token stays HttpOnly + server-side regardless)."""
    response.set_cookie(
        AUTH_COOKIE, _serializer().dumps(sid),
        max_age=config.SESSION_TTL, httponly=True,
        secure=config.COOKIE_SECURE, samesite="lax", path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE, path="/")


def current_auth(request: Request) -> auth.AuthRecord | None:
    """Resolve the request's auth record (verified cookie → server-side store)."""
    return auth.get_auth(_read_sid(request))


def _github_ctx(request: Request) -> dict:
    """GitHub-login state for the step-1 existing-codebase controls."""
    rec = current_auth(request)
    entry = rec.provider("github") if rec else None
    return {
        "github_configured": bool(config.GITHUB_OAUTH_CLIENT_ID),
        "github_connected": entry is not None,
        "github_login": entry.user_login if entry else "",
    }


async def _apply_repo_selection(request: Request, s) -> None:
    """Copy the user's picked private repos + their GitHub token onto the
    session (server-side) so the wizard can ground drafting in them. The token
    never goes back to the browser; only the opaque session cookie does."""
    if s.project_type != "existing":
        return
    form = await request.form()
    s.selected_repos = [r.strip() for r in form.getlist("selected_repos") if r and r.strip()]
    rec = current_auth(request)
    entry = rec.provider("github") if rec else None
    if entry is not None:
        s.github_token = entry.access_token


def _atlassian_ctx(request: Request) -> dict:
    """Atlassian-login state for the final/export step controls."""
    rec = current_auth(request)
    entry = rec.provider("atlassian") if rec else None
    meta = entry.meta if entry else {}
    return {
        "atlassian_configured": bool(config.ATLASSIAN_OAUTH_CLIENT_ID),
        "atlassian_connected": entry is not None,
        "atlassian_site": meta.get("site_name") or meta.get("site_url", ""),
    }


# Background wizard jobs are fire-and-forget. Keep a strong reference (a bare
# create_task() may be garbage-collected before it finishes) and log any
# unhandled exception (otherwise it's swallowed and the session is left stuck
# mid-phase with no error surfaced).
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)

    def _done(t: asyncio.Task) -> None:
        _background_tasks.discard(t)
        if not t.cancelled() and t.exception() is not None:
            log.error("background task failed", exc_info=t.exception())

    task.add_done_callback(_done)


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
    return _render("partials/settings.html", request, **_settings_ctx())


@app.post("/settings", response_class=HTMLResponse)
async def settings_save(request: Request, base_url: str = Form(""),
                        model: str = Form(""), api_key: str = Form(""),
                        reasoning_effort: str = Form("default")):
    try:
        settings.update(base_url=base_url, model=model, api_key=api_key,
                        reasoning_effort=reasoning_effort)
    except settings.SettingsError as e:
        return _render("partials/settings.html", request,
                       **_settings_ctx(error=str(e)))
    return _render("partials/settings.html", request,
                   **_settings_ctx(saved=True))


@app.post("/settings/models", response_class=HTMLResponse)
async def settings_models(request: Request, base_url: str = Form(""),
                          api_key: str = Form("")):
    from app.llm.openai_compat import list_models
    try:
        models = await list_models(base_url, api_key)
    except GenerationError as e:
        return _render("partials/model_options.html", request, models=[], error=str(e))
    return _render("partials/model_options.html", request, models=models, error="")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return _render("step1_idea.html", request, **_calibration_ctx(),
                   **_github_ctx(request))


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
                       mega_prompt=flow.assemble_final(s), **_atlassian_ctx(request))
    return _render("step1_idea.html", request, **_calibration_ctx(),
                   **_github_ctx(request))


@app.get("/sessions/{sid}/back/{to}", response_class=HTMLResponse)
async def go_back(request: Request, sid: str, to: str):
    """Same-session back navigation; work is preserved."""
    s = state.get(sid)
    if s is None:
        return _render("resume.html", request, body="expired.html", s=None)
    if to == "idea":
        # Re-edit the brain dump with the prior inputs prefilled. (Submitting
        # again starts a fresh draft — accepted.)
        return _render("step1_idea.html", request, idea=s.idea, repo_url=s.repo_url,
                       sel_project_type=s.project_type, **_calibration_ctx(),
                       **_github_ctx(request))
    if to == "clarify":
        s.phase = "clarify"
        return _render("resume.html", request, body="step3_clarify.html", s=s)
    if to == "sections":
        s.phase = "sections"
        return _render("resume.html", request, body="step4_sections.html",
                       s=s, examples=flow.REFINE_EXAMPLES, auto_party=s.auto_party)
    return _render("resume.html", request, body="expired.html", s=None)


@app.post("/sessions", response_class=HTMLResponse)
async def create_session(request: Request, idea: str = Form(...),
                         project_type: str = Form(...), repo_url: str = Form("")):
    s = state.create()
    s.idea = _cap(idea.strip())
    # form_factor is inferred from the idea in run_clarify; stakes is fixed.
    s.project_type, s.form_factor, s.stakes = project_type, "", DEFAULT_STAKES
    s.repo_url = repo_url.strip() if project_type == "existing" else ""
    await _apply_repo_selection(request, s)
    s.phase = "clarify"
    _spawn(flow.run_clarify(s))
    return _render("step3_clarify.html", request, headers=_push(s), s=s)


@app.post("/moonshot", response_class=HTMLResponse)
async def moonshot(request: Request, idea: str = Form(...),
                   project_type: str = Form(""), repo_url: str = Form("")):
    s = state.create()
    s.idea = _cap(idea.strip())
    # Honor the project_type the user set on step 1; run_moonshot infers the
    # rest (form factor always inferred now). Stakes is fixed to the default.
    s.project_type, s.form_factor, s.stakes = project_type, "", DEFAULT_STAKES
    s.repo_url = repo_url.strip() if project_type == "existing" else ""
    await _apply_repo_selection(request, s)
    s.phase = "moonshot"
    _spawn(flow.run_moonshot(s))
    return _render("step_moonshot.html", request, headers=_push(s), s=s)


@app.get("/sessions/{sid}/moon/status")
async def moon_status(sid: str):
    s = state.get(sid)
    if s is None:
        return Response(status_code=404)
    # Best-effort sub-steps can set s.error while the moonshot task continues.
    # Redirect only after the task reaches a terminal state.
    if s.phase == "final" or (s.error and s.moonshot_status == "error"):
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
        qa.answer = _cap(str(form.get(f"answer_{i}", "")).strip())
    # "Submit & Party" sets party=1: convene the round table once the draft lands.
    s.auto_party = bool(form.get("party"))
    flow.init_sections(s)
    _spawn(flow.run_sections(s))
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
    _spawn(flow.run_single_section(s, section_id))
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
    _spawn(flow.run_refine(s, section_id, _cap(instruction)))
    return _render("partials/section_card.html", request, s=s, sec=sec,
                   examples=flow.REFINE_EXAMPLES)


# ---- Party mode (round-table review on the final spec) ----

@app.post("/sessions/{sid}/party", response_class=HTMLResponse)
async def party_start(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    if s.party_status != "running":
        _spawn(flow.run_party(s))
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
        _spawn(flow.apply_party_change(s, cid))
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
        _spawn(flow.apply_party_changes(s, pending))
    return _render("partials/party_changes.html", request, s=s)


# ---- Question-review party (step 2) ----

@app.post("/sessions/{sid}/party-questions", response_class=HTMLResponse)
async def party_questions_start(request: Request, sid: str):
    s = state.get(sid)
    if s is None:
        return _render("expired.html", request)
    if s.party_status != "running":
        _spawn(flow.run_party_questions(s))
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
    (party round table) rewrites sections, so the page updates without a reload."""
    s = state.get(sid)
    if s is None:
        return HTMLResponse("")
    return _render("partials/sections_list.html", request, s=s,
                   examples=flow.REFINE_EXAMPLES)


@app.get("/sessions/{sid}/step3-actions", response_class=HTMLResponse)
async def step3_actions(request: Request, sid: str):
    """Step-3 bottom bar — Back during drafting, then Party / Finish."""
    s = state.get(sid)
    if s is None:
        return HTMLResponse("")
    return _render("partials/step3_actions.html", request, s=s)


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
                # The `error` channel carries raw model/upstream text that the
                # client innerHTML-swaps into #status-bar; escape it to prevent
                # reflected XSS. Other channels (progress, model_loading, moon,
                # party_msg) carry server-built trusted HTML and must not be
                # escaped.
                if ev["event"] == "error" and isinstance(ev["data"], str):
                    payload = html.escape(payload)
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
                   mega_prompt=flow.assemble_final(s), **_atlassian_ctx(request))


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


# ---- GitHub OAuth login -----------------------------------------------------
# Flow: /auth/github/login mints a session + CSRF state, sets the signed cookie,
# and 302s to GitHub. GitHub redirects back to /auth/github/callback?code&state;
# we exchange the code for a token, fetch the user, store the token server-side
# (app/auth.py), audit it, and redirect back to where the user started. The
# browser only ever holds the opaque signed session id.

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


def _safe_return_to(value: str | None) -> str:
    """Only allow same-app relative redirects (no open-redirect via //host)."""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return "/"


@app.get("/auth/github/login")
async def github_login(request: Request, return_to: str = "/"):
    if not config.GITHUB_OAUTH_CLIENT_ID:
        return PlainTextResponse("GitHub login is not configured.", status_code=503)
    # Reuse an existing session if the cookie is valid, else start a new one.
    rec = current_auth(request) or auth.create_auth()
    state = auth.new_state(rec, "github", _safe_return_to(return_to))
    params = {
        "client_id": config.GITHUB_OAUTH_CLIENT_ID,
        "redirect_uri": config.GITHUB_OAUTH_REDIRECT_URL,
        "scope": config.GITHUB_OAUTH_SCOPES,
        "state": state,
        "allow_signup": "false",
    }
    resp = RedirectResponse(f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}", status_code=302)
    _set_auth_cookie(resp, rec.id)
    return resp


@app.get("/auth/github/callback")
async def github_callback(request: Request, code: str = "", state: str = "",
                          error: str = ""):
    rec = current_auth(request)
    if rec is None:
        return PlainTextResponse("Auth session expired; please log in again.",
                                 status_code=400)
    payload = auth.pop_state(rec, state, "github")
    if payload is None:
        return PlainTextResponse("Invalid or expired OAuth state.", status_code=400)
    return_to = _safe_return_to(payload.get("return_to"))
    if error or not code:
        # User denied, or GitHub returned an error — back to where they started.
        return RedirectResponse(return_to, status_code=302)

    async with httpx.AsyncClient(timeout=config.REPO_TIMEOUT) as c:
        tok = await c.post(GITHUB_TOKEN_URL, headers={"Accept": "application/json"},
                           data={
                               "client_id": config.GITHUB_OAUTH_CLIENT_ID,
                               "client_secret": config.GITHUB_OAUTH_CLIENT_SECRET,
                               "code": code,
                               "redirect_uri": config.GITHUB_OAUTH_REDIRECT_URL,
                           })
        token_data = tok.json() if tok.status_code == 200 else {}
        access_token = token_data.get("access_token", "")
        if not access_token:
            return PlainTextResponse("GitHub did not return an access token.",
                                     status_code=400)
        ur = await c.get(GITHUB_USER_URL, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "incipit",
        })
        user = ur.json() if ur.status_code == 200 else {}

    auth.set_provider(rec, "github", access_token=access_token,
                      scope=token_data.get("scope", ""),
                      token_type=token_data.get("token_type", "bearer"),
                      user_id=str(user.get("id", "")),
                      user_login=user.get("login", ""))
    audit.token_issued("github", user_id=str(user.get("id", "")),
                       user_login=user.get("login", ""), scope=token_data.get("scope", ""))
    resp = RedirectResponse(return_to, status_code=302)
    _set_auth_cookie(resp, rec.id)  # refresh the cookie's max-age
    return resp


@app.post("/auth/github/logout")
async def github_logout(request: Request):
    rec = current_auth(request)
    if rec is not None:
        entry = auth.revoke(rec, "github")
        if entry is not None:
            audit.token_revoked("github", user_id=entry.user_id,
                                 user_login=entry.user_login)
    # Clear the cookie and tell HTMX to refresh so the UI reflects logged-out.
    resp = Response(status_code=204, headers={"HX-Refresh": "true"})
    _clear_auth_cookie(resp)
    return resp


@app.get("/api/github/repos", response_class=HTMLResponse)
async def github_repos(request: Request):
    """The signed-in user's private repos, as a searchable multi-select partial.
    401 (not signed in / token rejected) renders the re-authorize modal instead,
    which the client swaps in via the htmx:beforeSwap 401 handler."""
    rec = current_auth(request)
    entry = rec.provider("github") if rec else None
    if entry is None:
        return HTMLResponse(
            _html("partials/github_error.html",
                  reason="You're not signed in to GitHub. Log in to pick your private repos."),
            status_code=401)
    try:
        repos = await repo.list_private_repos(entry.access_token)
    except repo.GitHubAuthError:
        return HTMLResponse(
            _html("partials/github_error.html",
                  reason="GitHub rejected your session (the token expired or was revoked)."),
            status_code=401)
    return _render("partials/github_repos.html", request, repos=repos)


# ---- Atlassian (Jira) OAuth 2.0 / 3LO login ---------------------------------
# Mirrors the GitHub flow: /auth/atlassian/login mints a CSRF state, sets the
# signed cookie, and 302s to Atlassian with `offline_access` appended so we get
# a refresh token. The callback exchanges the code, caches the user's cloudId +
# site via accessible-resources, and stores access+refresh+expiry server-side
# (app/auth.py). The browser only ever holds the opaque signed session id.

ATLASSIAN_AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
ATLASSIAN_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"

# Refresh the access token when it's within this many seconds of expiry (or
# already expired), so an export never starts with a token about to lapse.
ATLASSIAN_REFRESH_SKEW = 60


class AtlassianAuthError(Exception):
    """Raised when the current session has no usable Atlassian token (not
    signed in, or a refresh failed) so callers can surface the re-authorize
    modal instead of a generic 500 — mirrors repo.GitHubAuthError."""


def _atlassian_scope() -> str:
    """Configured scopes plus `offline_access` (appended at request time, not a
    console scope) so Atlassian returns a refresh token."""
    scopes = config.ATLASSIAN_OAUTH_SCOPES.split()
    if "offline_access" not in scopes:
        scopes.append("offline_access")
    return " ".join(scopes)


@app.get("/auth/atlassian/login")
async def atlassian_login(request: Request, return_to: str = "/"):
    if not config.ATLASSIAN_OAUTH_CLIENT_ID:
        return PlainTextResponse("Atlassian login is not configured.", status_code=503)
    rec = current_auth(request) or auth.create_auth()
    state = auth.new_state(rec, "atlassian", _safe_return_to(return_to))
    params = {
        "audience": "api.atlassian.com",
        "client_id": config.ATLASSIAN_OAUTH_CLIENT_ID,
        "scope": _atlassian_scope(),
        "redirect_uri": config.ATLASSIAN_OAUTH_REDIRECT_URL,
        "state": state,
        "response_type": "code",
        "prompt": "consent",
    }
    resp = RedirectResponse(f"{ATLASSIAN_AUTHORIZE_URL}?{urlencode(params)}", status_code=302)
    _set_auth_cookie(resp, rec.id)
    return resp


@app.get("/auth/atlassian/callback")
async def atlassian_callback(request: Request, code: str = "", state: str = "",
                             error: str = ""):
    rec = current_auth(request)
    if rec is None:
        return PlainTextResponse("Auth session expired; please log in again.",
                                 status_code=400)
    payload = auth.pop_state(rec, state, "atlassian")
    if payload is None:
        return PlainTextResponse("Invalid or expired OAuth state.", status_code=400)
    return_to = _safe_return_to(payload.get("return_to"))
    if error or not code:
        # User denied, or Atlassian returned an error — back to where they were.
        return RedirectResponse(return_to, status_code=302)

    async with httpx.AsyncClient(timeout=config.REPO_TIMEOUT) as c:
        tok = await c.post(ATLASSIAN_TOKEN_URL, json={
            "grant_type": "authorization_code",
            "client_id": config.ATLASSIAN_OAUTH_CLIENT_ID,
            "client_secret": config.ATLASSIAN_OAUTH_CLIENT_SECRET,
            "code": code,
            "redirect_uri": config.ATLASSIAN_OAUTH_REDIRECT_URL,
        })
        token_data = tok.json() if tok.status_code == 200 else {}
        access_token = token_data.get("access_token", "")
        if not access_token:
            return PlainTextResponse("Atlassian did not return an access token.",
                                     status_code=400)
        # Resolve the user's accessible Jira site(s) → cloudId + site URL.
        rr = await c.get(ATLASSIAN_RESOURCES_URL, headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        })
        resources = rr.json() if rr.status_code == 200 else []

    first = resources[0] if isinstance(resources, list) and resources else {}
    meta = {
        "cloud_id": first.get("id", ""),
        "site_url": first.get("url", ""),
        "site_name": first.get("name", "") or first.get("url", ""),
    }
    auth.set_provider(rec, "atlassian", access_token=access_token,
                      refresh_token=token_data.get("refresh_token", ""),
                      scope=token_data.get("scope", ""),
                      token_type=token_data.get("token_type", "bearer"),
                      expires_at=_expires_at(token_data.get("expires_in")),
                      user_id=meta["cloud_id"], user_login=meta["site_name"],
                      meta=meta)
    audit.token_issued("atlassian", user_id=meta["cloud_id"],
                       user_login=meta["site_name"], scope=token_data.get("scope", ""))
    resp = RedirectResponse(return_to, status_code=302)
    _set_auth_cookie(resp, rec.id)  # refresh the cookie's max-age
    return resp


@app.post("/auth/atlassian/logout")
async def atlassian_logout(request: Request):
    rec = current_auth(request)
    if rec is not None:
        entry = auth.revoke(rec, "atlassian")
        if entry is not None:
            audit.token_revoked("atlassian", user_id=entry.user_id,
                                 user_login=entry.user_login)
    # HX-Refresh re-renders the final page so the connected chip disappears.
    return Response(status_code=204, headers={"HX-Refresh": "true"})


# ---- Jira export (issue creation over REST) ---------------------------------
# /api/jira/projects loads the user's projects into the picker (refreshing the
# token first); /api/jira/export builds the mega-prompt, converts it to ADF,
# creates the issue, attaches the raw .md, and audits the export — all inside a
# time budget. A lapsed Atlassian session answers 401 with the re-authorize
# modal (same beforeSwap handler as the GitHub path).

def _jira_unauthorized() -> HTMLResponse:
    return HTMLResponse(
        _html("partials/jira_error.html",
              reason="Your Atlassian session has expired. Re-authorize to export to Jira."),
        status_code=401)


def _jira_summary(s) -> str:
    """A concise issue summary derived from the idea."""
    idea = " ".join((s.idea or "").split())
    if not idea:
        return "Incipit mega-prompt"
    return f"Incipit brief: {idea[:120]}"


@app.get("/api/jira/projects", response_class=HTMLResponse)
async def jira_projects(request: Request, sid: str = ""):
    """The connected user's projects + issue-type options as the export form.
    401 (not signed in / refresh failed) renders the re-authorize modal."""
    rec = current_auth(request)
    try:
        entry = await refresh_atlassian_token(rec)
    except AtlassianAuthError:
        return _jira_unauthorized()
    cloud_id = entry.meta.get("cloud_id", "")
    try:
        projects = await jira.list_projects(cloud_id, entry.access_token)
    except jira.JiraError as e:
        log.warning("jira project/search failed: %s", e)
        return HTMLResponse(
            _html("partials/jira_error.html",
                  reason="Couldn't load your Jira projects. Re-authorize and try again."),
            status_code=401)
    return _render("partials/jira_projects.html", request, sid=sid, projects=projects,
                   issue_types=config.JIRA_ISSUE_TYPES,
                   default_project=config.JIRA_DEFAULT_PROJECT_KEY)


@app.post("/api/jira/export", response_class=HTMLResponse)
async def jira_export(request: Request, sid: str = Form(...),
                      project_key: str = Form(...), issue_type: str = Form("Task")):
    s = state.get(sid)
    if s is None:
        return _render("partials/jira_result.html", request, ok=False,
                       message="That session has expired; start a new one.")
    rec = current_auth(request)
    try:
        entry = await refresh_atlassian_token(rec)
    except AtlassianAuthError:
        return _jira_unauthorized()
    if not project_key:
        return _render("partials/jira_result.html", request, ok=False,
                       message="Pick a project before exporting.")

    cloud_id = entry.meta.get("cloud_id", "")
    site_url = entry.meta.get("site_url", "")
    md = flow.assemble_final(s)
    adf = markdown_adf.to_adf(md)
    summary = _jira_summary(s)
    budget = config.JIRA_EXPORT_TIMEOUT_MS / 1000

    try:
        result = await asyncio.wait_for(
            _export_to_jira(cloud_id, entry.access_token, site_url,
                            project_key, summary, issue_type, adf, md),
            timeout=budget)
    except asyncio.TimeoutError:
        return _render("partials/jira_result.html", request, ok=False,
                       message=(f"Export exceeded the {config.JIRA_EXPORT_TIMEOUT_MS}ms "
                                "budget. Nothing partial was reported — please retry."))
    except jira.JiraError as e:
        return _render("partials/jira_result.html", request, ok=False,
                       message=f"Jira rejected the export: {e}")

    audit.jira_export(project_key, result["key"], user_id=entry.user_id,
                      user_login=entry.user_login, attached=result["attached"])
    return _render("partials/jira_result.html", request, ok=True, key=result["key"],
                   url=result["url"], attached=result["attached"])


async def _export_to_jira(cloud_id, token, site_url, project_key, summary,
                          issue_type, adf, md) -> dict:
    """Create the issue, then best-effort attach the raw .md. Attachment failure
    doesn't fail the export — the issue exists either way; we just flag it."""
    issue = await jira.create_issue(
        cloud_id, token, project_key=project_key, summary=summary,
        issue_type=issue_type, description_adf=adf)
    key = issue["key"]
    attached = True
    try:
        await jira.upload_attachment(cloud_id, token, key, "mega-prompt.md", md)
    except jira.JiraError as e:
        log.warning("jira attachment failed for %s: %s", key, e)
        attached = False
    return {"key": key, "url": jira.browse_url(site_url, key), "attached": attached}


def _expires_at(expires_in) -> float:
    """Convert Atlassian's `expires_in` (seconds) into an absolute epoch; 0 when
    absent so we treat the token as already due for refresh."""
    try:
        return time.time() + int(expires_in)
    except (TypeError, ValueError):
        return 0.0


def _atlassian_token_expiring(entry: auth.ProviderEntry) -> bool:
    """True when the access token is unset, untracked, or within the refresh
    skew of expiry."""
    if not entry.expires_at:
        return True
    return entry.expires_at - time.time() <= ATLASSIAN_REFRESH_SKEW


async def refresh_atlassian_token(rec: auth.AuthRecord | None) -> auth.ProviderEntry:
    """Return a usable Atlassian provider entry, refreshing the access token via
    the stored refresh_token when it's near/after expiry. Raises
    AtlassianAuthError when there's no entry or the refresh fails, so the caller
    can surface the re-authorize modal (same pattern as the GitHub 401 path)."""
    entry = rec.provider("atlassian") if rec else None
    if entry is None:
        raise AtlassianAuthError("not signed in to Atlassian")
    if not _atlassian_token_expiring(entry):
        return entry
    if not entry.refresh_token:
        raise AtlassianAuthError("Atlassian access token expired and no refresh token")
    try:
        async with httpx.AsyncClient(timeout=config.REPO_TIMEOUT) as c:
            tok = await c.post(ATLASSIAN_TOKEN_URL, json={
                "grant_type": "refresh_token",
                "client_id": config.ATLASSIAN_OAUTH_CLIENT_ID,
                "client_secret": config.ATLASSIAN_OAUTH_CLIENT_SECRET,
                "refresh_token": entry.refresh_token,
            })
    except httpx.HTTPError as e:
        raise AtlassianAuthError(f"Atlassian token refresh failed: {e}") from e
    if tok.status_code != 200:
        raise AtlassianAuthError("Atlassian rejected the refresh token")
    data = tok.json()
    new_token = data.get("access_token", "")
    if not new_token:
        raise AtlassianAuthError("Atlassian refresh returned no access token")
    entry.access_token = new_token
    entry.expires_at = _expires_at(data.get("expires_in"))
    # Atlassian rotates refresh tokens; keep the new one when provided.
    if data.get("refresh_token"):
        entry.refresh_token = data["refresh_token"]
    if data.get("scope"):
        entry.scope = data["scope"]
    audit.token_refreshed("atlassian", user_id=entry.user_id,
                          user_login=entry.user_login, scope=entry.scope)
    return entry


@app.on_event("shutdown")
async def shutdown():
    await flow.backend.shutdown()
