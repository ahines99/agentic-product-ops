# ADR-008: Keep the handoff contract separate from Delivery OS internals

Status: accepted, 2026-09-28.

## Context

Read-only text inspection of the adjacent `agentic-delivery-engineer` repository found an Agentic Delivery OS public WorkItem model, version 1, with source/title/description/repository/base-branch/type/criteria/ambiguities/risk fields. It does not implement Product Ops WorkSpecification intake with expected approved digest verification. Inspection used Git revision `e00796e4cccc5371efe8603fabe883e1aba77eb4`; the public `src/agentic_delivery/domain/models.py` SHA-256 was `757c0f245aa59fef6c0b23e563ecb56c22530857062414aff5bb539d56f76606`. No sibling code was imported, run or modified.

## Decision

Preserve the independent Product Ops versioned envelope and exact WorkSpecification. Do not relabel an ordinary WorkItem conversion as verified cross-repository consumption, share persistence, or add implementation execution to Product Ops. The current handoff is explicitly offline and unsigned. A future consumer adapter belongs at Delivery OS's public ingress and retains the original approved artifact in its own store.

The adapter must verify schema/mode, trusted issuer/transport, expected digest, exact approval/revision/tenant/provider binding, unresolved-question and consumer risk gates. It must preserve traceability and invalidate stale planning assumptions on a newer revision. Any legacy WorkItem projection follows those checks and keeps the original artifact reference.

## Consequences

M5 remains incomplete. Product Ops's consumer-format test is useful but not actual Delivery OS consumption. This decision preserves the original product boundary and avoids changes to another repository under an initialization request for this one.
