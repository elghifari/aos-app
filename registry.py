"""
AOS agent registry + ownership.

Why this exists as a SEPARATE store rather than columns on Hermes's `tasks`
table: `tasks` is Hermes-owned and `hermes update` runs migrations against it.
Anything we add there is liable to be clobbered. Tasks are linked to an agent
via Hermes's native `tenant` field (CLI-settable, survives updates); everything
AOS knows about an agent lives here.

Two facts this encodes that the kanban schema cannot:
  1. A human owns an agent. `tasks.assignee` is a PROFILE (pod-p3-people),
     not a person, and several people may own agents in one pod.
  2. Seven of twenty roles have NO agent behind them. They are human seat
     work that still needs tasks, deliverables, and signatures.
"""
import sqlite3
from pathlib import Path

REGISTRY_DB = Path(__file__).parent / "registry.db"

# Delivery box, from the two-axis test. Determines whether a task can be
# dispatched to a Hermes worker at all.
AGENTIC = ("n8n+agent", "agent")          # a worker runs it
NON_AGENTIC = ("n8n", "seat")             # no model in the loop, or a human


def init_registry() -> None:
    con = sqlite3.connect(REGISTRY_DB)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            agent_no      TEXT PRIMARY KEY,      -- '10', '03a', '07c'
            name          TEXT NOT NULL,
            board         TEXT NOT NULL,         -- p3-people
            zone          TEXT NOT NULL CHECK (zone IN ('green','amber','red')),
            delivery_box  TEXT NOT NULL,         -- n8n+agent | agent | n8n | seat
            is_agentic    INTEGER NOT NULL,      -- 0 = no Hermes worker exists
            profile       TEXT,                  -- NULL when not agentic
            cadence       TEXT,
            guardrail     TEXT NOT NULL,
            brief_version TEXT,
            active        INTEGER NOT NULL DEFAULT 1
        );

        -- Many-to-many: one person may own several agents; an agent may have
        -- a primary owner plus a clinical countersigner.
        CREATE TABLE IF NOT EXISTS agent_owners (
            agent_no  TEXT NOT NULL,
            user_id   TEXT NOT NULL,
            role      TEXT NOT NULL,   -- 'owner' | 'countersigner' | 'consumer'
            PRIMARY KEY (agent_no, user_id, role),
            FOREIGN KEY (agent_no) REFERENCES agents(agent_no)
        );
    """)
    con.commit()
    con.close()


def tenant_for(agent_no: str) -> str:
    """The value written to a task's `tenant` field to link it to an agent."""
    return f"agent-{agent_no}"


def agent_of_task(task: dict) -> str | None:
    """Reverse: which agent does this task belong to?"""
    t = task.get("tenant") or ""
    return t[6:] if t.startswith("agent-") else None


def agents_for_user(user_id: str) -> list[dict]:
    """Every agent this person owns, across pods. Ownership is per-agent,
    not per-pod — one person may own agents in several pods."""
    con = sqlite3.connect(REGISTRY_DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT a.*, o.role AS ownership
        FROM agents a
        JOIN agent_owners o ON o.agent_no = a.agent_no
        WHERE o.user_id = ? AND a.active = 1
        ORDER BY a.board, a.agent_no
    """, (user_id,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def boards_for(user_id: str) -> list[str]:
    """Derived from agent ownership, not configured separately — a person can
    see exactly the pods where they own at least one agent."""
    return sorted({a["board"] for a in agents_for_user(user_id)
                   if a["ownership"] in ("owner", "countersigner")})


def owners_of(agent_no: str, role: str = "owner") -> list[str]:
    con = sqlite3.connect(REGISTRY_DB)
    rows = con.execute(
        "SELECT user_id FROM agent_owners WHERE agent_no = ? AND role = ?",
        (agent_no, role)).fetchall()
    con.close()
    return [r[0] for r in rows]


def get_agent(agent_no: str) -> dict | None:
    """Full registry row for one agent, or None if unknown."""
    con = sqlite3.connect(REGISTRY_DB)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT * FROM agents WHERE agent_no = ?", (agent_no,)).fetchone()
    con.close()
    return dict(row) if row else None


def is_dispatchable(agent_no: str) -> bool:
    """False for seat-work and n8n-only roles. A task for one of these is
    completed by a human or an external pipeline — never by a Hermes worker,
    and it must NOT be assigned to a profile."""
    con = sqlite3.connect(REGISTRY_DB)
    row = con.execute(
        "SELECT is_agentic FROM agents WHERE agent_no = ?", (agent_no,)).fetchone()
    con.close()
    return bool(row and row[0])


def register(agent_no, name, board, zone, delivery_box, guardrail,
             profile=None, cadence=None, owners=()) -> None:
    agentic = 1 if delivery_box in AGENTIC else 0
    if not agentic and profile:
        raise ValueError(
            f"agent {agent_no} is {delivery_box} (non-agentic) — it must not "
            f"have a profile; its tasks are completed by a human or n8n")
    con = sqlite3.connect(REGISTRY_DB)
    con.execute("""
        INSERT OR REPLACE INTO agents
          (agent_no, name, board, zone, delivery_box, is_agentic,
           profile, cadence, guardrail, active)
        VALUES (?,?,?,?,?,?,?,?,?,1)
    """, (agent_no, name, board, zone, delivery_box, agentic,
          profile, cadence, guardrail))
    for user_id, role in owners:
        con.execute("INSERT OR REPLACE INTO agent_owners VALUES (?,?,?)",
                    (agent_no, user_id, role))
    con.commit()
    con.close()


# Who may do what with an agent.
#   owner         — accountable; creates work, retries it, completes seat work
#   countersigner — signs Amber output before it is releasable
#   consumer      — reads SIGNED deliverables only. Never owns, never signs,
#                   never sees the pod queue. This is the content writer who
#                   collects a cleared evidence table and drafts elsewhere.
ROLES = ("owner", "countersigner", "consumer")


def consumers_of(agent_no: str) -> list[str]:
    return owners_of(agent_no, "consumer")


def agents_readable_by(user_id: str) -> list[dict]:
    """Agents whose signed output this person may collect. Distinct from
    agents_for_user(), which is about accountability."""
    con = sqlite3.connect(REGISTRY_DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT a.*, o.role AS ownership
        FROM agents a JOIN agent_owners o ON o.agent_no = a.agent_no
        WHERE o.user_id = ? AND a.active = 1
        ORDER BY a.board, a.agent_no
    """, (user_id,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def agents_on_board(board: str) -> list[dict]:
    con = sqlite3.connect(REGISTRY_DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM agents WHERE board = ? ORDER BY agent_no", (board,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


# Composite agents. The playbook numbers them as ONE role and decomposes them
# into stages; showing the stages as unrelated agents hides the thing that
# matters most — the human gate between them, which IS the control.
#
# gate_after: the stage number after which a human must act before the next
# stage may begin. None means the stages are independent, not sequential.
FAMILIES = {
    "03": {
        "name": "Clinical Content",
        "sequential": True,
        "gate_after": "03a",
        "gate": ("A clinician marks which claims are supportable. That becomes "
                 "the APPROVED CLAIM SET, and it is the only thing the drafter "
                 "may use."),
        "why": ("The agent must not research and write in one pass: claims "
                "generated alongside their own sources invite post-hoc "
                "justification, and a finished draft with citations attached is "
                "the hardest artifact for a reviewer to catch errors in."),
    },
    "07": {
        "name": "Enquiry Triage",
        "sequential": True,
        "gate_after": "07a",
        "gate": ("The risk-language gate runs BEFORE any model sees the message. "
                 "If it trips, the conversation leaves automation permanently "
                 "and a human takes it."),
        "why": ("A false positive costs a Care Navigator two minutes. A false "
                "negative is Red Zone item 3. The gate is tuned for recall, "
                "fails closed, and is irreversible per conversation."),
    },
    "11": {
        "name": "Recruitment",
        "sequential": True,
        "gate_after": "11a",
        "gate": ("Criteria are PUBLISHED before any candidate exists. Nothing "
                 "downstream may introduce a criterion that was not published."),
        "why": ("Extraction and flagging never rank, never remove a row, and "
                "never infer to fill a blank. The hiring decision stays human, "
                "and candidate data is personal data under the PDP Law."),
    },
}


def family_of(agent_no: str) -> str | None:
    """'03a' -> '03'. Returns None for standalone agents."""
    base = agent_no.rstrip("abcdefg")
    return base if base in FAMILIES and base != agent_no else None


def get_family(family_no: str) -> dict | None:
    meta = FAMILIES.get(family_no)
    if meta is None:
        return None
    con = sqlite3.connect(REGISTRY_DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM agents WHERE agent_no LIKE ? AND active = 1 "
        "ORDER BY agent_no", (family_no + "%",)).fetchall()
    con.close()
    stages = [dict(r) for r in rows]
    if not stages:
        return None
    return {**meta, "family_no": family_no, "stages": stages,
            "board": stages[0]["board"]}


def group_by_family(agents: list[dict]) -> list[dict]:
    """Collapse a flat agent list into families plus standalone agents,
    preserving order. Each family entry carries its stages."""
    out, seen = [], set()
    for a in agents:
        fam = family_of(a["agent_no"])
        if fam is None:
            out.append({"kind": "agent", "agent": a})
        elif fam not in seen:
            seen.add(fam)
            stages = [x for x in agents if family_of(x["agent_no"]) == fam]
            out.append({"kind": "family", "family_no": fam,
                        "meta": FAMILIES[fam], "stages": stages,
                        "board": stages[0]["board"]})
    return out
