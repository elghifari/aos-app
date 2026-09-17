# Decision log

One entry per decision that changes a guardrail, a zone, a signer, or a
constraint. Written by whoever implements it, at the time, in their own words.

**This is a record, not a signature.** It says who decided and when, so the
change is attributable and reversible. It does not claim the decider reviewed
this file. Where a decision needs real sign-off, that lives in `approvals.db`
against a specific artifact.

Keep entries short. If an entry takes more than five minutes, the decision
probably was not made yet.

Format:

```
## YYYY-MM-DD · <what changed>
**Decided by:** <name> · **Recorded by:** <name> · **Source:** verbal / chat / meeting
**Was:** ...
**Now:** ...
**Why:** ...
**Notified:** <who needs to know, and whether they have been told>
```

---

## 2026-09-16 · Agent 03b may be drafted by an agent

**Decided by:** Yazid (CEO) · **Recorded by:** El · **Source:** verbal, relayed

**Was:** 03b `seat` — a human drafts clinical content from the approved claim
set. Marked "not modifiable" in `constraints.md` as part of the CEO-approved
correction.

**Now:** 03b agentic, running on the `p1-drafting` profile.

**Why:** if a human writes the article anyway, 03a saves only the literature
search — roughly 20% of the work — and the automation does not pay for itself.

**What did not change.** The constraint's stated reason is that the agent must
not research and write *in one pass*, because claims generated alongside their
own sources invite post-hoc justification. Two separate runs with a human gate
between them is not one pass. The gate, the signature, and the `BELUM DIREVIEW`
watermark are unchanged.

**How the claim set is enforced.** `p1-drafting` has no web, no browser, no
terminal, and no memory or session search — four tools total. The drafter
cannot reach anything outside the claim set supplied in the task, so this is
provable rather than promised. A human drafter could google mid-draft; this
cannot.

**Residual risk.** An LLM writes fluent prose that subtly inflates hedged
evidence — "evidence is mixed" becoming "shown to help". That is the second
half of the original constraint and it still applies. Mitigation: claim-level
citation markers (`[C3]`) so the reviewer checks a mapping rather than reading
for tone.

**Notified:** Dr. Suzy Yusna Dewi — informed. Registry flipped 2026-09-16.

**The counterfactual matters, and it was not what the constraint assumed.**
The clinicians' own first proposal was for the marketing team to research and
write these articles themselves. The original constraint was written against
"an agent researches and writes in one pass" — but the real alternative on the
table was a non-clinical marketer researching adolescent depression treatment
by search engine, juggling it alongside content production, on a topic they do
not know.

Measured against that, a drafter with no internet access that can only use
claims a clinician has already signed is the **stricter** option. The evidence
pass is done by an agent that must show its sources; the claims are cleared by
a clinician; the drafter cannot reach past them. The human alternative had no
gate at all.

**Reversal:** set `03b` `delivery_box` back to `seat` in `registry.db` and
delete the `p1-drafting` profile. No data migration.
