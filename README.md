# AOS — Talenta Agentic Operating System

The human-facing layer for Talenta's AI agent roster. Hermes owns the agent
runtime; this app owns **who may see what** and **the recorded Amber
signature**.

Full architecture: the `aos` Hermes skill, `references/architecture.md`.
Governance (Red Zone, roster, briefs, rhythm): same skill, other references.

## What this is

| Layer | Owns |
| :--- | :--- |
| Hermes | profiles, gateway, kanban dispatcher, cron, skills |
| Board DBs (`~/.hermes/kanban/boards/<pod>/kanban.db`) | data plane |
| **This app** | users, sessions, authz, approvals |

Reads open board DBs **read-only**. Writes go through the `hermes kanban` CLI so
schema invariants stay Hermes's problem.

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
aos.py            authz + approvals core
approvals.db      signature store (gitignored — audit data)
artifacts/        deliverables (gitignored)
```

## Running

```bash
python -c "import aos; aos.init_approvals()"
```

Requires a Hermes install with boards under `$LOCALAPPDATA/hermes/kanban/boards/`
(Windows) — path is resolved in `aos.py`.

## Status

**Built and tested:** cross-pod read blocked · unqualified signer blocked ·
signature recorded · post-signature tamper detected · review queue returns.

**Not built:** HTTP layer, real auth, per-agent `owner` column, support for
non-agentic roles (03b, 06, 13, 15, 18, 19, 20 are human seat work and still
need tasks, deliverables, and signatures).

## Rules

- **Never commit `*.db`.** `approvals.db` is audit data.
- **Never commit `artifacts/`.** Deliverables may contain organisational data.
- **No patient-identifiable data anywhere in this repo.** Red Zone item 4.
- Authz is enforced in code, never by prompting a model.
