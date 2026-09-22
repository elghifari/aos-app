# AOS — Talenta Agentic Operating System

The human-facing layer for Talenta's AI agent roster. Hermes owns the agent
runtime; this app owns **who may request and see work**, **what needs human
review**, and **the recorded artifact-bound signature**.

Full architecture: the `aos` Hermes skill, `references/architecture.md`.
Governance (Red Zone, roster, briefs, rhythm): same skill, other references.

## What this is

| Layer | Owns |
| :--- | :--- |
| Hermes | profiles, gateway, kanban dispatcher, cron, skills |
| Board DBs (`~/.hermes/kanban/boards/<pod>/kanban.db`) | data plane |
| **This app** | employee task UI, pod authorization, review gates, approvals |

Board data is read directly from SQLite. Task creation, assignment, linking,
unblocking, and dispatch go through `hermes kanban` so Hermes retains those
invariants. Dismissing finished work is the narrow exception: AOS changes only
`tasks.status` to `archived` in the WAL-backed board DB, avoiding about two
seconds of CLI startup for one field update.

## Authorization

Board-per-pod is the boundary — each pod's board is a physically separate SQLite
DB. Authz is a lookup, checked before any query touches disk:

```python
if board not in boards_for(user):
    raise PermissionError
```

Six pods: `p1-growth`, `p2-access`, `p3-people`, `p4-quality`, `p5-research`,
`p6-education`.

## The approvals table

Kanban `status: done` means *the worker finished* — not that anyone signed.
`approvals` records who signed, when, and **`artifact_hash`** (sha256 of the
exact bytes reviewed), so a deliverable swapped after sign-off is detectable.

Playbook metric: **Amber outputs shipped without sign-off must be zero.**
`unsigned_amber()` implements the review queue with age.

## Layout

```
aos.py            authz, task lifecycle, gates, approval and integrity state
web.py            FastAPI routes and development identity handling
registry.py       agent registry + ownership
seed_registry.py  seeds 25 roles from the playbook roster
templates/        employee, reviewer, agent, and pipeline views
tests/            isolated stdlib unittest suite; temporary DBs only
approvals.db      signature store (gitignored — audit data)
registry.db       agent/owner store (gitignored — regenerate via seed)
demo.sh           prepares a clean local demo without replacing the UI
rehearse.sh        marks and resets rehearsal-created board state
```

## The agent registry

`tasks` is Hermes-owned and `hermes update` migrates it, so AOS adds no columns
there. Tasks link to an agent through Hermes's native **`tenant`** field
(`agent-10`); everything else lives in `registry.db`.

Two facts the kanban schema cannot express:

**A human owns an agent.** `tasks.assignee` is a *profile*, not a person.
Ownership is many-to-many — the Clinical Director countersigns 11 agents across
4 pods. `boards_for()` is *derived* from agent ownership, so there is no
separate access map to drift out of sync with the roster.

**13 of 25 roles have no Hermes worker.** 6 are deterministic n8n pipelines,
7 are human seat work. They still need tasks, deliverables, and signatures.

| Delivery box | Count | Worker? |
| :--- | ---: | :--- |
| `n8n+agent` | 5 | yes |
| `agent` | 7 | yes |
| `n8n` | 6 | no — deterministic pipeline |
| `seat` | 7 | no — human |

25 rather than 20 because composites split: 03a/03b, 07a/07b/07c, 11a/11b/11c.

Consequences enforced in code:
- `create_task()` assigns a profile **only** for agentic roles, then dispatches
  immediately. Non-agentic tasks are deliberately left unassigned.
- `register()` refuses to attach a profile to a non-agentic role — 07a's
  deterministic gate cannot accidentally be given a model.
- `complete_by_human()` refuses to close a task belonging to an agentic role.
- Agent 03 is split in code: 03b cannot start until a qualified signer approves
  a current 03a artifact. The approved claim set and its SHA-256 provenance are
  injected into 03b; the drafter profile has no web access.
- 03a standing evidence rules are prepended to every task, so employees can use
  short briefs without having to repeat citation and KURI controls.
- Evidence-tool failures are correlated against the run window. A degraded run
  is held for human review rather than trusted because the worker reported
  success; a qualified signature clears the warning for those exact bytes.

Seeded owners are **placeholders** (`u_hr`, `u_clinical_director`). Real
identities come from HR; nothing in the registry is real until then.

## First-time initialization

```bash
python -c "import aos; aos.init_approvals()"
python seed_registry.py
```

Requires a Hermes install with boards under `$LOCALAPPDATA/hermes/kanban/boards/`
(Windows) — paths are resolved in `aos.py`.

## Running

```bash
./run.sh     # detached; survives the shell that launched it
./stop.sh
```

The development UI is available at `http://127.0.0.1:8077`. Identity is still a
local-only `?as=<user>` parameter; do not expose this server to other machines.

## Testing

```bash
python -m unittest discover -s tests
```

The suite uses temporary registries, board DBs, approval DBs, filesystems, and
profile logs. It neither reads nor writes live approvals and never calls an LLM.

## Documentation

| File | For |
| :--- | :--- |
| `HANDOVER.md` | next engineering session — verified state, current work, known gaps |
| `ARCHITECTURE.md` | current implementation, boundaries, data flow, known defects |
| `DECISIONS.md` | record of guardrail/zone/signer changes |

## Status

**Working:** 13 application routes covering employee work, queue health, task
creation, agent and composite views, task progress, review-only file preview,
artifact-bound approve/reject, gated download, unblock, and non-destructive
archive. The home page separates running, waiting, and finished work; finished
items are capped and can be cleared without destroying their audit history.

Enforcement includes cross-pod authorization, qualified per-agent signers,
current-byte approval hashes, tamper detection, rejection state, unsigned Amber
release refusal, 03a→03b gate provenance, degraded evidence-run holds,
non-agentic role isolation, immediate dispatch, and safe redirect handling.

**Not built:** real authentication and sessions · seat-work upload · deployment ·
real owner identities · employee clarification/revision loop · capability
proposal/IT approval interface.

## Rules

- **Never commit `*.db`.** `approvals.db` is audit data.
- **Never commit generated deliverables.** They may contain organisational data.
- **No patient-identifiable data anywhere in this repo.** Red Zone item 4.
- Authz and release gates are enforced in code, never by prompting a model.
