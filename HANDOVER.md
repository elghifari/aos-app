# AOS — Session Handover

Last verified: **2026-09-22 09:25 SEAST**

This is the compact entry point for the next engineering session. It records
current implementation state, verification, known gaps, and where to continue.
It is not a leadership progress report and not a substitute for the governance
source documents.

## Read this first

A new session should read, in order:

1. The Hermes skill named **`aos`**. It is the authority for the Red Zone,
   Agent 03/07/11 constraints, roster, zoning, and organisational facts.
2. `README.md` for the current application overview and operating commands.
3. This file for current development state.
4. `ARCHITECTURE.md` when the task changes system boundaries, data flow,
   authorization, release behavior, or another documented invariant.
5. Only the source files relevant to the task being changed.

Do not ingest the full repository by default. Confirm implementation claims
against live code or tests when they matter.

## Repository state

- Repository: `C:/Users/M. Daffa El Ghifari/aos-app`
- Branch: `main`
- HEAD: `2cb81a3`
- Remote: `origin/main` is 0 ahead / 0 behind HEAD
- Working tree: intentionally uncommitted iterative work exists
- User commits and pushes their own work unless they explicitly ask otherwise

Current modified implementation areas:

- `aos.py`
- `web.py`
- `templates/_taskfields.html`
- `templates/new.html`
- `templates/queue.html`
- `templates/task.html`
- `tests/test_approvals.py`
- `tests/test_web.py`
- `README.md`
- `ARCHITECTURE.md`
- `HANDOVER.md`

Current additions:

- `demo.sh`
- `rehearse.sh`

Current repository housekeeping still to decide:

- `.hermes-tmp.wyrlK8/` is untracked and appears temporary.
- `.rehearsal-watermark` is untracked rehearsal state.
- Do not delete either without checking whether the current demo reset flow
  still needs it.

## Verified runtime state

- Development server: `http://127.0.0.1:8077`
- Last health check: HTTP 200, about 30 ms for the u_hr home page
- Application routes: 13, excluding FastAPI documentation routes
- Test command:

  ```bash
  python -m unittest discover -s tests
  ```

- Last result: **46 tests passed in 5.752 seconds**
- Tests use temporary board, registry, approval, filesystem, and profile-log
  fixtures. They do not call an LLM and do not use the live approvals DB.

## What AOS currently does

AOS is the employee-facing governance layer over Hermes kanban boards. Hermes
owns execution. AOS owns task commissioning, pod authorization, review state,
and release of deliverables.

Implemented employee flow:

1. An owner chooses one of their registered agents and submits a task.
2. Agentic work is assigned and dispatched immediately. The roughly 60-second
   gateway tick remains a fallback if direct dispatch fails.
3. Home shows work as running, waiting, or finished.
4. Task pages show plain-language progress rather than exposing only raw board
   status.
5. Finished items can be dismissed with **Done**. This archives the task rather
   than deleting it; task, files, runs, and signatures remain available.
6. The home page shows at most the eight most recent finished items. Running and
   waiting work is never capped.

Dismiss is deliberately the only direct write to a Hermes board DB: it updates
`tasks.status` to `archived`. The board is WAL-backed with a five-second busy
timeout. This removed about two seconds of CLI startup from a simple UI action.
Task creation, assignment, linking, unblock, and dispatch still go through the
Hermes CLI because Hermes owns those invariants.

Read-only board connections are pooled per board. Each query starts a fresh
read transaction and sees external dispatcher commits. This reduced the ADHD
task page from about 182 ms to about 47 ms without caching task data.

## Approval and release model

`done` means the worker finished. It does not mean the output is released.

Amber release is bound to:

- board;
- task;
- attachment ID;
- SHA-256 of the exact reviewed bytes;
- qualified signer and decision.

A reviewer opens a dedicated review route, sees the exact checksum, and records
Approve or Reject there. The ordinary raw-download route remains closed until
approval. If bytes change after preview or after signing, release is refused.
Rejected work remains rejected and visible in the queue.

Legacy approvals containing only a bare digest remain valid only when exactly
one attachment on that task has those bytes. Ambiguous matches fail closed.

Empty artifacts and bare placeholders such as `null`, `{}`, and `[]` are not
presented as deliverables and do not hold a substantive file hostage. Do not
replace this with a broad size threshold; short legitimate files exist.

An unsigned owner sees a normal **Under review** page rather than raw 403 JSON.
The qualified signer can still access the review-only file route.

## Agent 03 flow

Agent 03 is implemented as two stages with a code-enforced human gate:

- **03a** researches and produces an evidence table.
- A qualified human approves the current 03a artifact.
- **03b** can then start and receives only the approved claim set.

A direct request cannot bypass the gate. `create_task()` returns a gate error if
no current 03a artifact has been approved. Provenance is recorded in task links
and in the injected task body with signer and SHA-256 details.

The `p1-drafting` profile has no web access, so 03b cannot research around the
approved claim set.

### 03a standing rules

Employees should be able to write short briefs. AOS therefore prepends 03a's
standing evidence rules inside `create_task()` rather than requiring users to
repeat them. They require:

- research only, never marketing or patient-facing copy;
- citations only from sources opened during that run;
- DOI or PMID and a short supporting quotation per row;
- failed lookups listed under `COULD NOT VERIFY`;
- no reconstruction from model memory when sources cannot be reached;
- the KURI ceiling at evidence-gathering time.

Agents without an entry in `STANDING_RULES` receive the original brief
unchanged.

### Evidence-tool integrity guard

`run_integrity()` correlates the latest task-run timestamps with the assigned
profile's `logs/errors.log`. If an evidence tool failed within that run window,
the task is marked degraded and held for human review even if the worker claimed
success.

This control deliberately does not trust the worker's own report. A qualified
approval of the exact artifact clears the warning because the purpose of the
hold is to force independent human review, not to veto that review.

Known limitation: the current guard counts failures but does not record
successful calls. A run with one successful search and one failed search is
still marked degraded. The warning therefore means **some source access failed**,
not necessarily that every paper was unreachable. Preserve the hold, but improve
telemetry before making stronger claims in the UI.

## Current real trial tasks

### 03a TMS trial

- Board: `p1-growth`
- Task: `t_f912128e`
- Title: `Riset TMS untuk depresi remaja`
- Status: done
- Artifact: attachment 11, `riset-tms-depresi-remaja.md`, 9,731 bytes
- Integrity result: degraded; eight `web_search` failures occurred in the run
- Review state at last check: unsigned

The user manually checked the papers and considers them factual. That check must
be recorded through the Clinical Director review route before the warning is
removed:

`/file/p1-growth/t_f912128e/11?as=u_clinical_director`

The task-page warning already disappears after a qualified approval. A
regression test covers this. Do not remove the pre-signoff warning merely because
an informal check occurred; that would bypass the Agent 03 gate.

### Agent 12 rehearsal

- Board: `p3-people`
- Task: `t_05afd4b0`
- A real onboarding checklist was produced successfully.
- The task was archived from u_hr's finished-work list during dismissal testing.
- Archiving did not delete the task or artifact.

## Search reliability finding

Hermes web search is not inherently unavailable to the pods. A direct test from
`pod-p1-growth` returned results. However, the keyless provider path is
intermittent: trial runs have recorded repeated Firecrawl/search failures.

The important defect was behavioural: a worker could lose source access and
still report that citations had been verified. The standing prompt reduces that
risk; the deterministic integrity hold prevents silent release. A paid Exa or
Parallel key would improve availability but would not replace the integrity
control.

This desktop chat and each pod are separate Hermes profiles with isolated
sessions and memories. AOS workers cannot see this conversation unless relevant
context is explicitly placed in the task body.

## Known gaps

1. **Authentication:** identity is still `?as=<user>` and is development-only.
2. **Real owners/signers:** registry identities are placeholders.
3. **Seat-work upload:** human seat roles cannot upload their deliverables.
4. **Clarification/revision loop:** employees cannot answer an agent's question
   or request a new version in the same task with version history.
5. **Deployment:** local workstation only.
6. **n8n pipelines:** deterministic/event-driven roles are not implemented.
7. **Capability proposals:** employee proposes a new task → IT reviews and
   configures it is explicitly deferred.
8. **Source telemetry:** the integrity guard observes errors but cannot yet prove
   which sources were opened successfully.
9. **Agent history UX:** the home page is bounded; individual agent pages can
   still become long over time.

### Known implementation defects

The architecture refresh surfaced four defects that should precede new product
work:

1. `seed_registry.py` would revert 03b from agentic `p1-drafting` to seat work.
2. `sign()`, `can_review()`, and `attachment()` do not consistently authorize
   before reading task data.
3. Web approvals store `amber` as `signer_role` instead of countersigner or the
   signer's qualification.
4. A degraded Green run can be held without a named person able to clear it.

See `ARCHITECTURE.md` §14 for the full consistency list.

## Safety and development constraints

- Read `aos` skill `references/red-zone.md` before clinical, patient, hiring, or
  student-data work.
- Never process patient-identifiable data in an AI tool.
- Never weaken the deterministic constraints on Agents 03, 07, or 11.
- Never write to live boards, `approvals.db`, or production profiles merely to
  test code. Use temporary fixtures.
- Never fabricate clinical artifacts for demos.
- Do not emulate LLM responses in the test suite.
- Use stdlib `unittest`; pytest is not installed.
- Do not commit or push unless the user explicitly asks.
- Generated deliverables and database files must remain out of git.

## Where the next session should start

1. Load the `aos` skill and this file.
2. Run `git status --short`; do not discard the current uncommitted iteration.
3. Run `python -m unittest discover -s tests` before editing.
4. Confirm whether task `t_f912128e` was approved before changing the warning or
   Agent 03 flow.
5. Fix the documented consistency defects before adding another agent or major
   workflow. The seed mismatch and authorize-before-read ordering are first.
6. Then ask which product gap to take next: real auth, revision/clarification,
   seat upload, or better source-success telemetry.
7. After significant work, update this handover's verified state and known gaps.
