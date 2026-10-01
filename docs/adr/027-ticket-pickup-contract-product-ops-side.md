# ADR-027: Ticket pickup contract, Product Ops side

Status: accepted, 2026-10-01. Implements the Product Ops items PO-1 to PO-8 in the
[roadmap](../roadmap.md). Amended by [ADR-028](028-pull-handoff-contract-with-delivery-os.md):
the ticket reference, handoff path, response codes and progress source changed to match Delivery
OS's pull contract.

## Context

Delivery OS's own Linear monitor claimed PER-16 and PER-17 from the shared team and assumed the
wrong repository. The roadmap defines a pickup contract both systems implement. This records the
Product Ops half and the console, budget and policy changes that came with it.

## Decisions

**Ticket format v2 (`pilot-execution-v2`, PO-1).** Every published description starts with
`Repository: <name>` and `Product-Ops-Specification: <content digest>`. The name comes from the
operator's recorded repository selection, never from model text, and is omitted if it is not a
plain name. Markdown is escaped before HTML, so apostrophes are no longer sent as a broken entity
(backlog R14). Version 1 renders byte-for-byte as before, so earlier approvals still match. Delivery
OS already skips tickets naming a repository it does not own, so this line alone stops the PER-16
kind of pickup for other repositories.

**`delivery-ready` label (PO-2).** A plan adds the label only when the handoff policy allows the
specification's risk tier and the trusted scope binds the label. It is therefore part of the exact
plan a person approves. `product-ops-pilot delivery-label` finds or creates the team label with a
fixed identity, through the single write gate, and binds it.

**Publishing from the console (PO-3).** When the profile enables publication, a browser session
may call `publish` and `reconcile`. The page offers Publish only for an approved plan, asks for
confirmation, and offers a read-only Linear check instead of a retry after an uncertain write. The
server rechecks every gate. Risk changes and session minting stay out of the browser. This reverses
ADR-020's rule that the browser cannot publish, at the owner's request.

**Signed handoff by specification digest (PO-4).** A completed publication indexes the content
digest named in its tickets. `GET /v1/handoffs/specification/{digest}` returns the signed handoff
for that digest to a separate read-only credential (`handoff-reader-init`), which can do nothing
else. It refuses a superseded specification, and export rechecks tier, publication and approval.

**Delivery progress (PO-5).** For published work, `state` adds progress read from Linear: status
type and a `delivery-blocked` label that Delivery OS applies when it stops (roadmap DO-4). It is
labelled `grants_authority: false` and never changes Product Ops records.

**Ticket splitting and domain terms (PO-6).** Prompt version `roles-v4` asks for the fewest
independently shippable tickets and treats unfamiliar domain terms by their ordinary industry
meaning. Results are in [validation](../validation.md).

**Low-risk code handoff switch (PO-7).** `low_risk_code_handoff` (default off) selects a policy in
which a model proposal matching no risk term has floor 1 instead of 2. Nothing is lowered
automatically; a security approver must still reassess a specific request to tier 1 with a fresh
review and approval. Turning it on is the owner's decision.

**Per-request allowance (PO-8).** `request_maximum_spend` checks each model call against the
allowance of the specification it spends for, before it is sent. Exhausting it holds that request
only. The aggregate cap and authorization terms are unchanged.

## Consequences

- Until Delivery OS implements DO-1 and DO-2, its monitor still claims eligible tickets that name
  no repository or its own repository.
- The handoff credential must be given to Delivery OS out of band (it is in the profile's
  `handoff-reader.env`); Delivery OS must also pin Product Ops' signing key.
