# ADR-009: Durable recorded analysis, cancellation and pinned identity verification

Status: accepted, 2026-09-29. Extends ADR-007 without enabling live providers.

## Context

Version 0.2 had separate role orchestration and approval workflows. An ingress approval could be recorded without durable role-review evidence, clarification stopped without queued reanalysis, and identity was testing-only. The user authorized continued offline engineering; this does not authorize paid inference or live publication.

## Decision

Connect the scripted analyst/decomposer/reviewer runner to Temporal's preparation activity. Persist intent before each role execution and retain its exact request, validated response, output, usage/cost receipt and audit metadata. Bind cache keys to specification, policy, role, schema, prompt, model and budget. Reuse completed steps with their original context/receipt; hold incomplete intents without invoking a provider again. There is no operator-resolution endpoint yet.

Require exact-spec persisted proposal/review evidence before API approval and workflow decision acceptance. A clarification creates an immutable revision and a revision-specific outbox start, with a cap of ten answers/revisions. Scripted reanalysis cannot invent the semantics of an answer; ambiguity and unauthenticated-resolution gates remain intact. This is durable resumption, not completed semantic clarification.

Serialize approval, clarification, cancellation and publication reservation using the specification control row. API cancellation persists control, receipt, audit and signal job atomically. Future role/publication reservations fail; already committed reservations may finish. Historical approved workflow results remain immutable even if subsequent cancellation disables their use.

Implement optional RS256 token verification with explicitly configured pinned RSA public keys, exact issuer/audience, required short-lived claims, server-owned subject/role mapping and a mandatory fail-closed revocation callback. Ignore role/tenant claims as authority; reject remote-key headers and all other algorithms. No discovery or token URL fetch occurs. Default authentication stays deny-all. Tests create private keys only in memory. Validation follows the [PyJWT API](https://pyjwt.readthedocs.io/en/latest/api.html); no live identity system is configured.

## Consequences

Offline tests can exercise durable analysis, premature-approval denial, revision reanalysis, cancellation and signed-token attacks. Live inference, independent semantic review, human validation, production key rotation/revocation, Linear and Delivery OS remain unverified. Source/model artifacts now need a production data-retention/access policy separate from metadata-only audit logs. A token revocation callback does not revoke past approval receipts automatically; cancellation currently provides explicit specification-wide invalidation.
