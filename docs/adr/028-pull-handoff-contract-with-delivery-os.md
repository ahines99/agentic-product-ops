# ADR-028: Pull handoff contract with Delivery OS

Status: accepted, 2026-10-01. Answers the four decisions in Delivery OS's
[PR #13](https://github.com/ahines99/agentic-delivery-os/pull/13) and amends ADR-027.

## Context

Delivery OS built DO-1, DO-2 and DO-4 and proposed a pull contract for DO-3, DO-5 and DO-6. Product
Ops had already built PO-4 with a different ticket line, path and error codes, and PO-5 read a
label that Delivery OS does not write. Nothing had been published in the new ticket format, so
Product Ops adopted Delivery OS's proposal.

## Decisions

1. **Ticket reference and retrieval: accepted as proposed.** Tickets that carry `delivery-ready`
   also carry `Handoff: sha256:<64 lowercase hex>`, the approved specification's content digest,
   next to `Repository:`. The ticket never carries a URL. Delivery OS fetches
   `GET {base_url}/handoffs/{digest}` from its configured base URL; for the local profile that is
   `http://127.0.0.1:18013`. The `Product-Ops-Specification:` line and the
   `/v1/handoffs/specification/{digest}` path from ADR-027 are removed; neither was ever published
   or called.
2. **Authentication: a read-only bearer token.** `product-ops-pilot handoff-reader-init` creates
   it in the profile's `handoff-reader.env`. It can fetch handoffs and nothing else. It reaches
   Delivery OS out of band, as an environment variable on that side; Delivery OS also pins Product
   Ops' Ed25519 signing key.
3. **Responses and reasons.**
   - `200`: a freshly signed v2 envelope; the approval inside keeps its original times.
   - `404`: unknown digest, or not yet available (publication incomplete, or outside the handoff
     policy).
   - `410` with header `Reason: superseded`: a newer revision exists.
   - `410` with header `Reason: revoked`: the specification was cancelled, its approval was revoked,
     or the approver's grant is no longer active.
   - `expired` is not returned. Approvals are checked as of the moment each write was dispatched,
     and every response is signed fresh.
   - Held tickets do not need a visible reason. Delivery OS should not claim a ticket only to
     report that it is held; Product Ops' console already shows why a specification is not
     eligible for delivery.
4. **Repository name: the local directory name.** Product Ops writes the name of the folder the
   operator selected (for this repository, `agentic-delivery-engineer`), because it does not know
   GitHub names for local repositories. Delivery OS maps it with `linear_repository_names`.

**Multi-ticket handoffs (DO-5).** The existing envelope already carries what DO-5 asks for: the
specification's work items and dependencies, and a plan whose operations map each work item to its
Linear issue ID. All tickets of one specification share the same `Handoff:` digest.

**Progress (PO-5).** Product Ops now reads Delivery OS's progress comments, marked
`<!-- delivery-progress:<key>:<in_progress|done|blocked> -->` (its ADR-037), taking the newest
marker and showing the recorded reason for a block. Without markers it falls back to the ticket's
status type. The `delivery-blocked` label from ADR-027 is dropped. Progress remains display only.

## Consequences

- DO-3 can start once Delivery OS merges its PR #9 and configures the base URL, token and key.
- Profiles that published under ADR-027's format would need the old line; none did.
