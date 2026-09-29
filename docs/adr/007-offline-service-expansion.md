# ADR-007: Exercise service boundaries without live providers

Status: accepted, 2026-09-28. Extends ADR-001; preserves its modular-monolith and honest-claims decisions.

## Context

After M0 initialization, the user authorized all further work possible without input. PostgreSQL, Temporal and command ingress can be tested locally without credentials or paid APIs. Leaving them as empty interfaces would not exercise persistence, approval waits or crash boundaries. Conversely, a test identity or scripted model must not become a production authorization path.

## Decision

Implement a provider-neutral three-role runner with recorded responses, bounded local repository metadata, test-authenticated FastAPI commands, real PostgreSQL migrations and a real Temporal approval workflow. Production engine selection accepts PostgreSQL; SQLite requires explicit testing mode. PostgreSQL owns immutable artifacts/commands/audits, while Temporal owns workflow history. A transactional outbox bridges committed commands to workflow starts/receipt signals. Stored receipts, not signal text, authorize transitions. One decision per exact revision is immutable.

Ingress defaults to deny-all. Readiness remains 503 and publication is disabled until production identity and complete integration exist. No live model/Linear transport is installed. Mock GraphQL and GitHub adapters require MockTransport. Model outputs cannot replace requirements, unresolved decisions, repository evidence or server policy.

Durable publication remains a simulation harness. A committed UNKNOWN reservation is the dispatch linearization point. Cancellation prevents new reservations; already reserved calls may finish. Failed or lost responses reconcile exact provider content or hold, never blindly recreate. A database crash between reservation and actual dispatch may require operator resolution, because absence from a lookup is insufficient proof.

## Consequences

Local PostgreSQL migration, immutability and concurrency tests and Temporal restart/replay tests support concrete service claims. They do not establish production identity, full lifecycle wiring, live provider reliability, semantic quality or MVP completion. The first M0 evaluation and validation record remain preserved. Containers are supplied but not claimed tested. [Current status](../implementation-status.md) lists unfinished gates.
