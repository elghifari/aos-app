"""
AOS web layer — FastAPI + Jinja, server-rendered.

No build step, no npm, no SPA. Pod owners open a page on a mid-range
Android over mobile data, read a queue, open a deliverable, and sign.
The most complex interaction is a form POST; client-side state would be
cost without benefit.

AUTHENTICATION IS STUBBED AND DEV-ONLY
"""
import logging
import os
import re
import secrets
import subprocess
import time
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import (FileResponse, HTMLResponse,
                               RedirectResponse)
from fastapi.templating import Jinja2Templates

import aos
import registry as R

AOS_ENV = os.environ.get("AOS_ENV", "development")
BASE = Path(__file__).parent

app = FastAPI(title="AOS", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(BASE / "templates"))
logger = logging.getLogger(__name__)



# Keep short-lived return locations server-side so navigation URLs stay clean.
# Only same-origin routes matching this app's navigation surface are stored.
_BACK_OK = re.compile(r"^/(agent/[\w-]+|family/\d+|queue|task/[\w-]+/[\w-]+)?$")
_RETURN_SESSION_COOKIE = "aos_return_session"
_RETURN_SESSION_TTL_SECONDS = 600
_RETURN_SESSIONS: dict[str, tuple[float, dict[str, str]]] = {}


@app.middleware("http")
async def persist_return_session(request: Request, call_next):
    response = await call_next(request)
    session_id = getattr(request.state, "return_session_id", None)
    if session_id:
        response.set_cookie(
            _RETURN_SESSION_COOKIE,
            session_id,
            max_age=_RETURN_SESSION_TTL_SECONDS,
            httponly=True,
            samesite="lax",
            secure=AOS_ENV != "development",
        )
    return response


def _valid_return_path(path: str | None) -> str | None:
    return path if path and _BACK_OK.match(path) else None


def _return_session(request: Request, create: bool = False) -> dict[str, str] | None:
    now = time.monotonic()
    if create:
        for stale_id, (expires_at, _) in tuple(_RETURN_SESSIONS.items()):
            if expires_at <= now:
                del _RETURN_SESSIONS[stale_id]
    session_id = request.cookies.get(_RETURN_SESSION_COOKIE)
    entry = _RETURN_SESSIONS.get(session_id) if session_id else None
    if entry and entry[0] <= now:
        del _RETURN_SESSIONS[session_id]
        entry = None
    if not entry:
        if not create:
            return None
        session_id = secrets.token_urlsafe(32)
        entry = (now + _RETURN_SESSION_TTL_SECONDS, {})
    paths = entry[1]
    _RETURN_SESSIONS[session_id] = (now + _RETURN_SESSION_TTL_SECONDS, paths)
    request.state.return_session_id = session_id
    return paths


def _referer_path(request: Request) -> str | None:
    ref = request.headers.get("referer", "")
    if not ref:
        return None
    parsed = urlparse(ref)
    if parsed.netloc != request.url.netloc:
        return None
    return _valid_return_path(parsed.path)


def _remember_return_path(request: Request, user: str,
                          explicit: str | None = None) -> str | None:
    candidate = explicit
    if not candidate:
        candidate = _referer_path(request)
    candidate = _valid_return_path(candidate)
    if candidate:
        returns = _return_session(request, create=True)
        assert returns is not None
        returns[user] = candidate
    return candidate


def _take_return_path(request: Request, user: str) -> str | None:
    returns = _return_session(request)
    candidate = _valid_return_path(returns.pop(user, None) if returns else None)
    return candidate


def _with_user(path: str, user: str) -> str:
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}as={user}"


def back_link(request: Request, user: str, explicit: str | None = None) -> str:
    """Where the back arrow should point: request source, session, queue."""
    candidate = _remember_return_path(request, user, explicit)
    if not candidate:
        returns = _return_session(request)
        candidate = _valid_return_path(returns.get(user) if returns else None)
    return _with_user(candidate or "/", user)


def return_destination(request: Request, user: str, explicit: str | None = None,
                       fallback: str = "/") -> str:
    candidate = (_remember_return_path(request, user, explicit)
                 or _take_return_path(request, user)
                 or fallback)
    return _with_user(candidate, user)


def current_user(request: Request, as_: str | None = None) -> str:
    """DEV STUB. Identity comes from a query parameter.

    Hard-fails outside development rather than falling back to something
    plausible. A system whose central claim is 'every Amber output
    carries a named signature' cannot have a guessable identity.
    """
    if AOS_ENV != "development":
        raise HTTPException(
            status_code=500,
            detail="Stubbed auth cannot run outside development. "
                   "Implement real authentication before deploying.")
    user = as_ or request.query_params.get("as") or "u_hr"
    if not R.agents_for_user(user):
        raise HTTPException(status_code=403, detail=f"unknown user: {user}")
    return user


@app.get("/", response_class=HTMLResponse)
def home(request: Request, as_: str | None = Query(None, alias="as"),
         notice: str | None = Query(None)):
    user = current_user(request, as_)
    agents = R.agents_for_user(user)
    return templates.TemplateResponse(request, "queue.html", {
        "user": user,
        "agents": agents,
        "grouped": R.group_by_family(agents),
        "boards": aos.boards_for(user),
        "work": aos.my_work(user),
        "review": aos.unsigned_amber(user),
        "oversight": [t for t in aos.unsigned_amber(user, mine_only=False)
                      if t["id"] not in {r["id"] for r in aos.unsigned_amber(user)}],
        "blocked": aos.blocked_tasks(user),
        "env": AOS_ENV,
        "notice": notice,
    })


@app.get("/queue", response_class=HTMLResponse)
def queue_health(request: Request, as_: str | None = Query(None, alias="as")):
    user = current_user(request, as_)
    return templates.TemplateResponse(request, "health.html", {
        "user": user,
        "h": aos.queue_health(user),
        "load": aos.signing_load(user),
    })


@app.get("/new", response_class=HTMLResponse)
def new_task_form(request: Request, agent: str | None = Query(None),
                  source_task: str | None = Query(None),
                  as_: str | None = Query(None, alias="as")):
    user = current_user(request, as_)
    return _new_task_form(request, user, agent,
                          request.query_params.get("error"),
                          {"source_task": source_task} if source_task else None,
                          status=200)


def _new_task_form(request: Request, user: str, agent: str | None,
                   error: str | None, values: dict | None, status: int = 422):
    """The task form, used for both the empty case and every rejection.

    Arriving from an agent page scopes the form to that agent. The user
    already chose; re-presenting the full list makes them choose twice and
    buries the choice they made in a radio list.
    """
    creatable = aos.creatable_agents(user)
    focus = next((a for a in creatable if a["agent_no"] == agent), None)
    gate = None
    if focus:
        try:
            gate = aos.gate_state(user, focus["board"], agent)
        except PermissionError:
            gate = None
    sources = []
    if agent == "03b" and gate:
        seen = set()
        for source in gate["sources"]:
            task_id = source["task_id"]
            if task_id not in seen and aos.signature_state(focus["board"], task_id)["state"] == "approved":
                sources.append(source)
                seen.add(task_id)
    return templates.TemplateResponse(request, "new.html", {
        "user": user,
        "agents": creatable,
        "selected": agent,
        "focus": focus,
        "gate": gate,
        "sources": sources,
        "family": R.family_of(agent) if agent else None,
        "error": error,
        "values": values,
    }, status_code=status)


@app.post("/new")
def create_task_post(request: Request, background_tasks: BackgroundTasks,
                     agent_no: str = Form(...),
                     title: str = Form(...), body: str = Form(""),
                     priority: int = Form(3), user: str = Form(...),
                     source_task: str | None = Form(None)):
    user = current_user(request, user)
    agent = R.get_agent(agent_no)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"unknown agent: {agent_no}")
    try:
        task_id = aos.create_task(user, agent["board"], agent_no,
                                  title, body, priority, source_task=source_task,
                                  dispatch_now=False)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except aos.GateNotPassed as e:
        return _new_task_form(request, user, agent_no, str(e),
                              {"title": title, "body": body, "priority": priority,
                               "source_task": source_task})
    except ValueError as e:
        return _new_task_form(request, user, agent_no, str(e),
                              {"title": title, "body": body, "priority": priority,
                               "source_task": source_task})
    except (subprocess.CalledProcessError, OSError) as e:
        logger.error("Task creation failed for agent %s on board %s: %s",
                     agent_no, agent["board"],
                     (e.stderr or "").strip() if isinstance(e, subprocess.CalledProcessError)
                     else type(e).__name__)
        return _new_task_form(
            request, user, agent_no,
            "Could not start the task. Ask IT to check the board before trying again.",
            {"title": title, "body": body, "priority": priority,
             "source_task": source_task}, status=503)
    if agent["is_agentic"]:
        background_tasks.add_task(aos.dispatch_task, agent["board"])
    return RedirectResponse(
        f"/task/{agent['board']}/{task_id}?as={user}", status_code=303)


@app.get("/task/{board}/{task_id}", response_class=HTMLResponse)
def task_detail(request: Request, board: str, task_id: str,
                as_: str | None = Query(None, alias="as"),
                back: str | None = Query(None),
                notice: str | None = Query(None)):
    user = current_user(request, as_)
    if _valid_return_path(back):
        _remember_return_path(request, user, back)
        suffix = f"&notice={quote(notice)}" if notice else ""
        return RedirectResponse(f"/task/{board}/{task_id}?as={user}{suffix}", status_code=303)
    try:
        aos._authorize(user, board)
        task = aos._get_task(board, task_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    agent_no = R.agent_of_task(task)
    agent = R.get_agent(agent_no) if agent_no else None
    return templates.TemplateResponse(request, "task.html", {
        "back": back_link(request, user, back),
        "user": user,
        "board": board,
        "task": task,
        "brief": aos.brief_for_display(task),
        "agent": agent,
        "files": aos.deliverables(user, board, task_id),
        "runs": aos.runs(user, board, task_id),
        "state": aos.signature_state(board, task_id),
        "prog": aos.progress(task),
        "can_sign": aos.can_review(user, board, task_id),
        "can_handoff": agent_no == "03a" and user in R.owners_of("03b", "owner")
            and task["status"] in ("done", "review")
            and aos.signature_state(board, task_id)["state"] == "approved",
        "notice": notice,
    })


@app.get("/agent/{agent_no}", response_class=HTMLResponse)
def agent_detail(request: Request, agent_no: str,
                 as_: str | None = Query(None, alias="as")):
    user = current_user(request, as_)
    agent = R.get_agent(agent_no)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"unknown agent: {agent_no}")
    try:
        tasks = aos.agent_tasks(user, agent_no)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return templates.TemplateResponse(request, "agent.html", {
        "user": user,
        "agent": agent,
        "tasks": tasks,
        "owners": R.owners_of(agent_no, "owner"),
        "countersigners": R.owners_of(agent_no, "countersigner"),
    })


@app.get("/family/{family_no}", response_class=HTMLResponse)
def family_detail(request: Request, family_no: str,
                  as_: str | None = Query(None, alias="as")):
    """A composite agent as a pipeline: stages, and the human gate between
    them. The gate is the control — showing stages as unrelated agents
    hides it."""
    user = current_user(request, as_)
    fam = R.get_family(family_no)
    if fam is None:
        raise HTTPException(status_code=404, detail=f"unknown family: {family_no}")
    try:
        aos._authorize(user, fam["board"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    stages = []
    for st in fam["stages"]:
        stages.append({**st,
                       "tasks": aos.agent_tasks(user, st["agent_no"]),
                       "owners": R.owners_of(st["agent_no"], "owner"),
                       "signers": R.owners_of(st["agent_no"], "countersigner")})
    return templates.TemplateResponse(request, "family.html", {
        "user": user, "fam": fam, "stages": stages})


@app.get("/file/{board}/{task_id}/{att_id}", response_class=HTMLResponse)
def view_file(request: Request, board: str, task_id: str, att_id: str,
              as_: str | None = Query(None, alias="as"),
              back: str | None = Query(None)):
    """Preview a deliverable. Text renders inline; anything else offers
    a download.

    A qualified signer previews in REVIEW mode, so pending and rejected
    Amber work can be read and decided on. Everyone else sees it only
    once it has been approved. The sign form lives here rather than on
    the task page: a signature should attest to a file the signer
    actually opened.
    """
    user = current_user(request, as_)
    if _valid_return_path(back):
        _remember_return_path(request, user, back)
        return RedirectResponse(f"/file/{board}/{task_id}/{att_id}?as={user}", status_code=303)
    reviewing = aos.can_review(user, board, task_id)
    try:
        att = aos.attachment(user, board, task_id, att_id, review=reviewing)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except aos.NotSigned as e:
        dest = _with_user(
            _remember_return_path(request, user, back) or f"/task/{board}/{task_id}",
            user)
        return RedirectResponse(f"{dest}&notice={quote(str(e))}", status_code=303)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    return templates.TemplateResponse(request, "file.html", {
        "back": back_link(request, user, back),
        "user": user,
        "board": board,
        "task_id": task_id,
        "att": att,
        "text": aos.preview_text(att["path"]),
    })


@app.get("/file/{board}/{task_id}/{att_id}/review-raw")
def review_raw_file(request: Request, board: str, task_id: str, att_id: str,
                    as_: str | None = Query(None, alias="as")):
    """The reviewer's copy of an unapproved artifact.

    Separate from /raw so the two intents stay distinct in the code and in
    the logs: this is 'let the signer read it to decide', never 'release
    it'. Restricted to that agent's qualified countersigner.
    """
    user = current_user(request, as_)
    try:
        att = aos.attachment(user, board, task_id, att_id, review=True)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    return FileResponse(att["path"], filename=att["filename"],
                        media_type=att["content_type"]
                        or "application/octet-stream")


@app.get("/file/{board}/{task_id}/{att_id}/raw")
def download_file(request: Request, board: str, task_id: str, att_id: str,
                  as_: str | None = Query(None, alias="as")):
    user = current_user(request, as_)
    try:
        att = aos.attachment(user, board, task_id, att_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except aos.NotSigned as e:
        raise HTTPException(status_code=403, detail=str(e))
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    return FileResponse(att["path"], filename=att["filename"],
                        media_type=att["content_type"]
                        or "application/octet-stream")


@app.post("/sign/{board}/{task_id}")
def do_sign(request: Request, board: str, task_id: str,
            decision: str = Form(...), note: str = Form(""),
            artifact: str = Form(...), user: str = Form(...),
            expected_hash: str = Form(...),
            back: str = Form("")):
    user = current_user(request, user)
    agent_no = R.agent_of_task(aos._get_task(board, task_id))
    agent = R.get_agent(agent_no)
    try:
        aos.sign(board, task_id, signer=user,
                 signer_role=agent["zone"], decision=decision,
                 artifact_path=artifact, note=note,
                 expected_hash=expected_hash)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        # Most likely the file changed between preview and Approve. The
        # reviewer must see the current bytes before deciding again.
        raise HTTPException(status_code=409, detail=str(e))
    return RedirectResponse(return_destination(request, user, back), status_code=303)


@app.post("/dismiss/{board}/{task_id}")
def do_dismiss(request: Request, board: str, task_id: str,
               user: str = Form(...), back: str = Form("")):
    """Clear a finished item off the owner's list. Archives, never deletes."""
    user = current_user(request, user)
    try:
        aos.dismiss(user, board, task_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except aos.CannotDismiss as e:
        dest = return_destination(request, user, back)
        return RedirectResponse(
            f"{dest}&notice={quote(str(e))}", status_code=303)
    return RedirectResponse(return_destination(request, user, back), status_code=303)


@app.post("/unblock/{board}/{task_id}")
def do_unblock(request: Request, board: str, task_id: str, user: str = Form(...),
               back: str = Form("")):
    user = current_user(request, user)
    try:
        aos.unblock(user, board, task_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return RedirectResponse(return_destination(request, user, back), status_code=303)