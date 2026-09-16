# AOS — who does it, who signs it

One decision per agent. Two questions:

1. **Does the work** — for `seat` roles, which named person. For agent/n8n roles, which person owns the output.

2. **Signs it** — only Amber needs a signature. Green ships without one, by design.


*Zone and delivery are already fixed by the playbook and are not open for decision here.*


## P1 Growth

| # | Agent | Zone | Work done by | Owner (accountable) | Signs before it ships |
|---|---|---|---|---|---|
| 01 | SEO Technical Auditor | green | n8n + Hermes worker | **______________** | — *(green: none)* |
| 02 | Keyword & Content Strategist | green | Hermes worker | **______________** | — *(green: none)* |
| 03a | Clinical Evidence Table | amber | Hermes worker | **______________** | **______________** |
| 03b | Clinical Content Drafter | amber | a person | **______________** | **______________** |
| 04 | GA4 & Funnel Analyst | green | n8n pipeline (no model) | **______________** | — *(green: none)* |
| 05 | Local SEO & Reputation | amber | n8n + Hermes worker | **______________** | **______________** |
| 06 | Paid Media Operator | amber | a person | **______________** | **______________** |

> **01** — Cannot deploy. Output is a ticket list for the web vendor.

> **02** — Must use real volume data. Cannot invent search volumes.

> **03a** — Evidence table only. No prose, no draft. KURI ceiling at this stage.

> **03b** — Drafts from the APPROVED CLAIM SET only. Never researches and writes in one pass. BELUM DIREVIEW watermark until signed.

> **04** — Aggregate exports only. No user-level data. Never condition-based audiences.

> **05** — Any review alleging a clinical issue routes to Clinical Director and EXITS the agent workflow.

> **06** — Clinical-and-legal gate before live. No superiority/cure claims, no crisis-page retargeting.


## P2 Patient Access

| # | Agent | Zone | Work done by | Owner (accountable) | Signs before it ships |
|---|---|---|---|---|---|
| 07a | Risk-Language Gate | amber | n8n pipeline (no model) | **______________** | **______________** |
| 07b | Enquiry Router | green | n8n pipeline (no model) | **______________** | — *(green: none)* |
| 07c | Triage Script Curator | amber | n8n + Hermes worker | **______________** | **______________** |
| 08 | Booking & No-Show Analyst | green | n8n pipeline (no model) | **______________** | — *(green: none)* |
| 09 | Referral Network Coordinator | amber | Hermes worker | **______________** | **______________** |

> **07a** — DETERMINISTIC. Fail-closed, recall-tuned, irreversible per conversation, runs BEFORE any model sees text. Never agentic.

> **07b** — Administrative classification only. Never assesses clinical urgency.

> **07c** — Reads LOGS ONLY, never live conversations. Scripts approved by Clinical Director.

> **08** — Aggregate, de-identified before reaching any AI tool. Operations decide.

> **09** — Produces the TEMPLATE, never the instance. Outcome comms written by a clinician with documented consent.


## P3 People

| # | Agent | Zone | Work done by | Owner (accountable) | Signs before it ships |
|---|---|---|---|---|---|
| 10 | Job Analysis & JD Writer | green | Hermes worker | **______________** | — *(green: none)* |
| 11a | Recruitment Kit Builder | green | Hermes worker | **______________** | — *(green: none)* |
| 11b | CV Extractor | amber | n8n pipeline (no model) | **______________** | **______________** |
| 11c | Criteria Flagger | amber | n8n pipeline (no model) | **______________** | **______________** |
| 12 | Onboarding & Documentation | green | n8n + Hermes worker | **______________** | — *(green: none)* |
| 13 | Workforce & L&D Architect | green | a person | **______________** | — *(green: none)* |

> **10** — Validated by the role's actual supervisor. AI consistency is not accuracy.

> **11a** — Produces ads/rubrics BEFORE any candidate exists. Never sees a CV.

> **11b** — Declared facts into fixed columns. No free-text column. Never infers to fill a blank.

> **11c** — Flags met/not met/not stated against PUBLISHED criteria. Never ranks. Never removes a row. Fixed sort order.

> **12** — Legal/compliance content verified against current Indonesian regulation by a human before issue.

> **13** — Clinical competency standards set by clinical leadership; the agent structures, it does not define competence.


## P4 Quality & Clinical Ops

| # | Agent | Zone | Work done by | Owner (accountable) | Signs before it ships |
|---|---|---|---|---|---|
| 14 | SOP & Pathway Documentation | amber | Hermes worker | **______________** | **______________** |
| 15 | Competency & OSCE Materials | amber | a person | **______________** | **______________** |
| 16 | Quality Indicator Reporting | amber | n8n + Hermes worker | **______________** | **______________** |

> **14** — Clinical content ORIGINATES FROM CLINICIANS. Edits and structures; does not author protocol.

> **15** — Scenarios clinically validated before use. Assessment decisions made by human assessors.

> **16** — Aggregate, de-identified. Interpretation of a clinical trend is a clinical judgement.


## P5 Research (IIMH)

| # | Agent | Zone | Work done by | Owner (accountable) | Signs before it ships |
|---|---|---|---|---|---|
| 17 | Literature & Evidence | green | Hermes worker | **______________** | — *(green: none)* |
| 18 | Protocol & Analysis Assistant | amber | a person | **______________** | **______________** |

> **17** — EVERY citation verified to exist and to say what the summary claims. Verification is not optional.

> **18** — De-identified data only, only where ethics approval permits. Statistical conclusions verified by a qualified analyst.


## P6 Education

| # | Agent | Zone | Work done by | Owner (accountable) | Signs before it ships |
|---|---|---|---|---|---|
| 19 | Curriculum & Materials | amber | a person | **______________** | **______________** |
| 20 | Admissions & Parent Comms | green | a person | **______________** | — *(green: none)* |

> **19** — An individual child's IEP content is written by their teacher and therapist. No named student data.

> **20** — No individual student or family information.


---

**14 agents need a named signer. 11 are green and need none.**


For each signer, also record the qualification the role requires (e.g. Sp.KJ, Psikolog Klinis, Ners, or a named supervisor), because the system checks it before recording a signature.
