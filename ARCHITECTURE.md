# AOS — Architecture Reference

Current implementation reference for the Talenta Agentic Operating System.

Last verified: **2026-09-22** against the working tree at HEAD `2cb81a3`,
including the uncommitted iteration described in `HANDOVER.md`.

Use this document for system boundaries, data flow, invariants, and known
implementation defects. Use `HANDOVER.md` for current task state and where the
next session should begin. Governance authority remains the Hermes skill named
`aos`, especially `references/red-zone.md` and `references/constraints.md`.

---

## 0. Orientation

AOS is the employee-facing governance and workflow layer over Hermes Agent.
Hermes owns model execution, profiles, tools, kanban dispatch, workspaces, and
run history. AOS owns:

- which employee may commission which registered role;
- which pod data that employee may see;
- plain-language task status and employee work lists;
- which output requires qualified review;
- the exact artifact bytes a person approved or rejected;
- whether a deliverable may be released;
- the human gate and provenance between Agent 03a and 03b.

AOS is not an agent framework, scheduler, clinical system, or patient record.
It does not hold patient-identifiable data and must never be connected to a
clinical record system in a way that exposes such data to a general-purpose AI.

The organisation is Yayasan Bina Talenta Tunas Bangsa Karya Mandiri
("Talenta"), Bekasi, Indonesia. Total headcount is 238, but the likely AOS user
base is about 20 management staff, with roughly half using the app directly.
Design and licence decisions must be sized for that reality.

### Document map

| Document | Authority |
| :--- | :--- |
| Hermes `aos` skill | Governance, Red Zone, roster intent, operating model |
| `ARCHITECTURE.md` | Current implementation and system boundaries |
| `HANDOVER.md` | Current working-tree state, trial tasks, gaps, next session |
| `README.md` | Short setup and operating overview |
| `DECISIONS.md` | Attributed changes to guardrails, zones, signers, constraints |

---

## 1. Governance boundaries

### 1.1 Red Zone

AI is never used for:

- diagnosis, differential diagnosis, treatment selection, medication, admission,
  discharge, acuity, or risk assessment;
- interpretation of qEEG, EEG, PSG, TOVA, MMPI, MACI, M-PACI, MCMI, or other
  clinical/psychometric results;
- crisis conversations with patients or families;
- patient complaint or adverse-event investigation;
- final approval of clinical or technology claims;
- hiring, promotion, disciplinary, or termination decisions;
- processing patient-identifiable data in a general-purpose AI tool.

If a regulator asks who decided, the answer for any clinical judgement must be a
named licensed human. A task, document, prompt, or user request cannot waive this.

### 1.2 Zoning

| Zone | Release rule |
| :--- | :--- |
| Green | AI may draft; pod owner reviews for ordinary quality and ships |
| Amber | A named qualified human signs the exact current artifact before release |
| Red | AI is not used, including for a first pass or summary |

The target for Amber outputs released without sign-off is zero.

### 1.3 Standing constraints

1. **Agent 03:** evidence gathering and drafting are separate runs with a human
   approval gate between them.
2. **Agent 07:** the risk-language gate is deterministic, fail-closed,
   recall-tuned, irreversible per conversation, and runs before any model.
3. **Agent 11:** extract declared facts and flag published binary criteria only;
   never rank, score, remove, or infer a candidate into a decision.
4. **General:** safety-critical gates are deterministic and separately owned;
   agentic improvement work operates on logs rather than live high-risk cases.

Only Agent 03's inter-stage gate is implemented in AOS today. The Agent 07 and
11 deterministic pipelines are registry designs awaiting n8n implementation.

### 1.4 KURI claim ceiling

Applied during evidence gathering, before drafting:

- TMS only for selected indications;
- qEEG is not diagnostic on its own;
- neurofeedback evidence is mixed.

---

## 2. Runtime topology

```text
Employee browser
      │
      ▼
FastAPI + Jinja AOS app (localhost:8077)
      │
      ├── registry.db             AOS role/owner metadata
      ├── approvals.db            AOS append-only decisions
      └── Hermes board DBs        tasks, runs, attachments, links
                │
                ▼
        Hermes kanban dispatcher
                │
                ▼
       isolated Hermes profiles
```

### 2.1 Six pod boards

Each pod has a separate SQLite board DB under the active Hermes home:

```text
$HERMES_HOME/kanban/boards/<board>/kanban.db
```

Boards:

- `p1-growth`
- `p2-access`
- `p3-people`
- `p4-quality`
- `p5-research`
- `p6-education`

Board separation is the primary data boundary. Profile separation provides
separate configuration, sessions, skills, and memory. It is not an operating
system sandbox: profiles run as the same Windows user. Capability minimisation
therefore matters. A profile without terminal, web, memory, or session search
cannot use those routes through Hermes, but the host process itself is not a
separate security principal.

### 2.2 Technology stack

Verified versions on the development workstation:

| Layer | Version |
| :--- | :--- |
| Python | 3.11.16 |
| FastAPI | 0.133.1 |
| Starlette | 1.3.1 |
| uvicorn | 0.41.0 |
| Jinja2 | 3.1.6 |
| SQLite | 3.53.1 |
| python-multipart | 0.0.32 |

There is no JavaScript build, SPA, ORM, or CSS framework. Forms POST and redirect;
server-rendered templates own all UI state. `python-multipart` is required by
FastAPI `Form` routes, although the repository does not yet have a dependency
manifest. That missing manifest is a deployment gap.

Current source size is approximately:

- `aos.py`: 1,259 lines
- `web.py`: 371 lines
- `registry.py`: 261 lines
- templates: 1,021 lines total

### 2.3 Read and write policy

AOS reads Hermes board DBs directly. Read-only connections are pooled per board
to avoid Windows/antivirus connection-open overhead. Each query runs outside a
long-lived transaction, so external dispatcher commits remain visible.

Hermes CLI owns complex mutations:

- create task;
- assign profile;
- link task provenance;
- unblock;
- dispatch.

One narrow write bypasses the CLI: dismissing finished work changes only
`tasks.status` to `archived`. Boards use WAL and the write connection has a
five-second timeout. This reduced a roughly two-second CLI startup cost to a
roughly 20–30 ms request. Do not generalise this exception to task creation,
assignment, or run state without proving Hermes's invariants.

---

## 3. Data model

AOS depends on three SQLite stores plus attachment files and profile logs.

```text
Hermes board DBs                 tasks, runs, attachments, task links
registry.db                      role definitions and ownership
approvals.db                     approval/rejection history
board workspace files            artifact bytes being approved
profile logs/errors.log           independent evidence-tool failure signal
```

### 3.1 Task is not run

An **agent** is a standing role. A **task** is one commissioned unit of work. A
**run** is one execution attempt. One task can have several runs and several
attachments.

Tasks link to roles through Hermes's native `tenant` field:

```text
agent-03a
agent-12
```

`tasks.assignee` is a Hermes profile such as `pod-p1-growth`, never a human.
Human responsibility lives in `registry.db`.

### 3.2 Registry schema

```sql
agents(
    agent_no PRIMARY KEY,
    name,
    board,
    zone,
    delivery_box,
    is_agentic,
    profile,
    guardrail,
    cadence,
    brief_version,
    active
)

agent_owners(
    agent_no,
    user_id,
    role              -- owner | countersigner | consumer
)
```

Board access is derived from ownership rather than maintained as a second access
map. Owners and countersigners receive pod visibility. Consumers are a narrower
exception described in §4.2.

### 3.3 Approval schema

```sql
approvals(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    board TEXT NOT NULL,
    task_id TEXT NOT NULL,
    agent_no TEXT,
    signer TEXT NOT NULL,
    signer_role TEXT NOT NULL,
    decision TEXT CHECK(decision IN ('approved','rejected')),
    note TEXT,
    artifact_hash TEXT NOT NULL,
    signed_at INTEGER NOT NULL
)
```

There is no `artifact_path` column and no one-approval-per-task constraint.
Decisions form an append-only history. Current attachment identity is encoded in
`artifact_hash`:

```text
attachment:<attachment_id>:sha256:<digest>
```

The latest matching decision for that attachment and those exact bytes controls
release. A later approval may supersede a rejection. If the file bytes change,
the new bytes are pending and require a new review.

Legacy rows containing only a bare digest remain accepted when exactly one
attachment on that task has those bytes. If multiple attachments match, the
legacy decision is ambiguous and release fails closed.

---

## 4. Identity and authorization

### 4.1 Development identity

Authentication is not implemented. `current_user()` accepts `?as=<user>` or the
POSTed `user` field in development. Outside `AOS_ENV=development`, each request
fails with HTTP 500. The process itself can still start; it does not fail at
startup.

This server must remain local until real authentication exists. A query
parameter is not a defensible signing identity.

### 4.2 Board authorization

`boards_for(user)` is derived from registry ownership. A person sees boards
where they own or countersign at least one agent. Signers can review but
`creatable_agents()` excludes them unless they are also an owner, preserving the
separation between commissioning and approval.

A consumer does not receive general board access. A consumer assigned to a
specific agent may retrieve only that agent's already-released attachment.

The intended invariant is authorization before task or artifact data is read.
The task-detail route enforces this. Three lower-level helpers currently do not:

- `sign()` reads the task before `_authorize()`;
- `can_review()` reads the task without board authorization;
- `attachment()` reads the task before its consumer/reviewer authorization path.

These paths still apply signer/consumer checks before release, but they violate
the documented authorize-before-read rule and may expose task existence through
error behavior. Treat this as a current defect, not intended architecture.

### 4.3 Redirect safety

Navigation origin is carried through a `back` parameter. `_BACK_OK` accepts only
known same-origin route shapes. Raw `Referer` values are never used directly, so
POST redirects cannot become open redirects.

---

## 5. Task lifecycle and employee UX

### 5.1 Creation

`create_task()` performs, in order:

1. board authorization;
2. agent existence, board, active-state, and owner checks;
3. refusal of Amber work with no named countersigner;
4. Agent 03 upstream-gate check where applicable;
5. standing-rule injection where configured;
6. Hermes task creation with the agent tenant;
7. provenance links for gated downstream work;
8. assignment only when the role is agentic;
9. immediate best-effort dispatch.

If immediate dispatch fails, the task remains created and assigned so the normal
roughly 60-second gateway tick can pick it up. Non-agentic roles are left
unassigned so no worker can claim them.

### 5.2 Standing prompts

Agent-specific standing rules live in `STANDING_RULES`, keyed by agent number.
They are prepended inside `create_task()` and cannot be omitted by a busy
requester. Agents without an entry receive the user's brief unchanged.

The registry `guardrail` remains queryable metadata. For 03a it is also included
with the standing instructions sent to the worker.

### 5.3 Plain-language status

The authoritative Hermes statuses are mapped as follows:

| Board status | Employee label |
| :--- | :--- |
| `triage`, `todo`, `scheduled`, `ready` | Not started |
| `running` | Working on it now |
| `review`, `done` | Finished |
| `blocked` | Stopped |
| `archived` | Archived |

Unknown status names are shown honestly with the raw board value. Do not invent
aliases such as `in_progress`; Hermes uses `running`.

### 5.4 Home and dismissal

`my_work()` groups an owner's tasks across pods into running, waiting, and
finished. Running and waiting lists are uncapped. The home page shows the eight
most recent finished items.

**Done** calls `dismiss()` and archives rather than deletes. It refuses when:

- the task is unfinished;
- the user does not own the role;
- the output is still awaiting required review.

Task, run, attachment, and approval history remain available after archive.

### 5.5 Blocked work

Blocked tasks do not restart themselves. The UI shows them separately with their
last failure, and authorized owners can invoke Hermes unblock/retry. Shared model
quota exhaustion is a known operational cause of silent worker failure.

---

## 6. Artifact review and release

### 6.1 File states

Each substantive current attachment resolves to one state:

- `pending`
- `approved`
- `rejected`

Task-level release uses the weakest current substantive attachment state,
reporting rejection before pending. Every substantive current attachment must be
approved for an Amber task to release.

Bare placeholders—empty files, `null`, `{}`, and `[]`—are not substantive and
do not hold a real document hostage. This check is content-specific; a broad
minimum-size threshold would incorrectly discard short legitimate documents.

### 6.2 Review versus release

The qualified signer reads pending or rejected bytes through an explicit review
path:

```text
/file/{board}/{task_id}/{att_id}/review-raw
```

This is separate from ordinary release. A marketer cannot download an unsigned
Amber artifact. The signer can read it only to decide, sees the SHA-256, and
posts Approve or Reject from the artifact preview page.

Ordinary preview and download use `attachment()` without review mode and remain
closed until current bytes are approved. An unsigned owner receives the
`Under review` page rather than raw JSON.

### 6.3 Exact-byte binding

The review form carries the hash shown during preview. `sign()` recomputes the
file hash and refuses if it changed between preview and decision. It also
verifies that the path is an attachment of that task and stays beneath that
board's root.

This prevents:

- approving a file the reviewer never opened;
- swapping bytes after preview;
- one approval releasing a sibling attachment with identical bytes;
- replacing approved bytes without returning to pending.

### 6.4 Evidence-tool integrity hold

`run_integrity()` reads the latest run window and correlates it with the assigned
profile's `logs/errors.log`. Failures from `web_search`, `web_extract`, or
`web_fetch` mark the run degraded independently of the worker's summary.

A degraded run is held for human review even if the model reports success. Once
a qualified signer approves the exact artifact, the warning clears; the hold
exists to require independent review, not to veto it.

Current limitations:

- only failures are recorded; successful source opens are not proven;
- one failed call marks a partially successful run degraded;
- log timestamp parsing is an operational heuristic, not structured telemetry;
- a degraded **Green** task can be held even though Green roles normally have no
  countersigner, creating an uncleared state. This needs a named escalation path
  or a narrower policy before degraded Green runs occur in production.

The UI must describe this as incomplete source access, not proof that every
source was unreachable.

### 6.5 Current signing metadata defect

The web signing route currently passes the agent zone (`"amber"`) as
`signer_role`. The authorization decision still comes from registry
`countersigner` ownership, but the stored role label is semantically wrong. A
future migration should record `countersigner` or, preferably, the signer's
actual qualification at signing time.

---

## 7. Agent 03 implementation

### 7.1 03a — evidence table

03a is Amber and runs in `pod-p1-growth`. Every task receives standing rules that
require:

- research only, no marketing or patient-facing prose;
- citations only from sources opened during that run;
- DOI or PMID and a short supporting quotation per row;
- failed lookups under `COULD NOT VERIFY`;
- no reconstruction from model memory if sources cannot be reached;
- the KURI ceiling during evidence gathering.

These instructions improve model behavior. The independent integrity hold and
human signature remain the controls.

### 7.2 Human gate

`GATED_STAGES` maps `03b` to `03a`. `gate_state()` finds current approved 03a
artifacts. If none exist, `create_task()` raises `GateNotPassed`, including when
the caller bypasses the UI.

When the gate is open, `_claim_set_body()` prepends:

- the exact approved artifact text;
- upstream task and filename;
- signer;
- SHA-256 provenance;
- instructions not to add or strengthen claims.

Task links record upstream/downstream provenance as data.

### 7.3 03b — constrained drafting profile

03b is agentic in the live registry and runs in `p1-drafting`. Its enabled CLI
toolsets are:

- `clarify`
- `file`
- `kanban`
- `skills`
- `todo`

It has no web, browser, terminal, code execution, memory, session search,
delegation, or computer-use tool. It therefore cannot browse around the approved
claim set through Hermes capabilities.

### 7.4 Seed mismatch

The live registry reflects the approved decision in `DECISIONS.md`: 03b is an
agent using `p1-drafting`. `seed_registry.py` still defines 03b as `seat` with no
profile. Running the seed would regress the live role.

This is a reproducibility defect. Update the seed before rebuilding any registry.
Do not treat the current live DB as a substitute for a correct seed.

---

## 8. Agent registry snapshot

Live registry totals:

- 25 active rows representing 20 playbook roles;
- 14 Amber, 11 Green;
- 13 agentic, 12 non-agentic;
- delivery boxes: 5 `n8n+agent`, 8 `agent`, 6 `n8n`, 6 `seat`.

| # | Role | Board | Zone | Delivery | Agentic | Profile | Countersigner |
| :-- | :-- | :-- | :-- | :-- | :--: | :-- | :-- |
| 01 | SEO Technical Auditor | p1-growth | green | n8n+agent | yes | pod-p1-growth | — |
| 02 | Keyword & Content Strategist | p1-growth | green | agent | yes | pod-p1-growth | — |
| 03a | Clinical Evidence Table | p1-growth | amber | agent | yes | pod-p1-growth | u_clinical_director |
| 03b | Clinical Content Drafter | p1-growth | amber | agent | yes | p1-drafting | u_clinical_director |
| 04 | GA4 & Funnel Analyst | p1-growth | green | n8n | no | — | — |
| 05 | Local SEO & Reputation | p1-growth | amber | n8n+agent | yes | pod-p1-growth | u_clinical_director |
| 06 | Paid Media Operator | p1-growth | amber | seat | no | — | u_clinical_director |
| 07a | Risk-Language Gate | p2-access | amber | n8n | no | — | u_clinical_director |
| 07b | Enquiry Router | p2-access | green | n8n | no | — | — |
| 07c | Triage Script Curator | p2-access | amber | n8n+agent | yes | pod-p2-access | u_clinical_director |
| 08 | Booking & No-Show Analyst | p2-access | green | n8n | no | — | — |
| 09 | Referral Network Coordinator | p2-access | amber | agent | yes | pod-p2-access | u_clinical_director |
| 10 | Job Analysis & JD Writer | p3-people | green | agent | yes | pod-p3-people | — |
| 11a | Recruitment Kit Builder | p3-people | green | agent | yes | pod-p3-people | — |
| 11b | CV Extractor | p3-people | amber | n8n | no | — | — |
| 11c | Criteria Flagger | p3-people | amber | n8n | no | — | — |
| 12 | Onboarding & Documentation | p3-people | green | n8n+agent | yes | pod-p3-people | — |
| 13 | Workforce & L&D Architect | p3-people | green | seat | no | — | — |
| 14 | SOP & Pathway Documentation | p4-quality | amber | agent | yes | pod-p4-quality | u_clinical_director |
| 15 | Competency & OSCE Materials | p4-quality | amber | seat | no | — | u_clinical_director |
| 16 | Quality Indicator Reporting | p4-quality | amber | n8n+agent | yes | pod-p4-quality | u_clinical_director |
| 17 | Literature & Evidence | p5-research | green | agent | yes | pod-p5-research | — |
| 18 | Protocol & Analysis Assistant | p5-research | amber | seat | no | — | u_clinical_director |
| 19 | Curriculum & Materials | p6-education | amber | seat | no | — | — |
| 20 | Admissions & Parent Comms | p6-education | green | seat | no | — | — |

Amber roles 11b, 11c, and 19 have no countersigner and are refused at task
creation until one is assigned.

Composite families:

```text
03  evidence → HUMAN GATE → constrained drafting
07  deterministic risk gate → administrative router → log-based curator
11  pre-candidate kit → fixed extraction → published-criteria flags
```

Zones may differ within a family. Never collapse a family to one badge.

---

## 9. Web layer

`web.py` currently exposes 13 application routes:

| Method | Route | Purpose |
| :-- | :-- | :-- |
| GET | `/` | Employee work, signature queue, oversight, blocked tasks, agent list |
| GET | `/queue` | Queue age, signer/agent breakdown, estimated signing load |
| GET | `/new` | Scoped task form and gate state |
| POST | `/new` | Validate, create, assign, and dispatch |
| GET | `/task/{board}/{task_id}` | Task status, files, runs, review state |
| GET | `/agent/{agent_no}` | Agent metadata, guardrail, tasks, current work |
| GET | `/family/{family_no}` | Composite stages and human gates |
| GET | `/file/{board}/{task_id}/{att_id}` | File preview or Under review page |
| GET | `/file/{board}/{task_id}/{att_id}/review-raw` | Qualified signer's pending-byte read |
| GET | `/file/{board}/{task_id}/{att_id}/raw` | Released download |
| POST | `/sign/{board}/{task_id}` | Approve or reject exact reviewed bytes |
| POST | `/dismiss/{board}/{task_id}` | Non-destructive archive |
| POST | `/unblock/{board}/{task_id}` | Retry blocked work |

Approve/Reject lives on the artifact preview, not the task summary. This keeps
the decision adjacent to the bytes and checksum being signed.

The app has no client-side state. Navigation preserves a validated `back` path
through forms and redirects.

---

## 10. Queue health and review capacity

`unsigned_amber()` produces the review queue and age. `queue_health()` groups it
by signer and agent. `signing_load()` exposes expected weekly load from cadence
metadata.

`REVIEW_SLA_DAYS` is currently 10. Despite comments referring to ten **working**
days, implementation compares elapsed calendar days. Either rename the metric or
implement a working-day calculation before presenting it as an SLA.

Operational assumptions:

- only 3–4 people may be qualified to sign clinical work;
- qualifications are not interchangeable;
- a queue aging for two weeks at low volume usually means poor routing or
  visibility rather than excessive standards;
- if review capacity is exceeded, throttle agents rather than release unsigned
  work.

---

## 11. Testing

The suite uses stdlib `unittest`:

```bash
python -m unittest discover -s tests
```

Last verified result: **46 tests passing**.

Tests use temporary:

- board SQLite DBs;
- registry DB;
- approvals DB;
- artifact filesystem;
- profile error logs.

No test calls or emulates an LLM. Tests cover authorization, approval binding,
tamper detection, rejection state, per-attachment release, reviewer preview,
Agent 03 gate enforcement, standing-rule injection, integrity holds, immediate
dispatch, plain-language statuses, archive behavior, redirect safety, and the
main HTTP paths.

The test suite does not replace a live model-output review. It proves structural
controls, not citation accuracy or writing quality.

---

## 12. Operational behavior

### 12.1 Server lifecycle

```bash
./run.sh
./stop.sh
```

`run.sh` starts uvicorn detached with a PID file so it survives the launching
Hermes session. Verify readiness with an HTTP request rather than process state.

### 12.2 Search reliability

Pod web search uses Hermes's provider chain and has been intermittent on the
keyless path. Trial runs recorded repeated search/Firecrawl failures; other
runs returned real results from the same pod profile.

A paid search key improves availability. It does not remove the need for source
provenance or the integrity hold because a model can still invent around partial
results.

### 12.3 Profile/session isolation

The desktop chat, `pod-p1-growth`, `pod-p3-people`, and other profiles have
separate sessions and memories. An AOS worker cannot see this conversation unless
AOS places the relevant context in the task body. The `p1-drafting` profile also
lacks memory and session-search tools.

---

## 13. Not built

| Gap | Consequence |
| :--- | :--- |
| Real authentication and sessions | `?as=` is development-only; signatures are not deployable identities |
| Real owner and qualification records | Placeholder IDs cannot support a real pilot or defensible signatures |
| Seat-work upload/completion UI | Six seat roles cannot record work through the web app |
| n8n pipelines | Deterministic and event-driven roles, including 07 and 11, are designs only |
| Clarification/revision loop | Employees cannot answer an agent or request a versioned revision in one task |
| Capability proposal workflow | Employee suggestion → IT review/configuration is deferred |
| Deployment and dependency manifest | Local workstation only; reproducible install is incomplete |
| Successful-source telemetry | AOS sees evidence-tool errors but cannot prove which URLs were opened |
| Long agent-history filtering | Home is bounded; agent pages will grow over time |
| Telegram signing | Deferred; no route or identity binding exists |

---

## 14. Known defects and consistency risks

These are current facts, not intended design:

1. **`seed_registry.py` would regress 03b** from agentic `p1-drafting` to seat
   work. Fix before reseeding.
2. **Authorize-before-read is incomplete** in `sign()`, `can_review()`, and
   `attachment()`.
3. **Stored `signer_role` is wrong** for web approvals: the route records the
   zone (`amber`) rather than countersigner or qualification.
4. **Degraded Green work has no general clearance path** because Green agents
   normally have no countersigner.
5. **Integrity telemetry proves failures, not successful source access.** The UI
   must avoid saying every source was unreachable.
6. **Review SLA uses calendar days** while comments say working days.
7. **No dependency manifest** records FastAPI, uvicorn, Jinja2, and
   python-multipart.
8. **The web module comment says auth refuses startup**, but implementation
   refuses requests outside development after the app starts.

Fixing these should precede adding more agent roles.

---

## 15. Repository and development rules

- Never commit `*.db`; `approvals.db` is audit data.
- Never commit generated deliverables or uploads.
- Never place patient-identifiable data in this repository or any AI tool.
- Use temporary stores for tests; do not mutate live boards or approvals to
  verify code.
- Do not emulate LLM responses in tests.
- Preserve exact identifiers, attachment hashes, and signer identity.
- Record guardrail, zone, signer, or constraint changes in `DECISIONS.md`.
- Do not commit or push unless the user explicitly requests it.

When advising on AOS:

1. Load the `aos` skill first.
2. Prefer structural enforcement over model instruction.
3. Keep employee briefs short by placing universal rules in the role.
4. Keep ordinary Green workflows low-friction.
5. Make warnings precise enough that staff do not learn to ignore them.
6. Never weaken a release gate to solve queue capacity; improve routing,
   batching, telemetry, or reviewer assignment instead.
