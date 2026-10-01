# ADR-023: Reviewed inferences may proceed; calibrate when questions block

Status: accepted by the owner, 2026-09-30.

## Context

The 16-case evaluation in ADR-022 found two causes that together stopped every general request:

1. The readiness gate rejected any requirement marked `safe_inference` with the finding
   "inferred behavior needs independent review", even immediately after the independent reviewer
   had passed that exact proposal. The gate was written before the reviewer existed and never
   learned about it.
2. The analyst marked minor details (an event payload, a default) as blocking questions, so it
   stopped on every well-specified request.

## Decisions

**A passing review satisfies the inference rule.** An inferred requirement no longer blocks
readiness when the caller supplies a review that (a) is bound to the exact content digest being
checked and (b) has no blocking findings. The review always comes from trusted persistence: the
revision pipeline passes the review it just recorded, and approval, publication, handoff and
workflow validation load it with `passing_review`, which returns only a stored review that
`recorded_review` accepts. A model cannot supply or forge it. Without such a review, with a review
of other content, or with any blocking finding, the rule still holds. Every other readiness check,
including acceptance criteria that need a human decision, is unchanged. A person still approves
every proposal.

**Prompts version `roles-v2` calibrates blocking questions.** The analyst is told to mark a
question blocking only when a competent engineer could not begin without the answer (scope,
access, personal data or money, legal obligations, irreversible effects) and to record lesser
gaps as non-blocking questions. The decomposer marks a criterion as needing a human decision only
while its blocking question is unanswered. Revisions return the objective unchanged. Receipts
record the prompt version, so results from `roles-v1` and `roles-v2` stay distinguishable.

**Measure on held-out cases.** The change is evaluated on a fresh 20-case set written by a
separate context that saw neither the earlier cases nor any output, so the prompts were not tuned
to the cases they are scored on.

## Results

On the held-out set, routing accuracy rose from 25% to 70%, all 7 ambiguous requests still
stopped, and 8 of 20 requests reached an approvable proposal, against 0 of 16 before. Revisions
were also told to clear a human-decision flag once its blocking questions are answered. Most
answered requests still stop because the revision gate also waits for optional questions; that
rule is left for the owner (backlog R12). See [validation](../validation.md#calibration-on-a-held-out-set).

## Consequences

- Proposals containing reviewed inferences can now reach human approval and publication. The
  inferences remain visible in the specification and the tickets.
- Handoff to Delivery OS is unchanged: only the constrained documentation lane qualifies.
- The calibration is a prompt change, so its effect must be re-measured whenever the model or
  prompts change.
