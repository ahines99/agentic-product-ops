# ADR-024: Blocking questions settle decisions; observed calls settle spend

Status: accepted by the owner, 2026-09-30.

## Context

The held-out evaluation in ADR-023 found one rule stopping most answered requests. A requirement's
"needs a human decision" flag could clear only when every question affecting it was answered,
including non-blocking ones. Only blocking questions are put to a person, and the calibrated
prompts record minor gaps as non-blocking questions, so the flag could not clear in 25 answered
revisions.

Separately, spend caps were enforced against full reservations, sized for the maximum possible
input and output of every call. A 20-case run reserved $15.23 for about $6 of usage, so a cap
stopped work long before it was reached in money.

## Decisions

**Only blocking questions hold a decision flag.** A revision may clear `needs_human_decision` on a
requirement once every blocking question affecting it has an authenticated answer. Non-blocking
questions stay open and visible on the proposal. A flagged requirement with no blocking question
still cannot be cleared, and every other revision invariant is unchanged.

**Observed calls count at their usage.** Against a spending cap, a call with recorded provider
usage counts at that usage priced at the authorization's conservative rates, never more than its
reservation. A call without recorded usage (in flight, failed or uncertain) keeps its whole
reservation. The conservative rates are at or above published prices, so the cap remains an upper
bound on actual spend. Summaries report both `reserved_usd` and `committed_usd`.

## Results

On a fresh 16-case set, no answered case stopped on the flag rule, which had held 8 of 12
answered cases before; 5 of the 7 answered cases evaluated reached a reviewed proposal. The cap
counted $9.81 at conservative rates against about $7.28 estimated at standard rates, and refused
further calls before they were sent once it was reached, leaving 8 cases unevaluated. See
[validation](../validation.md#fresh-set-after-the-decision-flag-change).

## Consequences

- Answered requests are no longer held by optional questions; a person still approves every
  proposal and sees the open optional questions.
- Caps admit more work for the same money. Concurrency stays safe: in-flight calls still count in
  full, which a test exercises by holding two calls open while six competitors are refused.
- If published prices ever exceed the configured conservative rates, the bound no longer holds;
  the rates must be reviewed when the model or price list changes.
