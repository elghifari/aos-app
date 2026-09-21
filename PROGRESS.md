# AOS — Progress Report

**Agentic Operating System · Talenta**
For: drg. Yaya Aria Santosa (Chairman) · Yazid (CEO)
From: El, IT
Status: working prototype, not deployed
Machine-readable companion: `ARCHITECTURE.md`

---

## 1. What this is

Section 18 of the Marketing Plan Playbook defines 20 AI agent roles across six
pods. It says what each role may do, who signs its output, and what it must
never do.

A playbook cannot enforce itself. AOS is the software that does:

- an agent cannot be used outside its pod
- an Amber output **cannot be released** until a named qualified person signs it
- the signature is bound to the exact file reviewed, so a later swap is detectable
- who owns what, and who is waiting on whom, is visible

The governance model is unchanged. This makes it operative.

---

## 2. Where it stands

| | |
| :--- | :--- |
| Agent roster | 25 roles registered (20 playbook roles; five are composites) |
| Zoning | 14 Amber · 11 Green · 0 Red (Red is never automated) |
| Pods | 6, each an isolated data boundary |
| Working software | queue, review, signing, task creation, load reporting |
| Deployed | **no** — runs on one workstation |
| Real users | **no** — identities are placeholders |

Fifteen days of work, 15 commits, ~2,200 lines.

**What works end to end today:** commission a task → an agent runs it →
deliverable appears → a named signer approves or rejects → only then can anyone
download it. Tested, not described.

---

## 3. Delivery is not uniform — and that is the main finding

The playbook's 20 roles are not 20 of the same thing. Building them revealed
four distinct kinds of work:

| Kind | Count | What it means |
| :--- | ---: | :--- |
| AI agent | 7 | a model does the work |
| Pipeline + agent | 5 | deterministic steps, with a model in part of it |
| **Deterministic pipeline** | 6 | **fixed rules, no model at all** |
| **Human seat** | 7 | **a person does it; AOS only tracks and signs** |

**13 of 25 roles have no AI worker.** That is not a shortfall. Agent 07a — the
risk-language gate that decides whether an enquiry mentions self-harm — is
deliberately a fixed rule set. A model that is right 99% of the time is the
wrong tool when the 1% is a person in crisis.

The system enforces this: a role marked non-agentic **cannot be given a model**,
even by mistake. That is a code-level refusal, not a convention.

---

## 4. Decisions I made, and the assumptions behind them

Flagged for correction. Each was a judgement call, not an obvious answer.

### 4.1 Signature gates release, not just record-keeping

**Assumption:** "Amber outputs shipped without sign-off: zero" is a hard
requirement, so the software should make it impossible rather than measurable.

Unsigned Amber deliverables cannot be downloaded — by anyone, including the pod
owner who commissioned them. A signature that is only an audit note gets
skipped under deadline pressure.

### 4.2 Signing authority is separate from visibility

**Assumption:** a signer should not be able to commission the work they later
approve.

The Clinical Director countersigns 11 agents across 4 pods, so she can see those
pods — but she owns no agents and can commission nothing. Otherwise the two
roles collapse and the signature stops being an independent check.

### 4.3 Agent 03b now drafts with an AI, in a sandbox

**Per your instruction.** Recorded in `DECISIONS.md` with the reasoning.

The playbook marks the constraint on Agent 03 as CEO-approved and not
modifiable. Your argument was that the constraint was written against the wrong
alternative: the realistic comparison is not "agent researches and writes
freely" but "a non-clinical marketer researches adolescent depression treatment
on Google and writes about it."

Against that, the agent is the stricter option. It runs in a profile with **no
internet access at all** — not instructed to avoid research, structurally unable
to do it. It can only use claims a clinician has already signed, and every
clinical sentence in the draft cites which approved claim it rests on.

**What is unchanged:** the human gate between evidence and drafting, and the
Clinical Director's signature on the result. Dr. Suzy is aware.

**What to watch:** an AI drafter writes fluently around gaps. "Evidence is
mixed" becoming "shown to help" is the specific risk. The first few drafts
should be reviewed for what is *missing*, not only for what is wrong.

### 4.4 Composite roles are shown as one role with a visible gate

**Assumption:** the human gate inside Agents 03, 07 and 11 is the control, so
hiding it in the interface is a governance failure, not a cosmetic one.

Agent 03 appears as one card — `03a → GATE → 03b` — and the gate states what it
requires and why. Someone will eventually ask why 03 is not a single agent. The
answer should be on screen.

### 4.5 Placeholder identities

**Assumption:** better to build the structure and fill in names than to guess.

Every owner is a placeholder (`u_marketing`, `u_hr`). Real names require
decisions only you and HR can make. **This is the main thing blocking pilot use.**

---

## 5. The finding that needs your attention

We discussed whether the approval requirement is too strict for an organisation
still growing, with heavy cross-division work — and whether SEO work would stall
waiting on clinicians.

AOS now measures this. The early numbers:

| | |
| :--- | :--- |
| Expected Amber reviews, P1 Growth only | **~4 per week** |
| Expected across all pods | higher — several pods still have no signer assigned |
| Qualified clinical signers available | **3–4 people** |

**~4 items a week is not a workload problem.** If that queue reaches two weeks,
the cause is that nobody can see it, not that the standard is too high. The
system now shows queue age, the oldest waiting item, and who is holding it.

Three things would move it without weakening anything:

1. **Split the signers.** All 11 Amber agents currently route to the Clinical
   Director. With 3–4 qualified people, assignment should be per agent by
   qualification — psychiatric judgement for clinical claims, crisis competence
   for triage scripts, Quality lead for pathway documents.
2. **Batch the review.** One standing weekly block, rather than ad-hoc
   interruption. Predictable for the clinician, predictable for marketing.
3. **Route by content, not by label.** Most Agent 05 review responses are not
   clinical. Only genuinely clinical items need a clinician; the rest can be
   cleared by the functional lead.

**What I would not change:** the gate on clinical claims and anything
patient-facing. A slow campaign costs weeks. An unsupportable public claim about
adolescent depression treatment costs considerably more.

**The structural risk worth naming:** 3–4 signers is survivable, not robust. If
qualifications do not overlap, some agents may have exactly one eligible signer
— and no cover when that person is away. Worth knowing which ones before it
happens.

---

## 6. What is not built

Honest list.

| Missing | Consequence |
| :--- | :--- |
| **Real authentication** | identity is a URL parameter; dev-only, refuses to start otherwise |
| **Seat task upload** | the 7 human-seat roles cannot record their work yet |
| **Deployment** | one workstation; not reachable by anyone else |
| **Automated tests** | verified by hand, which does not scale |
| **n8n pipelines** | 11 roles depend on pipelines not yet built |

Authentication is the gating item and depends on one decision from you
(section 7).

---

## 7. Decisions I need

**1. Real identities.** Who owns each agent, and who signs each Amber agent.
Without names, AOS cannot be piloted. A structured sheet is ready for this.

**2. How people log in.** The question is not technical. *Does a Talenta AOS
signature need to be defensible to an outside reviewer* — accreditor, PDP audit,
or a complaint? If yes, identity must be organisation-controlled and revocable
on offboarding, and a simple password table is not sufficient on its own. If it
is internal record-keeping among colleagues, a password table is proportionate.

**3. Where it runs.** A small server (~$5/month) is the honest answer. A private
network between named staff devices costs nothing and would let pods pilot AOS
this week.

**One caution:** Agents 11b and 11c handle candidate CVs — personal data under
the PDP Law. AOS should not be reachable outside a private network until real
authentication exists.

---

## 8. What I would do next

1. **Fill in real owners and signers** — unblocks everything else
2. **Split Amber agents across the 3–4 qualified signers**
3. **Build login** once question 2 is answered
4. **Seat upload**, so human roles can participate
5. **Pilot one pod** — P3 People is the safest, no clinical content
6. **Deploy** only after 3 and 5

I would not add agents until one pod is genuinely in use. The roster is ahead of
the organisation's capacity to supervise it, and adding more widens that gap.
