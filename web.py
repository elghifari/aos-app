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
from pathlib import Path

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
        "boards": aos.boards_for(user),
        "review": aos.unsigned_amber(user),
        "blocked": aos.blocked_tasks(user),
        "env": AOS_ENV,
    })


@app.get("/task/{board}/{task_id}", response_class=HTMLResponse)
def task_detail(request: Request, board: str, task_id: str,
                as_: str | None = Query(None, alias="as")):
    user = current_user(request, as_)
    try:
        task = aos._get_task(board, task_id)
        aos._authorize(user, board)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    agent_no = R.agent_of_task(task)
    agent = R.get_agent(agent_no) if agent_no else None
    return templates.TemplateResponse(request, "task.html", {
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
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    return templates.TemplateResponse(request, "file.html", {
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
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    return FileResponse(att["path"], filename=att["filename"],
                        media_type=att["content_type"]
                        or "application/octet-stream")


@app.post("/sign/{board}/{task_id}")
def do_sign(board: str, task_id: str,
            decision: str = Form(...), note: str = Form(""),
            artifact: str = Form(...), user: str = Form(...)):
    agent_no = R.agent_of_task(aos._get_task(board, task_id))
    agent = R.get_agent(agent_no)
    try:
        aos.sign(board, task_id, signer=user,
                 signer_role=agent["zone"], decision=decision,
                 artifact_path=artifact, note=note)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return RedirectResponse(f"/?as={user}", status_code=303)


@app.post("/unblock/{board}/{task_id}")
def do_unblock(board: str, task_id: str, user: str = Form(...)):
    try:
        aos.unblock(user, board, task_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return RedirectResponse(f"/?as={user}", status_code=303)
