# ADR-025: Only blocking questions look required

Status: accepted by the owner, 2026-09-30.

## Context

The first real request through the prompt console reached an approvable proposal, but the page
listed four optional questions with "Submit answer" buttons. Each said the implementer could
choose a default, yet they looked required, and answering one would have created a new revision
needing fresh analysis and approval.

## Decisions

- The console shows blocking questions under "Answer required before approval". Optional
  questions sit in a collapsed "Optional notes" section that says no answer is needed and that
  answering starts a new revision. They can still be answered.
- Prompt version `roles-v3`: the analyst no longer asks about details an implementer can settle
  (naming, formatting, rounding, minor defaults, edge-case messages) and raises at most two
  non-blocking questions, only for choices that change what users see or can do. The decomposer
  records each chosen default as an assumption naming the value, so it stays visible on the
  proposal.

## Consequences

- Approval is visibly possible whenever no blocking question remains.
- Fewer optional questions is a prompt change and has not been re-measured on a fresh evaluation
  set; the earlier results in [validation](../validation.md) were produced with `roles-v1` and
  `roles-v2`.
