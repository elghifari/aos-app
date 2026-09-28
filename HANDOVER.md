# AOS — Session Handover

Last verified: **2026-09-28 SEAST**

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
- User commits and pushes their own work unless they explicitly ask otherwise
- The UI redesign, 03a→03b handoff, and `run.sh` health-check fix were
  committed together. Check `git status` and `git log -1` for live state.
- The deleted `AOS_agent_decisions.xlsx`, demo/rehearsal scripts and watermark,
  temporary `.hermes-tmp.*`, and design review artifacts were deliberately not
  included in that commit. Their ownership and retention need separate review.
- The post-build UI audit (`anti-slop/audit-001-2026-09-22.md`) records residual
  mobile wrapping, touch-target, dialog, and copy issues; they were not fixed
  by the 03b handoff work.

## Verified runtime state

- Development server: `http://127.0.0.1:8077`
- Last health check: HTTP 200 for the task page and 03b form
- Application routes: 13, excluding FastAPI documentation routes
- Test command:

  ```bash
  python -m unittest discover -s tests
  ```

- Last result: **64 tests passed**; `bash tests/test_run_script.sh` also passed
- On 2026-09-28, a `/new` 500 was traced to AOS passing the obsolete
  `--completion-contract artifact-required` to `hermes kanban create`. Hermes
  now accepts only `local-only` or a GitHub PR target. The unsupported flag
  was removed; the artifact instruction remains in the task body, and Amber
  release still requires an artifact-bound qualified signature. CLI failures
  now re-render the form (503) with the brief retained, instead of a generic
  500.
- Responsive task creation (2026-09-28): a Create submission no longer waits on
  three sequential CLI calls. Ordinary agentic work is assigned in the same
  `create --assignee` call, the HTTP handler redirects to the task page as soon
  as Hermes returns the real task ID, and dispatch runs after the response via a
  FastAPI `BackgroundTask`. The ~60-second gateway tick remains the fallback if
  that post-response dispatch is interrupted. Gated work (03b) is still created
  unassigned, has its provenance `link` recorded first, and is only then
  assigned — the prerequisite ordering is preserved. `ready` now renders as
  **Queued / "Waiting for a worker to start."** so the redirect target is
  truthful before a worker claims it. Both `/new` form variants expose a
  `data-create-form` hook, a `data-create-button` that switches to "Creating…",
  and a polite `role="status"` live region; `pageshow` restores the button on
  bfcache back-navigation.
- Verified live end-to-end on the restarted server: a public-literature 03a
  task submitted through the real HTTP form returned `303` to
  `t_333d485e` immediately, the task page rendered live state, and background
  dispatch moved it to `running` assigned to `pod-p1-growth` without waiting for
  the tick. (This smoke-test task is real board work pending clinical sign-off;
  archive it when no longer needed.)
- `run.sh`/`stop.sh` pidfile fix (2026-09-28): on Windows git-bash the `python`
  launcher re-execs the runtime python as a child, so `$!` captured a
  short-lived intermediate PID and the pidfile never matched the real listener —
  `stop.sh` could not kill the server. `run.sh` now resolves the true listening
  PID once the port answers; `stop.sh` kills by pidfile and then sweeps anything
  still listening on 8077. Restart round-trip verified.
- Tests use temporary board, registry, approval, filesystem, and profile-log
  fixtures. They do not call an LLM and do not use the live approvals DB.

## What AOS currently does

AOS is the employee-facing governance layer over Hermes kanban boards. Hermes
owns execution. AOS owns task commissioning, pod authorization, review state,
and release of deliverables.

Implemented employee flow:

1. An owner chooses one of their registered agents and submits a task.
2. For agentic work the assignee is set in the same `create` call, and the form
   redirects to the task page as soon as the real task ID exists; dispatch runs
   just after the response. The roughly 60-second gateway tick remains a
   fallback if that post-response dispatch fails. Gated work (03b) is created
   unassigned and assigned only after its provenance link is recorded.
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

An approved 03a task shows **Send to 03b** in its Review state box to the 03b
owner. That opens a form with the source fixed to this task; it does not dispatch
until the owner enters a title and drafting brief and submits. General 03b
creation also requires selecting an approved 03a task. `create_task()` rejects
missing or stale approval even for direct calls; it carries only the selected
task's current approved files, checks their bytes against the signed hashes,
and records provenance in task links and the injected task body.

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

## Historical trial tasks (recheck status before use)

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

On 2026-09-28, `pod-p1-growth` was configured with `web.search_backend: tavily`,
`web.extract_backend: tavily`, and `web.keyless_rescue: false`. Tavily is running
keyless (no provider key was found in the profile or process). The model remains
on the company-provided Anthropic credential; no personal GPT credential was
added to P1. Its CLI toolset still has no terminal or code execution.

A P1 CLI diagnostic successfully searched for a 2025 Indonesian autism paper,
extracted the open-access Springer article 10.1007/s44202-025-00381-0, and read
its Method and Results from the full saved page. A second P1 CLI call extracted
the abstract of 10.1007/s44217-026-01149-x. A direct native Tavily extraction
of the second URL first returned `Error fetching content` and succeeded on
retry: keyless access is still not a production reliability guarantee. This
was a profile CLI diagnostic, **not** an Agent 03a board run. The real
commissioning flow remains to be tested with a user-created, non-patient task.

`grounded-citations` is installed in P1, but its Python ledger/verifier cannot
run inside the restricted worker. The evidence/quotation instructions can be
followed; automated claim-to-quote verification needs a controlled host-side
gate before it may be treated as enforced.

The important defect was behavioural: a worker could lose source access and
still report that citations had been verified. The standing prompt reduces that
risk; the deterministic integrity hold prevents silent release. A keyed
provider may improve availability but would not replace the integrity control.

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
2. Run `git status --short`; preserve unrelated local files and changes.
3. Run `python -m unittest discover -s tests` before editing.
4. Confirm whether task `t_f912128e` was approved before changing the warning or
   Agent 03 flow.
5. Fix the documented consistency defects before adding another agent or major
   workflow. The seed mismatch and authorize-before-read ordering are first.
6. Then ask which product gap to take next: real auth, revision/clarification,
   seat upload, or better source-success telemetry.
7. After significant work, update this handover's verified state and known gaps.
