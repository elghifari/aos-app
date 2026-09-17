"""
AOS authorization, task lifecycle, and the recorded Amber signature.

Sits BESIDE Hermes, never over it. Hermes owns the agent runtime (profiles,
dispatcher, cron, skills). This module owns who may see what, how work is
created and completed, and the signature an accreditor asks for.

Board DBs are read-only here. Writes to tasks go through the `hermes kanban`
CLI so schema invariants stay Hermes's problem.

THIRTEEN OF TWENTY-FIVE ROLES HAVE NO HERMES WORKER. Six are deterministic
n8n pipelines, seven are human seat work. They still need tasks, deliverables,
and signatures on the same boards — so nothing here may assume a task has a
worker behind it.
"""
import hashlib
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

import registry as R

HERMES = Path(os.environ["LOCALAPPDATA"]) / "hermes"
BOARDS = HERMES / "kanban" / "boards"
APPROVALS_DB = Path(__file__).parent / "approvals.db"

# Amber sign-off authority, per pod. Playbook 18.2/18.4.
# Resolved through the registry's countersigner role where one exists.
AMBER_SIGNER_ROLE = "countersigner"


# ---------------------------------------------------------------- authz

def boards_for(user: str) -> list[str]:
    """Derived from agent ownership — a person sees exactly the pods where
    they own at least one agent. No separately-maintained access map to
    drift out of sync with the roster."""
    return R.boards_for(user)


def _connect(board: str) -> sqlite3.Connection:
    db = BOARDS / board / "kanban.db"
    if not db.exists():
        raise FileNotFoundError(f"no such board: {board}")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _authorize(user: str, board: str) -> None:
    if board not in boards_for(user):
        raise PermissionError(f"{user} has no access to {board}")


def tasks_for(user: str, board: str) -> list[dict]:
    """Authorization enforced HERE, before any query runs."""
    _authorize(user, board)
    con = _connect(board)
    rows = con.execute("""
        SELECT t.id, t.title, t.status, t.priority, t.assignee, t.tenant,
               t.result, t.completed_at,
               (SELECT COUNT(*) FROM task_attachments a
                 WHERE a.task_id = t.id) AS deliverables
        FROM tasks t
        ORDER BY t.status, t.priority
    """).fetchall()
    con.close()

    out = []
    for r in rows:
        d = dict(r)
        d["agent_no"] = R.agent_of_task(d)
        d["dispatchable"] = (
            R.is_dispatchable(d["agent_no"]) if d["agent_no"] else None)
        out.append(d)
    return out


def my_tasks(user: str) -> list[dict]:
    """Every task for every agent this person owns, across all their pods."""
    mine = {a["agent_no"] for a in R.agents_for_user(user)}
    out = []
    for board in boards_for(user):
        for t in tasks_for(user, board):
            if t["agent_no"] in mine:
                out.append({**t, "board": board})
    return out


def deliverables(user: str, board: str, task_id: str) -> list[dict]:
    _authorize(user, board)
    con = _connect(board)
    rows = con.execute("""
        SELECT id, filename, stored_path, content_type,
               size AS size_bytes, uploaded_by, created_at
        FROM task_attachments WHERE task_id = ? ORDER BY id
    """, (task_id,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


# ----------------------------------------------------- task lifecycle

def _kanban(board: str, *args: str) -> str:
    cmd = ["hermes", "kanban", "--board", board, *args]
    return subprocess.run(cmd, capture_output=True, text=True,
                          check=True).stdout


def creatable_agents(user: str) -> list[dict]:
    """Agents this person may create work for — the ones they own.

    Countersigners are excluded deliberately. Signing authority is not
    tasking authority: the Clinical Director countersigns 11 agents but
    commissions none of them, and letting a signer commission the work
    they later approve collapses two roles that exist to be separate.
    """
    out = []
    for a in R.agents_for_user(user):
        if a["ownership"] != "owner" or not a["active"]:
            continue
        signers = R.owners_of(a["agent_no"], AMBER_SIGNER_ROLE)
        out.append({**a,
                    "signers": signers,
                    "needs_signature": a["zone"] == "amber",
                    "blocked": a["zone"] == "amber" and not signers})
    return out


def create_task(user: str, board: str, agent_no: str, title: str, body: str,
                priority: int = 3) -> str:
    """Create work for an agent.

    Dispatchability is decided by the registry, not the caller. An agentic
    role is assigned to its pod profile so the dispatcher picks it up; a
    non-agentic role is deliberately left UNASSIGNED so no worker ever
    claims it — its task is completed by a human or an n8n pipeline.
    """
    _authorize(user, board)
    agent = R.get_agent(agent_no)
    if agent is None:
        raise ValueError(f"unknown agent: {agent_no}")
    if agent["board"] != board:
        raise ValueError(
            f"agent {agent_no} belongs to {agent['board']}, not {board}")
    if not agent["active"]:
        raise ValueError(f"agent {agent_no} is not active")
    if user not in R.owners_of(agent_no, "owner"):
        raise PermissionError(f"{user} does not own agent {agent_no}")

    # Refuse to commission Amber work that nobody can sign. The output
    # would complete, fail the release gate, and sit in a queue with no
    # named signer — work done that can never ship.
    if agent["zone"] == "amber" and not R.owners_of(agent_no, AMBER_SIGNER_ROLE):
        raise ValueError(
            f"agent {agent_no} is amber but has no assigned signer. "
            f"Assign one before commissioning work that cannot be released.")

    out = _kanban(board, "create", title, "--body", body,
                  "--priority", str(priority),
                  "--tenant", R.tenant_for(agent_no), "--json")
    task_id = json.loads(out)["id"]

    if agent["is_agentic"]:
        _kanban(board, "assign", task_id, agent["profile"])
    # else: intentionally unassigned. A dispatcher cannot claim an
    # unassigned task, which is exactly the behaviour we want.
    return task_id


def complete_by_human(user: str, board: str, task_id: str,
                      result: str, artifact_path: str | None = None) -> None:
    """Completion path for NON-AGENTIC roles (seat work and n8n output).

    A Hermes worker completes its own task; nobody completes these, so the
    owner does it here. Refuses to touch a task belonging to an agentic
    role — that would let a human silently close work a worker is running.
    """
    _authorize(user, board)
    task = _get_task(board, task_id)
    agent_no = R.agent_of_task(task)
    if agent_no and R.is_dispatchable(agent_no):
        raise ValueError(
            f"task {task_id} belongs to agentic agent {agent_no} — "
            f"its worker completes it, not a human")
    if agent_no and user not in R.owners_of(agent_no):
        raise PermissionError(f"{user} does not own agent {agent_no}")

    if artifact_path:
        _kanban(board, "attach", task_id, artifact_path, "--author", user)
    _kanban(board, "complete", task_id, "--result", result)


def _get_task(board: str, task_id: str) -> dict:
    con = _connect(board)
    row = con.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    con.close()
    if row is None:
        raise ValueError(f"no such task: {task_id}")
    return dict(row)


# ------------------------------------------------------- amber signature

def init_approvals() -> None:
    con = sqlite3.connect(APPROVALS_DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS approvals (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            board         TEXT NOT NULL,
            task_id       TEXT NOT NULL,
            agent_no      TEXT,
            signer        TEXT NOT NULL,
            signer_role   TEXT NOT NULL,
            decision      TEXT NOT NULL CHECK (decision IN ('approved','rejected')),
            note          TEXT,
            artifact_hash TEXT NOT NULL,
            signed_at     INTEGER NOT NULL
        )
    """)
    con.commit()
    con.close()


def sign(board: str, task_id: str, signer: str, signer_role: str,
         decision: str, artifact_path: str, note: str = "") -> dict:
    """Record an Amber sign-off.

    Signing authority comes from the registry's countersigner role for the
    agent in question. Works identically for agentic and non-agentic roles —
    a human-drafted article needs the same signature as a model-drafted one.

    artifact_hash pins the signature to the exact bytes reviewed, so a
    deliverable swapped after sign-off is detectable.
    """
    task = _get_task(board, task_id)
    agent_no = R.agent_of_task(task)
    if agent_no is None:
        raise ValueError(f"task {task_id} is not linked to an agent")

    authorized = R.owners_of(agent_no, AMBER_SIGNER_ROLE)
    if signer not in authorized:
        raise PermissionError(
            f"{signer} is not a qualified signer for agent {agent_no}")

    digest = hashlib.sha256(Path(artifact_path).read_bytes()).hexdigest()
    now = int(time.time())

    con = sqlite3.connect(APPROVALS_DB)
    con.execute("""
        INSERT INTO approvals
            (board, task_id, agent_no, signer, signer_role, decision,
             note, artifact_hash, signed_at)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (board, task_id, agent_no, signer, signer_role, decision,
          note, digest, now))
    con.commit()
    con.close()
    return {"task_id": task_id, "agent_no": agent_no, "signer": signer,
            "decision": decision, "artifact_hash": digest, "signed_at": now}


def blocked_tasks(user: str) -> list[dict]:
    """Work that stopped and will not restart by itself.

    The dispatcher gives up after a small number of consecutive failures
    (2 by default) and parks the task as `blocked`. Nothing notifies
    anyone, so without this view a pod owner's first signal is work that
    silently never arrived — a weekly agent that blocked on Tuesday looks
    identical to one that had nothing to do.

    Shared-quota exhaustion is the common cause: the worker spawns, waits
    on an API call that never returns, dies, retries into the same wall,
    and gives up. That is the dispatcher behaving correctly, but it is
    invisible without somewhere to show it.
    """
    out = []
    for board in boards_for(user):
        _authorize(user, board)
        con = _connect(board)
        rows = con.execute("""
            SELECT id, title, status, assignee, tenant,
                   consecutive_failures, last_failure_error,
                   last_heartbeat_at, created_at
            FROM tasks
            WHERE status = 'blocked'
            ORDER BY last_heartbeat_at DESC
        """).fetchall()
        con.close()
        for r in rows:
            d = dict(r)
            agent_no = R.agent_of_task(d)
            agent = R.get_agent(agent_no) if agent_no else None
            stalled = (time.time() - (d["last_heartbeat_at"] or
                                      d["created_at"] or 0)) / 3600
            out.append({**d, "board": board, "agent_no": agent_no,
                        "agent_name": agent["name"] if agent else "—",
                        "zone": agent["zone"] if agent else None,
                        "stalled_hours": round(stalled, 1),
                        # Visible for oversight, but only the agent's own
                        # owner may retry it. The UI must not offer an
                        # action the caller will be refused.
                        "can_retry": bool(agent_no) and user in
                                     R.owners_of(agent_no, "owner")})
    return sorted(out, key=lambda r: -r["stalled_hours"])


def unblock(user: str, board: str, task_id: str) -> None:
    """Return a blocked task to the queue. Ownership is required — a
    person may only retry work for an agent they own."""
    _authorize(user, board)
    task = _get_task(board, task_id)
    agent_no = R.agent_of_task(task)
    if agent_no and user not in R.owners_of(agent_no):
        raise PermissionError(f"{user} does not own agent {agent_no}")
    _kanban(board, "unblock", task_id)


def runs(user: str, board: str, task_id: str) -> list[dict]:
    """Execution history for one task.

    Hermes records every attempt: which profile ran it, how long, what it
    concluded, and why it failed. For an Amber output this is part of the
    provenance a signer should see — what the worker claims it did, next
    to the file it produced.
    """
    _authorize(user, board)
    con = _connect(board)
    rows = con.execute("""
        SELECT id, profile, status, outcome, summary, error,
               started_at, ended_at, worker_pid
        FROM task_runs WHERE task_id = ? ORDER BY id
    """, (task_id,)).fetchall()
    con.close()

    out = []
    for r in rows:
        d = dict(r)
        if d["started_at"] and d["ended_at"]:
            d["duration_s"] = d["ended_at"] - d["started_at"]
        else:
            d["duration_s"] = None
        out.append(d)
    return out



class NotSigned(Exception):
    """An Amber deliverable was requested before it was signed."""


def signature_state(board: str, task_id: str) -> dict:
    """Is this task's output releasable?

    Green output needs no signature. Amber output is releasable only
    after an approval is recorded — a rejection does not release it.
    """
    task = _get_task(board, task_id)
    agent_no = R.agent_of_task(task)
    agent = R.get_agent(agent_no) if agent_no else None
    zone = agent["zone"] if agent else None

    con = sqlite3.connect(APPROVALS_DB)
    con.row_factory = sqlite3.Row
    row = con.execute("""
        SELECT signer, decision, signed_at, artifact_hash FROM approvals
        WHERE task_id = ? ORDER BY signed_at DESC LIMIT 1
    """, (task_id,)).fetchone()
    con.close()
    last = dict(row) if row else None

    if zone != "amber":
        return {"zone": zone, "approved": True, "reason": None, "last": last}

    if last is None:
        who = R.owners_of(agent_no, AMBER_SIGNER_ROLE) or ["an assigned signer"]
        return {"zone": zone, "approved": False, "last": None,
                "reason": f"Awaiting sign-off by {', '.join(who)}."}

    if last["decision"] != "approved":
        return {"zone": zone, "approved": False, "last": last,
                "reason": f"Rejected by {last['signer']}. Not releasable."}

    return {"zone": zone, "approved": True, "reason": None, "last": last}


def attachment(user: str, board: str, task_id: str, att_id: str) -> dict:
    """Resolve one deliverable for serving, with authorization.

    The stored path is verified to live under the board's own directory
    before anything is read. The value comes from Hermes's DB rather than
    the request, but a serving route that trusts a filesystem path out of
    a database is one bad row away from serving arbitrary files.
    """
    # A consumer is not on the board. They reach exactly one thing: a
    # signed deliverable of an agent they are named against. Board access
    # is checked only for accountable roles.
    task = _get_task(board, task_id)
    agent_no = R.agent_of_task(task)
    if user in R.consumers_of(agent_no or ""):
        pass
    else:
        _authorize(user, board)

    # THE SIGNATURE GATE.
    # An Amber deliverable is not releasable until a qualified signer has
    # approved it. Without this the signature is decoration: a content
    # writer could download an unsigned evidence table and draft from
    # claims nobody cleared, which is the exact failure the CEO
    # constraint on agent 03 exists to prevent — just relocated from the
    # model to the human.
    #
    # Green ships unsigned by design, so this only bites where it should.
    gate = signature_state(board, task_id)
    if gate["zone"] == "amber" and not gate["approved"]:
        raise NotSigned(gate["reason"])

    con = _connect(board)
    row = con.execute("""
        SELECT id, task_id, filename, stored_path, content_type, size,
               uploaded_by, created_at
        FROM task_attachments WHERE id = ? AND task_id = ?
    """, (att_id, task_id)).fetchone()
    con.close()
    if row is None:
        raise ValueError(f"no such attachment: {att_id}")

    d = dict(row)
    path = Path(d["stored_path"]).resolve()
    root = (BOARDS / board).resolve()
    if not path.is_relative_to(root):
        raise PermissionError(
            f"attachment {att_id} resolves outside {board}: {path}")
    if not path.exists():
        raise FileNotFoundError(f"file missing on disk: {path}")
    d["path"] = path
    return d


TEXT_SUFFIXES = {".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".log"}


def preview_text(path: Path, limit: int = 20000) -> str | None:
    """Inline preview for text deliverables. Reviewing a file you cannot
    see is not review, and most agent output is markdown."""
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return None


def agent_tasks(user: str, agent_no: str) -> list[dict]:
    """Every task for one agent. Ownership required — an agent is only
    visible to the people who own or countersign it."""
    agent = R.get_agent(agent_no)
    if agent is None:
        raise ValueError(f"unknown agent: {agent_no}")
    # Viewing an agent requires board access, not ownership: clinical
    # leadership oversees every flow in a pod they are attached to.
    # _authorize() inside tasks_for() enforces the board boundary.

    con = sqlite3.connect(APPROVALS_DB)
    signed = {r[0] for r in con.execute("SELECT task_id FROM approvals")}
    con.close()

    out = []
    for t in tasks_for(user, agent["board"]):
        if t["agent_no"] != agent_no:
            continue
        out.append({**t, "board": agent["board"],
                    "signed": t["id"] in signed})
    return out


def unsigned_amber(user: str, mine_only: bool = True) -> list[dict]:
    """The review queue. Amber tasks that are done but unsigned.

    VISIBILITY VS SIGNING AUTHORITY — these are deliberately different.

    Visibility is board-level: clinical leadership retains sight of every
    clinical flow in a pod they are attached to, even for agents they do
    not personally sign. That is a governance decision, not an oversight
    — the Clinical Director's remit is the clinic's clinical safety, and
    narrowing her view to her own agents would trade real oversight for
    tidy permissions.

    Signing authority is per-agent, and this queue defaults to it. A
    queue headed "needs your signature" must contain only work the
    reader can actually sign, or the one queue that has to stay clean
    fills with items its owner cannot act on. The Clinical Director
    countersigns 11 agents across 4 pods; she is the named bottleneck,
    and noise here is expensive.

    Pass mine_only=False for the oversight view: everything unsigned on
    every board the user can see, including agents they do not sign.

    Playbook metrics this implements:
      - Amber outputs shipped without sign-off  -> must be zero
      - Review queue age (oldest unsigned item) -> <= 10 working days
    """
    signable = set()
    if mine_only:
        signable = {a["agent_no"] for a in R.agents_for_user(user)
                    if a["ownership"] == AMBER_SIGNER_ROLE}
    con = sqlite3.connect(APPROVALS_DB)
    signed = {r[0] for r in con.execute("SELECT task_id FROM approvals")}
    con.close()

    out = []
    for board in boards_for(user):
        for t in tasks_for(user, board):
            if t["status"] != "done" or t["id"] in signed:
                continue
            agent = R.get_agent(t["agent_no"]) if t["agent_no"] else None
            if not agent or agent["zone"] != "amber":
                continue
            if mine_only and t["agent_no"] not in signable:
                continue
            age = (time.time() - (t["completed_at"] or 0)) / 86400
            out.append({**t, "board": board, "agent_name": agent["name"],
                        "age_days": round(age, 1)})
    return sorted(out, key=lambda r: -r["age_days"])
