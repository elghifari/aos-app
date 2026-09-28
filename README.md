# AOS

AOS is the internal web app Talenta staff use to hand work to AI agents and to
sign off on what comes back. Talenta runs a mental-health clinic, schools, and
a research institute, so a lot of that work sits close to patients, students,
or hiring. The app exists to keep that work reviewable.

A staff member picks an agent they own, writes a short brief, and gets a task
page that shows progress and the files the agent produced. For Green zone
agents, the owner reviews the output and ships it. For Amber agents, a named
qualified person has to approve the exact file before anyone can download it.
Some work is never given to AI at all: clinical decisions, reading clinical
results, crisis conversations, patient-identifiable data, and hiring
decisions. That list is the Red Zone, and nothing in this app is meant to
touch it.

## How it is built

The agents run on [Hermes](https://github.com/NousResearch/hermes-agent). Each
pod has a Hermes profile (its model, tools, and skills) and a kanban board (a
SQLite file of tasks, runs, and attachments). A Hermes dispatcher picks up
assigned tasks and starts a worker process for each one.

AOS sits beside Hermes and keeps track of what Hermes doesn't: which person
owns which agent, who can see which board, and who signed off on what.

```
browser ──> web.py (FastAPI + Jinja templates)
               │
               ├── aos.py ── reads board DBs directly, read-only
               │         └── writes through the `hermes kanban` CLI
               ├── registry.db   agents, pods, owners, signers
               └── approvals.db  signatures
```

Reads go straight to each board's SQLite file. Writes (create, assign, link,
dispatch) go through the Hermes CLI so Hermes keeps control of its own schema.
The one exception is dismissing a finished task, which sets `tasks.status` to
`archived` directly because the CLI call took about two seconds for a single
field.

Each pod has its own database file, and a user can only open boards for pods
where they own or sign for an agent. That check runs before any query touches
disk.

A signature in `approvals.db` records the signer, their role, the decision,
and the SHA-256 of the file they reviewed. If the file changes after signing,
the download is refused. Kanban's own `done` status only means the worker
finished, so AOS never treats it as approval.

Agent 03 has two extra controls in code. 03a produces an evidence table and
03b drafts from it, as separate tasks. A 03b task can only be created from a
03a task whose current file has been approved, and it receives only those
approved files. The drafting profile has no web access. Separately, if the
evidence search logged errors during a 03a run, the task is held for review
even when the worker reports success.

## Pods and agents

The roster comes from Section 18 of the clinic marketing playbook: 20 roles in
six pods, each pod with one accountable owner. Roles 03, 07, and 11 each mix a
safety gate with other work, so they are split into stages (03a/03b,
07a/07b/07c, 11a/11b/11c). That gives 25 rows in the registry.

Only 13 of those 25 have an AI worker. Six are fixed-step pipelines planned
for n8n (04, 07a, 07b, 08, 11b, 11c), and six are seat work that a person does
and records in the app (06, 13, 15, 18, 19, 20). The registry refuses to give
a Hermes profile to a non-agentic role, so the 07a risk-language gate can
never end up behind a model.

| Pod | Board | Agents with a worker | Pipeline or seat roles |
| :-- | :-- | :-- | :-- |
| P1 Growth | `p1-growth` | 01, 02, 03a, 03b, 05 | 04, 06 |
| P2 Patient Access | `p2-access` | 07c, 09 | 07a, 07b, 08 |
| P3 People | `p3-people` | 10, 11a, 12 | 11b, 11c, 13 |
| P4 Clinical Ops & Quality | `p4-quality` | 14, 16 | 15 |
| P5 Research (IIMH) | `p5-research` | 17 | 18 |
| P6 Education | `p6-education` | none | 19, 20 |

On the development machine all six boards and profiles exist, plus
`p1-drafting` for 03b. P1, P3, P4, and P5 have had real tasks: 02, 03a, 03b,
05, 06, 10, 11a, 12, 13, 14, and 17. P2 and P6 have none yet, and none of the
n8n pipelines are built.

Owners and signers in the registry are placeholders such as `u_marketing` and
`u_clinical_director` until HR supplies real identities.

## Running it locally

You need Windows, [uv](https://docs.astral.sh/uv/), and a working Hermes
install. `aos.py` looks for Hermes at `%LOCALAPPDATA%\hermes`, so on Linux or
macOS you would have to change that path first.

```bash
uv sync
```

That creates `.venv` with Python 3.11 and the versions pinned in `uv.lock`.
You don't need to activate it: `run.sh`, `stop.sh`, and the commands below go
through `uv run`, so they use the project environment whichever `python` is
first on your PATH.

Create a board and a profile in Hermes for each pod you want to try:

```bash
hermes kanban boards create p1-growth --name "P1 · Growth"
hermes profile create pod-p1-growth --description "P1 Growth pod"
```

Then create the two local databases:

```bash
uv run python -c "import aos; aos.init_approvals()"
uv run python seed_registry.py
```

Start and stop the server:

```bash
./run.sh
./stop.sh
```

`run.sh` detaches the server so it keeps running after the shell closes, and
writes the listener's PID to `.aos.pid`. Open
`http://127.0.0.1:8077/?as=u_marketing` to use the app as the P1 owner, or put
another registry user after `?as=`. That parameter is the only login, so keep
the server on localhost.

Agent tasks only run if the pod's profile has a working model and something is
dispatching: either the Hermes gateway, or
`hermes kanban --board <board> dispatch` by hand.

The tests use temporary databases and never call a model:

```bash
uv run python -m unittest discover -s tests
bash tests/test_run_script.sh
```

## Not built yet

Real login, uploads for seat work, a way for staff to answer an agent's
question or ask for a revision, the n8n pipelines, and deployment.
`.env.example` lists login and session settings that the code does not read
yet.

## Other docs

`ARCHITECTURE.md` goes deeper on boundaries, data flow, and known defects.
`DECISIONS.md` records changes to guardrails, zones, and signers. `PRODUCT.md`
and `DESIGN.md` hold the product constraints and visual tokens for the UI.

Don't commit `*.db` files or agent deliverables, and don't put
patient-identifiable data anywhere in this repo.
