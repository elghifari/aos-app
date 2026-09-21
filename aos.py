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


def _scoped_hash(att_id, digest: str) -> str:
    """Bind a recorded signature to one attachment as well as its bytes.

    A bare sha256 says 'these bytes were approved' — which would also
    release a different attachment holding identical content. Scoping to
    the attachment id keeps each deliverable's decision independent.

    Legacy rows written before this change hold a bare digest; the read
    path accepts both, so the production approvals DB needs no migration.
    """
    return f"attachment:{att_id}:sha256:{digest}"


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
         decision: str, artifact_path: str, note: str = "", *,
         expected_hash: str) -> dict:
    """Record an Amber sign-off against one specific attachment.

    Signing authority comes from the registry's countersigner role for the
    agent in question. Works identically for agentic and non-agentic roles —
    a human-drafted article needs the same signature as a model-drafted one.

    `expected_hash` is the sha256 the reviewer was shown. If the bytes on
    disk no longer match it, the signature is refused: a decision must
    attest to what was actually read, not to whatever occupies the path at
    the moment Approve is pressed.

    The recorded hash is scoped to the attachment id, so approving one file
    never releases a sibling that happens to hold identical bytes.
    """
    task = _get_task(board, task_id)
    agent_no = R.agent_of_task(task)
    if agent_no is None:
        raise ValueError(f"task {task_id} is not linked to an agent")

    authorized = R.owners_of(agent_no, AMBER_SIGNER_ROLE)
    if signer not in authorized:
        raise PermissionError(
            f"{signer} is not a qualified signer for agent {agent_no}")
    _authorize(signer, board)

    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'")
    if not expected_hash:
        raise ValueError(
            "expected_hash from the reviewed artifact is required")

    # The path must be an attachment OF THIS TASK, not merely a file
    # somewhere under the board. Otherwise a signature could be pinned to
    # an unrelated task's deliverable.
    path = Path(artifact_path).resolve()
    if not path.is_relative_to((BOARDS / board).resolve()):
        raise PermissionError("artifact resolves outside the board")
    matches = [a for a in deliverables(signer, board, task_id)
               if Path(a["stored_path"]).resolve() == path]
    if not matches:
        raise ValueError("artifact is not an attachment of this task")

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected_hash:
        raise ValueError("artifact changed since preview; review it again")
    now = int(time.time())

    con = sqlite3.connect(APPROVALS_DB)
    con.execute("""
        INSERT INTO approvals
            (board, task_id, agent_no, signer, signer_role, decision,
             note, artifact_hash, signed_at)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (board, task_id, agent_no, signer, signer_role, decision,
          note, _scoped_hash(matches[0]["id"], digest), now))
    con.commit()
    con.close()
    return {"task_id": task_id, "agent_no": agent_no, "signer": signer,
            "decision": decision, "artifact_hash": digest, "signed_at": now}



# Playbook target: the oldest unsigned Amber item stays under 10 working days.
REVIEW_SLA_DAYS = 10


def queue_health(user: str) -> dict:
    """Aggregate state of the review queue, per signer and per agent.

    Individual rows already carry an age. This exists because the shape is
    invisible from them: nobody can see how many items are waiting, whose
    they are, or which agents generate the backlog.

    That matters for a live argument at Talenta — whether the review gate
    is too strict for a foundation this size, or simply unstaffed. Those
    look identical from inside a slow queue and are opposite problems.
    A signer with four items a week is not a bottleneck; the same signer
    with forty is, and no amount of discipline fixes it.

    Reports oldest-first, since the SLA is on the oldest item, not the mean.
    """
    items = unsigned_amber(user, mine_only=False)

    by_signer: dict[str, list] = {}
    by_agent: dict[str, list] = {}
    for t in items:
        for s in R.owners_of(t["agent_no"], AMBER_SIGNER_ROLE) or ["(unassigned)"]:
            by_signer.setdefault(s, []).append(t)
        by_agent.setdefault(t["agent_no"], []).append(t)

    def summarise(group: dict, label_key: str) -> list[dict]:
        out = []
        for key, ts in group.items():
            ages = [t["age_days"] for t in ts]
            out.append({
                label_key: key,
                "waiting": len(ts),
                "oldest_days": max(ages),
                "breaching": sum(1 for a in ages if a > REVIEW_SLA_DAYS),
                "agent_name": ts[0].get("agent_name"),
                "board": ts[0].get("board"),
            })
        return sorted(out, key=lambda r: -r["oldest_days"])

    ages = [t["age_days"] for t in items]
    return {
        "total_waiting": len(items),
        "oldest_days": max(ages) if ages else 0,
        "breaching": sum(1 for a in ages if a > REVIEW_SLA_DAYS),
        "sla_days": REVIEW_SLA_DAYS,
        "by_signer": summarise(by_signer, "signer"),
        "by_agent": summarise(by_agent, "agent_no"),
        "items": items,
    }


def signing_load(user: str) -> list[dict]:
    """Expected weekly signing load per signer, from agent cadences.

    An estimate, not a measurement — it says what the roster implies, which
    is the number worth having before deciding the gate is too strict. If
    the implied load is small, a slow queue is an attention problem, not a
    design problem.
    """
    PER_WEEK = {"continuous": 5.0, "weekly": 1.0, "per piece": 1.0,
                "per vacancy": 0.5, "batch": 0.5, "ongoing": 0.5,
                "monthly": 0.25, "per cycle": 0.25, "per project": 0.25,
                "quarterly": 0.08}
    load: dict[str, dict] = {}
    for board in boards_for(user):
        for a in R.agents_on_board(board):
            if a["zone"] != "amber" or not a["active"]:
                continue
            est = PER_WEEK.get(a["cadence"] or "", 0.5)
            for s in R.owners_of(a["agent_no"], AMBER_SIGNER_ROLE) or ["(unassigned)"]:
                e = load.setdefault(s, {"signer": s, "per_week": 0.0, "agents": []})
                e["per_week"] += est
                e["agents"].append(f"{a['agent_no']} ({a['cadence'] or 'ad hoc'})")
    for e in load.values():
        e["per_week"] = round(e["per_week"], 1)
    return sorted(load.values(), key=lambda r: -r["per_week"])


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


def _digest_is_ambiguous(board: str, task_id: str, digest: str) -> bool:
    """True when more than one of this task's attachments holds these bytes.

    Only matters for legacy bare-digest approvals, which cannot name the
    file they were recorded against.
    """
    con = _connect(board)
    rows = con.execute(
        "SELECT * FROM task_attachments WHERE task_id = ?", (task_id,)).fetchall()
    con.close()
    seen = 0
    for row in rows:
        try:
            path = _attachment_path(board, dict(row))
        except (OSError, PermissionError):
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            seen += 1
            if seen > 1:
                return True
    return False


def _artifact_state(board: str, task_id: str, att_id, digest: str) -> dict:
    """Review state of ONE attachment at its CURRENT bytes.

    Looks for a decision recorded against this attachment and this digest.
    Anything else — a decision on a sibling file, on an earlier version of
    this file, or on another task — is not a match, so tampering and
    cross-file leakage both resolve to 'pending' rather than 'approved'.
    """
    task = _get_task(board, task_id)
    agent_no = R.agent_of_task(task)
    agent = R.get_agent(agent_no) if agent_no else None
    zone = agent["zone"] if agent else None

    con = sqlite3.connect(f"file:{APPROVALS_DB}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        # New rows are attachment-scoped. Legacy rows hold a bare sha256
        # and are accepted too — but only when this task has exactly one
        # attachment carrying those bytes, since a bare digest cannot say
        # WHICH file was reviewed. Ambiguous legacy rows resolve to
        # pending rather than releasing a file nobody signed.
        accepted = [_scoped_hash(att_id, digest)]
        if not _digest_is_ambiguous(board, task_id, digest):
            accepted.append(digest)
        row = con.execute(f"""
            SELECT * FROM approvals
            WHERE board = ? AND task_id = ?
              AND artifact_hash IN ({','.join('?' * len(accepted))})
            ORDER BY signed_at DESC, id DESC LIMIT 1
        """, (board, task_id, *accepted)).fetchone()
    finally:
        con.close()

    last = dict(row) if row else None
    if last:
        last["artifact_hash"] = digest

    if zone != "amber":
        state = "not_required"
    elif last is None:
        state = "pending"
    else:
        state = last["decision"]

    reason = None
    if state == "pending":
        who = R.owners_of(agent_no or "", AMBER_SIGNER_ROLE) or ["an assigned signer"]
        reason = f"Awaiting sign-off by {', '.join(who)} for these exact bytes."
    elif state == "rejected":
        reason = f"Rejected by {last['signer']}. Not releasable."

    return {"zone": zone, "approved": state in ("approved", "not_required"),
            "state": state, "last": last, "reason": reason}


def _attachment_path(board: str, att: dict) -> Path:
    """Resolve an attachment's bytes, refusing anything outside the board.

    The value comes from Hermes's DB rather than the request, but a serving
    route that trusts a filesystem path out of a database is one bad row
    away from serving arbitrary files.
    """
    path = Path(att["stored_path"]).resolve()
    if not path.is_relative_to((BOARDS / board).resolve()):
        raise PermissionError(
            f"attachment {att['id']} resolves outside {board}: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"file missing on disk: {path}")
    return path


def signature_state(board: str, task_id: str) -> dict:
    """Task-level release state: the weakest state across all attachments.

    A task is releasable only when every current attachment is approved.
    Reports rejection ahead of pending so the actionable problem surfaces
    first.
    """
    task = _get_task(board, task_id)
    agent_no = R.agent_of_task(task)
    agent = R.get_agent(agent_no) if agent_no else None
    zone = agent["zone"] if agent else None
    if zone != "amber":
        return {"zone": zone, "approved": True, "state": "not_required",
                "reason": None, "last": None}

    con = _connect(board)
    rows = con.execute(
        "SELECT * FROM task_attachments WHERE task_id = ? ORDER BY id",
        (task_id,)).fetchall()
    con.close()

    states = []
    for row in rows:
        att = dict(row)
        try:
            path = _attachment_path(board, att)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except (OSError, PermissionError):
            states.append({"zone": zone, "approved": False, "state": "pending",
                           "last": None,
                           "reason": "Attachment unavailable; not releasable."})
            continue
        states.append(_artifact_state(board, task_id, att["id"], digest))

    for blocking in ("rejected", "pending"):
        found = next((s for s in states if s["state"] == blocking), None)
        if found:
            return found
    if states:
        return states[-1]
    return {"zone": zone, "approved": False, "state": "pending", "last": None,
            "reason": "No attached artifact to review."}


# How a raw kanban status reads to someone who just wants their work.
# The board's vocabulary is the dispatcher's, not the requester's: "done"
# means the worker exited, and a task can sit in "blocked" for days looking
# no different from one nobody has picked up yet.
PROGRESS = {
    "triage":      ("Not started", "Waiting to be picked up."),
    "todo":        ("Not started", "Queued, no worker yet."),
    "scheduled":   ("Not started", "Scheduled to run later."),
    "ready":       ("Not started", "Ready for a worker to claim."),
    "in_progress": ("Working on it now", "A worker is running this."),
    "review":      ("Finished", "Waiting on a person to review it."),
    "done":        ("Finished", "The worker finished and produced its result."),
    "blocked":     ("Stopped", "It stopped and will not restart by itself."),
    "archived":    ("Archived", "Closed and kept for the record."),
}


def progress(task: dict) -> dict:
    """Plain-language state of one task, for display.

    Returns the headline, an explanation, and whether the work is actually
    finished — so a page can stop claiming a blocked task was 'completed by'
    anyone.
    """
    status = task.get("status") or ""
    label, detail = PROGRESS.get(status, ("Unknown", f"Board status: {status}."))
    if status == "blocked" and task.get("last_failure_error"):
        detail = f"{detail} Last error: {task['last_failure_error']}"
    return {"status": status, "label": label, "detail": detail,
            "finished": status in ("done", "review", "archived"),
            "running": status == "in_progress",
            "stopped": status == "blocked"}


def can_review(user: str, board: str, task_id: str) -> bool:
    """Is this person the qualified signer for this task's agent?

    Cheap enough to call before serving a preview, and it keeps the web
    layer from having to know how signing authority is resolved.
    """
    try:
        task = _get_task(board, task_id)
    except (ValueError, FileNotFoundError):
        return False
    agent_no = R.agent_of_task(task)
    return bool(agent_no) and user in R.owners_of(agent_no, AMBER_SIGNER_ROLE)


def attachment(user: str, board: str, task_id: str, att_id: str,
               review: bool = False) -> dict:
    """Resolve one deliverable for serving, with authorization.

    `review=True` is the reviewer's read: it returns a PENDING or REJECTED
    artifact to the qualified countersigner of that agent, and to nobody
    else. Reviewing a file you cannot open is not review — but reading it
    to decide is not the same as releasing it, so the ordinary path below
    stays gated on an approval.
    """
    task = _get_task(board, task_id)
    agent_no = R.agent_of_task(task)
    can_sign = user in R.owners_of(agent_no or "", AMBER_SIGNER_ROLE)

    if review and not can_sign:
        raise PermissionError(
            f"{user} is not a qualified signer for agent {agent_no}")

    # A consumer is not on the board. They reach exactly one thing: a
    # signed deliverable of an agent they are named against. Board access
    # is checked only for accountable roles.
    if user not in R.consumers_of(agent_no or ""):
        _authorize(user, board)

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
    path = _attachment_path(board, d)
    d["path"] = path
    d["artifact_hash"] = hashlib.sha256(path.read_bytes()).hexdigest()
    gate = _artifact_state(board, task_id, d["id"], d["artifact_hash"])

    # THE SIGNATURE GATE.
    # An Amber deliverable is not releasable until a qualified signer has
    # approved these exact bytes. Without this the signature is decoration:
    # a content writer could download an unsigned evidence table and draft
    # from claims nobody cleared, which is the exact failure the CEO
    # constraint on agent 03 exists to prevent — just relocated from the
    # model to the human.
    #
    # Green ships unsigned by design, so this only bites where it should.
    if not gate["approved"] and not review:
        raise NotSigned(gate["reason"])

    d["signature"] = gate
    d["can_sign"] = can_sign
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

    out = []
    for t in tasks_for(user, agent["board"]):
        if t["agent_no"] != agent_no:
            continue
        # An approval ROW is not an approved TASK: the last decision may
        # have been a rejection, and a second attachment may be unsigned.
        # Rendering any row as "signed" is how rejected work disappears
        # from the queue wearing a green badge.
        state = signature_state(agent["board"], t["id"])
        out.append({**t, "board": agent["board"],
                    "review_state": state["state"],
                    "review_reason": state["reason"],
                    "signed": state["state"] == "approved"})
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

    out = []
    for board in boards_for(user):
        for t in tasks_for(user, board):
            if t["status"] != "done":
                continue
            agent = R.get_agent(t["agent_no"]) if t["agent_no"] else None
            if not agent or agent["zone"] != "amber":
                continue
            if mine_only and t["agent_no"] not in signable:
                continue
            # Still waiting unless every current attachment is approved.
            # A rejected item remains here: someone has to act on it.
            state = signature_state(board, t["id"])
            if state["state"] == "approved":
                continue
            age = (time.time() - (t["completed_at"] or 0)) / 86400
            out.append({**t, "board": board, "agent_name": agent["name"],
                        "review_state": state["state"],
                        "review_reason": state["reason"],
                        "age_days": round(age, 1)})
    return sorted(out, key=lambda r: -r["age_days"])
