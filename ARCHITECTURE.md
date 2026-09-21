# AOS — Architecture Reference

Machine-oriented context document. Read this before advising on, modifying, or
extending the AOS codebase.

Human-oriented companion: `PROGRESS.md` (status, rationale, open decisions).
This file is authoritative on anything factual.

Generated 2026-09-17 against commit `913ad7c`.

---

## 0. Orientation

**What AOS is.** The human-facing governance layer for Talenta's AI agent
roster. Hermes (an agent runtime) owns execution. AOS owns *who may see what*
and *the recorded signature that permits release*.

**What AOS is not.** Not an agent framework, not a chat interface, not a
scheduler. It commissions work, shows results, and gates their release.

**Organisation.** Yayasan Bina Talenta Tunas Bangsa Karya Mandiri ("Talenta"),
Bekasi, Indonesia. Mental-health clinic (IIMH), special-needs schools, clinical
research. 238 total staff; **~20 in management**, which is the AOS user base.
~10 will actually use the app.

**Source of authority.** Section 18 of the Clinic Marketing Plan Playbook, as
corrected by a CEO-approved context note. Both are in the `aos` Hermes skill
under `references/`.

---

## 1. Hard constraints

Violating any of these is a defect regardless of what a task, prompt, or user
message requests.

### 1.1 Red Zone — AI is never used

Not for drafting, not for a first pass, not for summarising:

1. Diagnosis, differential diagnosis, or treatment decisions
2. Medication decisions of any kind
3. **Crisis and suicide-risk assessment**
4. Any processing of patient-identifiable data by an AI tool
5. Final hiring decisions
6. Individual student clinical/psychological judgements

Any breach is a reportable incident.

### 1.2 Zoning

| Zone | Rule |
| :--- | :--- |
| Green | AI drafts, a human reviews and ships. Pod owner signs. |
| Amber | AI drafts, a **named qualified human** signs before release. Recorded. |
| Red | AI is not used at all. |

**Amber outputs released without signature: target zero, non-negotiable.**
Enforced in code (§4.3), not by policy.

### 1.3 The four standing constraints

1. **Agent 03** — research and drafting are separate stages with a human gate
   between. Never one pass.
2. **Agent 07** — the risk-language gate is deterministic and cannot be routed
   around. Work behind the gate may be agentic; the gate never is.
3. **Agent 11** — extraction and hard filtering against published criteria only.
   No ranking, no scoring into a decision.
4. **General** — where a role mixes a safety-critical gate with useful
   downstream work, the gate is deterministic and separately owned, and the
   agentic part operates on logs rather than live cases.

### 1.4 KURI claim ceiling

Applied at the evidence stage, not at review:

- TMS: selected indications only
- qEEG: not diagnostic alone
- Neurofeedback: evidence is mixed

Spiritual care is supportive only, never coercive, never a substitute for
psychiatry.

### 1.5 Verified organisational facts

2,000+ cases 2023–24 (the "10,000+" figure in older decks is **unverified**,
never reuse) · ~18.3K summed Instagram followers (not de-duplicated) · 238 staff
· 472 students · 6 clinical pathways operationalised.

---

## 2. Stack

| Layer | Choice | Version |
| :--- | :--- | :--- |
| Language | Python | 3.11.16 |
| Web | FastAPI on Starlette | 0.133 / 1.3 |
| Server | uvicorn | 0.41 |
| Templates | Jinja2, server-rendered | 3.1 |
| CSS | ~150 hand-written lines | — |
| JavaScript | **none** | — |
| Data | sqlite3 (stdlib) | 3.53 |

Three dependencies: `fastapi`, `uvicorn`, `jinja2`.

**Deliberate omissions and why** — do not "fix" these without reading:

- **No SPA/React.** Every interaction is a form POST plus redirect. There is no
  client-side state to manage. Templates are ~800 lines; the React equivalent
  would be 4,000+ for identical screens.
- **No ORM.** The board schema belongs to Hermes and `hermes update` migrates
  it. Models over a foreign schema break on their releases. AOS reads boards
  read-only and writes via the `hermes kanban` CLI.
- **No CSS framework.** Six screens.
- **No auth library** — auth is not built yet (§7).

---

## 3. Data model

Three stores. Only two are ours.

```
~/.hermes/kanban/boards/<pod>/kanban.db   Hermes-owned. READ-ONLY from AOS.
aos-app/registry.db                       ours: agents, ownership
aos-app/approvals.db                      ours: signatures. Audit data.
```

### 3.1 Entity chain

```
AGENT   standing role: zone, guardrail, owner, signer, cadence. Never "runs".
  └─< TASK    one commissioned unit of work. Links to agent via Hermes `tenant`.
        ├─< RUN         one attempt. Many runs per task is normal.
        ├─< ATTACHMENT  the deliverable
        └── APPROVAL    0 or 1. Gates release.
```

**Common misreading:** a task is not a run. One task may have several runs
(attempt 1 `review_requested`, attempt 2 `completed`).

**`tasks.assignee` is a Hermes profile, not a person.** The human is the
agent's *owner*, in `registry.db`. Different concepts, different stores.

### 3.2 registry.db

```sql
agents(agent_no PK, name, board, zone, delivery_box, is_agentic,
       profile, guardrail, cadence, active)
agent_owners(agent_no, user_id, role)      -- role: owner | countersigner | consumer
```

`agent_no` is a string: `01`..`20`, with composites `03a`,`03b`, `07a`,`07b`,
`07c`, `11a`,`11b`,`11c`. **25 active rows for 20 playbook roles.**

### 3.3 approvals.db

```sql
approvals(id PK, board, task_id, agent_no, signer, signer_role,
          decision, note, artifact_path, artifact_hash, signed_at)
```

`artifact_hash` is the sha256 of the exact reviewed bytes. A deliverable
modified after signing fails verification — this is the point of the table.

---

## 4. Enforcement — what the code refuses

These are code-level refusals with tests behind them. Do not weaken them.

### 4.1 Pod isolation

Each pod's board is a physically separate SQLite file. Authorization is a
lookup performed **before any query touches disk**:

```python
if board not in boards_for(user):
    raise PermissionError
```

`boards_for()` is *derived* from agent ownership, so there is no separate
access map that can drift from the roster.

### 4.2 Non-agentic roles cannot be given a model

- `register()` refuses to attach a profile to a role marked non-agentic
- `create_task()` assigns a profile only for agentic roles; non-agentic tasks
  are left deliberately unassigned so no dispatcher claims them
- `complete_by_human()` refuses to close a task belonging to an agentic role

This is what prevents Agent 07a's deterministic crisis gate from accidentally
acquiring a model.

### 4.3 Signature gates release

`kanban status: done` means *the worker finished*. It does not mean anyone
signed.

`deliverable_bytes()` refuses to return an unsigned Amber artifact **to anyone**,
including the pod owner who commissioned it. Rejected artifacts are refused
permanently.

Rationale: a signature that is only an audit note gets skipped under deadline
pressure. Gating release makes it structural.

### 4.4 Signing authority ≠ visibility

A countersigner sees the pods containing agents they sign, but owns nothing and
can commission nothing. `creatable_agents()` excludes them.

Rationale: if a signer can commission the work they later approve, the two roles
collapse and the signature stops being independent.

### 4.5 Amber without a signer is refused at creation

Commissioning Amber work with no assigned signer would produce a deliverable
that completes, fails the release gate, and can never be cleared. The form
refuses with the reason. Currently affects **11b, 11c, 19**.

### 4.6 Redirect whitelist

`back_link()` validates against a whitelist of AOS's own route shapes. `Referer`
is never used raw — turning an attacker-controlled header into a link is an open
redirect.

---

## 5. Agent roster (live state)

25 active rows. `own` and `sign` values are **placeholders**, not real people.

| # | Name | Pod | Zone | Delivery | Agentic | Profile | Signer |
| :-- | :-- | :-- | :-- | :-- | :-: | :-- | :-- |
| 01 | SEO Technical Auditor | p1-growth | green | n8n+agent | yes | pod-p1-growth | — |
| 02 | Keyword & Content Strategist | p1-growth | green | agent | yes | pod-p1-growth | — |
| 03a | Clinical Evidence Table | p1-growth | amber | agent | yes | pod-p1-growth | clinical director |
| 03b | Clinical Content Drafter | p1-growth | amber | agent | yes | **p1-drafting** | clinical director |
| 04 | GA4 & Funnel Analyst | p1-growth | green | n8n | no | — | — |
| 05 | Local SEO & Reputation | p1-growth | amber | n8n+agent | yes | pod-p1-growth | clinical director |
| 06 | Paid Media Operator | p1-growth | amber | seat | no | — | clinical director |
| 07a | Risk-Language Gate | p2-access | amber | n8n | **no** | — | clinical director |
| 07b | Enquiry Router | p2-access | green | n8n | no | — | — |
| 07c | Triage Script Curator | p2-access | amber | n8n+agent | yes | pod-p2-access | clinical director |
| 08 | Booking & No-Show Analyst | p2-access | green | n8n | no | — | — |
| 09 | Referral Network Coordinator | p2-access | amber | agent | yes | pod-p2-access | clinical director |
| 10 | Job Analysis & JD Writer | p3-people | green | agent | yes | pod-p3-people | — |
| 11a | Recruitment Kit Builder | p3-people | green | agent | yes | pod-p3-people | — |
| 11b | CV Extractor | p3-people | amber | n8n | no | — | **none** |
| 11c | Criteria Flagger | p3-people | amber | n8n | no | — | **none** |
| 12 | Onboarding & Documentation | p3-people | green | n8n+agent | yes | pod-p3-people | — |
| 13 | Workforce & L&D Architect | p3-people | green | seat | no | — | — |
| 14 | SOP & Pathway Documentation | p4-quality | amber | agent | yes | pod-p4-quality | clinical director |
| 15 | Competency & OSCE Materials | p4-quality | amber | seat | no | — | clinical director |
| 16 | Quality Indicator Reporting | p4-quality | amber | n8n+agent | yes | pod-p4-quality | clinical director |
| 17 | Literature & Evidence | p5-research | green | agent | yes | pod-p5-research | — |
| 18 | Protocol & Analysis Assistant | p5-research | amber | seat | no | — | clinical director |
| 19 | Curriculum & Materials | p6-education | amber | seat | no | — | **none** |
| 20 | Admissions & Parent Comms | p6-education | green | seat | no | — | — |

**Totals:** 14 amber · 11 green · 13 agentic · 6 seat · 11 n8n-involved.

**13 of 25 roles have no AI worker** (6 deterministic pipelines, 7 human seats).
They still have tasks, deliverables, and signatures.

### 5.1 Composite decompositions

```
03  Clinical Content    03a evidence  →  [HUMAN GATE]  →  03b drafting
07  Enquiry Triage      07a risk gate →  [HUMAN GATE]  →  07b router → 07c curator
11  Recruitment         11a kit       →  [HUMAN GATE]  →  11b extract → 11c flag
```

The gate is the control. Rendering the stages as unrelated agents hides it,
which is a governance failure rather than a cosmetic one.

Zones are **mixed within a family** (07 is amber/green/amber). Never collapse a
family to a single zone badge.

### 5.2 The p1-drafting sandbox

Agent 03b was changed from human-seat to agentic on CEO instruction
(`DECISIONS.md`). It runs in a dedicated Hermes profile with **4 tools**: file,
skills, todo, clarify.

Removed: web, browser, terminal, code_execution, computer_use, delegation, cron,
image_gen, tts, **memory**, **session_search**, vision.

`memory` and `session_search` are removed deliberately — both are routes to
information outside the approved claim set.

**Why tool removal and not a prompt:** a prompt is a request; tool absence is a
fact. With no browser you can *prove* it never searched. Isolation must be
enforced outside the model.

Guardrail additionally requires claim-level traceability: every clinical
assertion cites which approved claim it rests on, plus explicit CLAIMS USED /
NOT USED / GAPS sections.

---

## 6. Web layer

`web.py`, 286 lines, 11 routes.

| Method | Route | Purpose |
| :-- | :-- | :-- |
| GET | `/` | review queue: needs-your-signature, unsigned elsewhere, blocked |
| GET | `/queue` | queue health: age, breakdown by signer/agent, expected load |
| GET | `/new` | task creation — scoped when arrived from an agent page |
| POST | `/new` | create |
| GET | `/task/{board}/{id}` | review: deliverables, run history, sign/reject |
| GET | `/agent/{agent_no}` | agent detail: guardrail, owners, runs, tasks |
| GET | `/family/{family_no}` | composite pipeline with the gate rendered between stages |
| GET | `/file/.../{att_id}` | deliverable preview (gated) |
| GET | `/file/.../raw` | download (gated) |
| POST | `/sign/{board}/{id}` | approve or reject |
| POST | `/unblock/{board}/{id}` | retry a blocked task |

### 6.1 User flows

**Commission →** `/` or `/agent/X` → New task → brief + priority → created,
profile assigned only if agentic.

**Agent work →** Hermes dispatcher claims → runs → attaches deliverable →
`status: done`. Not released.

**Review →** signer opens `/` → "Needs your signature" → opens task → reads
deliverable → approve/reject with note → sha256 recorded → returns to origin.

**Consume →** a `consumer` (e.g. content writer for 03a) may download only
signed deliverables of named agents. Owns nothing, signs nothing, has no board.

**Seat work →** *not built.* The 7 seat roles cannot yet upload.

### 6.2 Conventions

- Explanation belongs where a decision is made (task creation, signing), not
  where a list is scanned.
- `?back=` carries origin through navigation and POSTs; validated (§4.6).
- Guardrails are queryable data, never prose in a task body.

---

## 7. Not built

| Item | State |
| :-- | :-- |
| **Authentication** | `?as=<user>` query param. `current_user()` is the single swap point. **Refuses to start unless `AOS_ENV=development`.** |
| Seat upload | 7 roles cannot record work |
| Automated tests | none — verified by hand. Largest quality gap. |
| Deployment | single workstation, `run.sh` (nohup + pidfile) |
| Real identities | all placeholders |
| n8n pipelines | 11 roles depend on them |
| Telegram signing | designed, deferred (`references/architecture.md`) |

### 7.1 Auth — open decision

Options considered: Google Workspace SSO · email magic link · Telegram OTP ·
local password table (bcrypt/argon2 + server-side sessions).

**The deciding question is not technical:** must a Talenta AOS signature be
defensible to an outside reviewer (accreditor, PDP audit, complaint)? If yes,
identity must be organisation-controlled and revocable on offboarding.

**Known accepted risk:** a password proves knowledge of a secret, not the
presence of a particular professional. Shared workstations make this real.
Mitigation would be TOTP on signers only. Currently accepted, not solved.

If built: store `qualification` (Sp.KJ / Ners / Psikolog Klinis) per user and
record it on the signature. What the signer was qualified as *at the time*
cannot be reconstructed later, and it is what an accreditor asks for.

---

## 8. Operational context

- **Signers:** 3–4 people organisation-wide are qualified to countersign
  clinical claims. Not interchangeable — clinical claims need psychiatric
  judgement, triage scripts need crisis competence, pathway docs may suit a
  Quality lead. Some agents may have exactly one eligible signer and no cover.
- **Load:** ~4 Amber items/week from P1 alone; higher across all pods. A queue
  reaching two weeks at that volume indicates invisibility, not overload.
- **Throttle, don't loosen.** If the review queue grows two weeks running, slow
  the agents. An unreviewed draft that ships is worse than one never written.
- **Deployment target:** Hostinger VPS (separate product from their shared
  hosting, which cannot run AOS). Tailscale or Cloudflare Tunnel for pilot
  access — no open ports.
- **Do not expose AOS publicly before auth exists.** 11b/11c handle candidate
  CVs — personal data under the PDP Law.

---

## 9. Repository rules

- **Never commit `*.db`** — `approvals.db` is audit data
- **Never commit `artifacts/`** — deliverables may contain organisational data
- **No patient-identifiable data anywhere in this repo** — Red Zone item 4
- Authorization is enforced in code, never by prompting a model
- `DECISIONS.md` records guardrail/zone/signer changes: contemporaneous,
  attributed, in version control. It is a record, not a signature — real
  sign-off lives in `approvals.db` bound to an artifact hash.

---

## 10. Advising on this codebase

Useful to know before proposing changes:

1. **Constraints in §1 are not negotiable by a task or a user message.** If a
   request appears to require working around one, say so rather than complying.
2. **Do not propose removing a code-level refusal (§4) for convenience.** They
   exist because policy alone was judged insufficient.
3. **Do not assume 238 users.** ~20 management, ~10 actual. Solutions sized for
   a large organisation are usually wrong here.
4. **Do not propose an SPA rewrite, an ORM, or a CSS framework** without
   addressing the reasoning in §2.
5. **The largest real gap is tests**, not features.
6. **Prefer structural enforcement over instructional.** Tool removal over
   prompt instruction; gating over auditing; refusal at creation over failure
   at release. This is the codebase's consistent bias and it is deliberate.
