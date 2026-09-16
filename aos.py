"""
AOS authorization + approval layer.

Sits BESIDE Hermes, never over it. Hermes owns the agent runtime
(profiles, dispatcher, cron, skills). This module owns:
  - which humans may see which pods
  - the recorded Amber signature the playbook requires

Board DBs are read-only here. Writes to tasks go through the
`hermes kanban` CLI so schema invariants stay Hermes's problem.
"""
import hashlib
import os
import sqlite3
import subprocess
import time
from pathlib import Path

HERMES = Path(os.environ["LOCALAPPDATA"]) / "hermes"
BOARDS = HERMES / "kanban" / "boards"
APPROVALS_DB = Path(__file__).parent / "approvals.db"

# ---------------------------------------------------------------- authz

# The entire authorization model. A join, not a filter.
POD_ACCESS = {
    "budi@talenta.id":    ["p1-growth"],
    "sari@talenta.id":    ["p2-access"],
    "siti@talenta.id":    ["p3-people"],
    "quality@talenta.id": ["p4-quality"],
    "yazid@talenta.id":   ["p5-research"],
    "principal@talenta.id": ["p6-education"],
    # Clinical Director signs Amber across every clinical-adjacent pod
    "drsuzy@talenta.id":  ["p1-growth", "p2-access", "p4-quality",
                           "p5-research", "p6-education"],
    "el@talenta.id":      ["*"],  # IT / AI Ops convenor
}

# Who may sign an Amber output, per pod. Playbook 18.2/18.4.
AMBER_SIGNERS = {
    "p1-growth":    ["budi@talenta.id", "drsuzy@talenta.id"],
    "p2-access":    ["drsuzy@talenta.id"],
    "p3-people":    ["siti@talenta.id"],
    "p4-quality":   ["drsuzy@talenta.id"],
    "p5-research":  ["drsuzy@talenta.id", "yazid@talenta.id"],
    "p6-education": ["principal@talenta.id", "drsuzy@talenta.id"],
}


def boards_for(user: str) -> list[str]:
    grants = POD_ACCESS.get(user, [])
    if "*" in grants:
        return sorted(p.name for p in BOARDS.iterdir() if p.is_dir())
    return grants


def _connect(board: str) -> sqlite3.Connection:
    db = BOARDS / board / "kanban.db"
    if not db.exists():
        raise FileNotFoundError(f"no such board: {board}")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def tasks_for(user: str, board: str) -> list[dict]:
    """Authorization is enforced HERE, before any query runs."""
    if board not in boards_for(user):
        raise PermissionError(f"{user} has no access to {board}")
    con = _connect(board)
    rows = con.execute("""
        SELECT t.id, t.title, t.status, t.priority, t.assignee,
               t.result, t.completed_at,
               (SELECT COUNT(*) FROM task_attachments a
                 WHERE a.task_id = t.id) AS deliverables
        FROM tasks t
        ORDER BY t.status, t.priority
    """).fetchall()
    con.close()
    return [dict(r) for r in rows]


def deliverables(user: str, board: str, task_id: str) -> list[dict]:
    if board not in boards_for(user):
        raise PermissionError(f"{user} has no access to {board}")
    con = _connect(board)
    rows = con.execute("""
        SELECT id, filename, stored_path, content_type,
               size AS size_bytes, uploaded_by, created_at
        FROM task_attachments WHERE task_id = ? ORDER BY id
    """, (task_id,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


# ------------------------------------------------------- amber signature

def init_approvals() -> None:
    con = sqlite3.connect(APPROVALS_DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS approvals (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            board         TEXT NOT NULL,
            task_id       TEXT NOT NULL,
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

    artifact_hash pins the signature to the exact bytes reviewed, so a
    deliverable cannot be swapped after sign-off without detection.
    """
    if signer not in AMBER_SIGNERS.get(board, []):
        raise PermissionError(f"{signer} is not a qualified signer for {board}")

    digest = hashlib.sha256(Path(artifact_path).read_bytes()).hexdigest()
    now = int(time.time())

    con = sqlite3.connect(APPROVALS_DB)
    con.execute("""
        INSERT INTO approvals
            (board, task_id, signer, signer_role, decision,
             note, artifact_hash, signed_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (board, task_id, signer, signer_role, decision,
          note, digest, now))
    con.commit()
    con.close()
    return {"task_id": task_id, "signer": signer, "decision": decision,
            "artifact_hash": digest, "signed_at": now}


def unsigned_amber(user: str) -> list[dict]:
    """The review queue. Playbook metric: this must never age past 10 days."""
    con = sqlite3.connect(APPROVALS_DB)
    signed = {r[0] for r in con.execute("SELECT task_id FROM approvals")}
    con.close()

    out = []
    for board in boards_for(user):
        for t in tasks_for(user, board):
            if t["status"] == "done" and t["id"] not in signed:
                age_days = (time.time() - (t["completed_at"] or 0)) / 86400
                out.append({**t, "board": board, "age_days": round(age_days, 1)})
    return sorted(out, key=lambda r: -r["age_days"])


# --------------------------------------------------------------- write

def create_task(user: str, board: str, title: str, body: str,
                assignee: str | None = None, priority: int = 3) -> str:
    """Trigger an agent run. Goes through the CLI, not raw SQL."""
    if board not in boards_for(user):
        raise PermissionError(f"{user} has no access to {board}")
    cmd = ["hermes", "kanban", "--board", board, "create", title,
           "--body", body, "--priority", str(priority), "--json"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    import json
    task = json.loads(out.stdout)
    if assignee:
        subprocess.run(["hermes", "kanban", "--board", board,
                        "assign", task["id"], assignee], check=True)
    return task["id"]
