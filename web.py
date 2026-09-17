"""
AOS web layer — FastAPI + Jinja, server-rendered.

No build step, no npm, no SPA. Pod owners open a page on a mid-range
Android over mobile data, read a queue, open a deliverable, and sign.
The most complex interaction is a form POST; client-side state would be
cost without benefit.

AUTHENTICATION IS STUBBED AND DEV-ONLY. The signing-identity decision is
still open (Telegram OTP vs email magic link vs Workspace accounts for
pod owners), and building OTP now means building it twice. The stub
REFUSES to start outside AOS_ENV=development — a stubbed identity must
never be one environment variable away from production.
"""
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import (FileResponse, HTMLResponse,
                               RedirectResponse)
from fastapi.templating import Jinja2Templates

import aos
import registry as R

AOS_ENV = os.environ.get("AOS_ENV", "development")
BASE = Path(__file__).parent

app = FastAPI(title="AOS", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(BASE / "templates"))



# Pages are reached from several places: the queue, an agent, a family, queue
# health. Sending everyone "home" loses the thread — you came from agent 10 to
# read one of its tasks, and back should return you to agent 10.
#
# Derived from Referer, but never trusted raw: an attacker-controlled Referer
# turned into a link is an open redirect. Only same-origin paths matching our
# own routes are accepted, and anything else falls back to the queue.
_BACK_OK = re.compile(r"^/(agent/[\w-]+|family/\d+|queue|task/[\w-]+/[\w-]+)?$")


def back_link(request: Request, user: str, explicit: str | None = None) -> str:
    """Where the back arrow should point. explicit wins (it survives a POST),
    then Referer, then the queue."""
    candidate = explicit
    if not candidate:
        ref = request.headers.get("referer", "")
        if ref:
            p = urlparse(ref)
            same_origin = (p.netloc == request.url.netloc)
            if same_origin and _BACK_OK.match(p.path):
                candidate = p.path
    if not candidate or not _BACK_OK.match(candidate):
        return f"/?as={user}"
    sep = "&" if "?" in candidate else "?"
    return f"{candidate}{sep}as={user}"


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
def home(request: Request, as_: str | None = Query(None, alias="as")):
    user = current_user(request, as_)
    agents = R.agents_for_user(user)
    return templates.TemplateResponse(request, "queue.html", {
        "user": user,
        "agents": agents,
        "grouped": R.group_by_family(agents),
        "boards": aos.boards_for(user),
        "review": aos.unsigned_amber(user),
        "oversight": [t for t in aos.unsigned_amber(user, mine_only=False)
                      if t["id"] not in {r["id"] for r in aos.unsigned_amber(user)}],
        "blocked": aos.blocked_tasks(user),
        "env": AOS_ENV,
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
                  as_: str | None = Query(None, alias="as")):
    user = current_user(request, as_)
    creatable = aos.creatable_agents(user)
    # Arriving from an agent page scopes the form to that agent. The user
    # already chose; re-presenting the full list makes them choose twice
    # and buries the choice they made in a radio list.
    focus = next((a for a in creatable if a["agent_no"] == agent), None)
    return templates.TemplateResponse(request, "new.html", {
        "user": user,
        "agents": creatable,
        "selected": agent,
        "focus": focus,
        "family": R.family_of(agent) if agent else None,
        "error": request.query_params.get("error"),
    })


@app.post("/new")
def create_task_post(request: Request, agent_no: str = Form(...),
                     title: str = Form(...), body: str = Form(""),
                     priority: int = Form(3), user: str = Form(...)):
    agent = R.get_agent(agent_no)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"unknown agent: {agent_no}")
    try:
        task_id = aos.create_task(user, agent["board"], agent_no,
                                  title, body, priority)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        return RedirectResponse(
            f"/new?as={user}&agent={agent_no}&error={e}", status_code=303)
    return RedirectResponse(
        f"/task/{agent['board']}/{task_id}?as={user}", status_code=303)


@app.get("/task/{board}/{task_id}", response_class=HTMLResponse)
def task_detail(request: Request, board: str, task_id: str,
                as_: str | None = Query(None, alias="as"),
                back: str | None = Query(None)):
    user = current_user(request, as_)
    try:
        task = aos._get_task(board, task_id)
        aos._authorize(user, board)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    agent_no = R.agent_of_task(task)
    agent = R.get_agent(agent_no) if agent_no else None
    return templates.TemplateResponse(request, "task.html", {
        "back": back_link(request, user, back),
        "user": user,
        "board": board,
        "task": task,
        "agent": agent,
        "files": aos.deliverables(user, board, task_id),
        "runs": aos.runs(user, board, task_id),
        "can_sign": user in R.owners_of(agent_no, "countersigner")
                    if agent_no else False,
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
              as_: str | None = Query(None, alias="as")):
    """Preview a deliverable. Text renders inline; anything else offers
    a download."""
    user = current_user(request, as_)
    try:
        att = aos.attachment(user, board, task_id, att_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except aos.NotSigned as e:
        raise HTTPException(status_code=403, detail=str(e))
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
def do_sign(board: str, task_id: str,
            decision: str = Form(...), note: str = Form(""),
            artifact: str = Form(...), user: str = Form(...),
            back: str = Form("")):
    agent_no = R.agent_of_task(aos._get_task(board, task_id))
    agent = R.get_agent(agent_no)
    try:
        aos.sign(board, task_id, signer=user,
                 signer_role=agent["zone"], decision=decision,
                 artifact_path=artifact, note=note)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    # Back to where the reviewer was working. Signing one of five queued
    # items should not eject them to the top of the app.
    dest = back if back and _BACK_OK.match(back) else "/"
    sep = "&" if "?" in dest else "?"
    return RedirectResponse(f"{dest}{sep}as={user}", status_code=303)


@app.post("/unblock/{board}/{task_id}")
def do_unblock(board: str, task_id: str, user: str = Form(...)):
    try:
        aos.unblock(user, board, task_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    # Back to where the reviewer was working. Signing one of five queued
    # items should not eject them to the top of the app.
    dest = back if back and _BACK_OK.match(back) else "/"
    sep = "&" if "?" in dest else "?"
    return RedirectResponse(f"{dest}{sep}as={user}", status_code=303)
