# Architecture

Agentic Product Ops is a modular monolith. Models propose; deterministic code controls lifecycle, ambiguity, risk, authorization, team/repository scope, idempotency and writes. Product Ops defines approved work; Delivery OS executes it using its own persistence. [ADR-007](adr/007-offline-service-expansion.md) extends the original [M0 decision](adr/001-offline-foundation.md) with exercised service components.

```mermaid
flowchart LR
    Source[Untrusted request] --> Fixture[Fixture or scripted role runner]
    Repo[Bounded static repository metadata] --> Fixture
    Fixture --> Spec[Strict WorkSpecification]
    Spec --> Gates[Deterministic proposal gates]
    API[Bounded API with test identity] --> PG[PostgreSQL immutable records and outbox]
    Gates --> PG
    PG --> Temporal[Temporal approval wait and receipt validation]
    Spec --> Plan[Exact deterministic publication plan]
    Plan --> Sim[Explicit fake publication harness]
    Sim --> Handoff[Offline versioned handoff]
```

These are executable components, not a claim that every arrow in the target product is connected. In version 0.3 the API still drafts from fixtures, while Temporal's preparation activity runs and persists the three recorded roles before an approval can be accepted. The CLI also exposes an in-memory recorded path. Clarifications queue new revision-specific analysis workflows; unresolved semantics remain held. A deployed human identity provider and live Linear transport are absent; default ingress denies all. The offline handoff remains a separate simulation path. [ADR-009](adr/009-durable-recorded-governance.md) records the new authority boundary.

## Modules and state ownership

| Module | Responsibility |
| --- | --- |
| `domain/contracts.py` | Immutable schemas, canonical digest, traceability and graph validation |
| `policies/validation.py` | Trusted policy, risk floor, ambiguity/review gates, scope and approval binding |
| `adapters/model/` | Strict role contracts, independent contexts, recorded provider, usage/budget receipts |
| `adapters/repository/` | Local static metadata, bounded search, digested snapshots and mock GitHub reader |
| `api/app.py` | Commands, test authentication, idempotency and immutable revisions; default deny |
| `adapters/identity/` | Optional pinned RSA issuer/audience verification with server-owned grants and revocation callback |
| `services/durable_analysis.py` | Immutable role intent/request/response/result/usage evidence, retry reuse and uncertainty hold |
| `adapters/persistence/store.py` | PostgreSQL immutable artifacts, commands, audits, outbox and publication intents |
| `workflows/governance.py` | Temporal approval wait, signal receipt validation, cancellation and timeout |
| `workflows/activities.py` | Database activities and replay-safe outbox dispatch/reconciliation |
| `workflows/lifecycle.py` | Full target graph's pure transition validator; unavailable live transitions denied |
| `services/publication.py` | Durable fake-provider reservation, authorization and reconciliation harness |
| `adapters/linear/` | Canonical plan/rendering, in-memory fake, mock-only GraphQL transport |
| `adapters/artifacts/handoff.py` | Public handoff export and independent deserialization/integrity verification |
| `evaluation/harness.py` | Frozen routing corpus and report identity; no semantic claims |

PostgreSQL stores immutable source/specification/clarification/approval records and audit metadata. Temporal owns durable workflow history and waits; a database row is not a second lifecycle authority. Commands and outbox jobs commit together. Duplicate starts reconcile against workflow identity; decision signals carry only a stored receipt ID, never an authoritative approval boolean. A completed matching receipt query reconciles a lost outbox acknowledgement. Database constraints and PostgreSQL triggers enforce immutability independently of application calls. Reads recheck artifact digests.

Publication intents use unique workspace/operation keys. The simulator reserves UNKNOWN before a fake dispatch, rechecks a trusted advancing clock per operation, and reconciles exact content after uncertainty. It does not invent a real Linear persistence model. Delivery OS imports a future public artifact adapter, never these database classes.

## HTTP surface

Implemented: `POST /v1/intakes`, `GET /v1/intakes/{id}`, `GET /v1/specifications/{id}`, `GET /v1/specifications/{id}/review`, `POST /v1/specifications/{id}/clarifications`, `POST /v1/specifications/{id}/approve`, `POST /v1/specifications/{id}/reject`, `POST /v1/specifications/{id}/cancel`, `/health`, `/ready`. The publish route always denies with 503. Publication/handoff GET routes read tenant-scoped artifacts if present, but no live path populates those records. No arbitrary state PATCH or UI exists.

Approval requires persisted recorded proposal/review evidence for the exact revision/digest and is checked against server scope, role and time. One immutable decision per revision prevents contradictory receipts. Clarification creates a new revision, invalidates old approval and queues reanalysis; ten clarification revisions are allowed. Role/publication reservation and approval/clarification/cancellation share a row lock. Review responses distinguish persisted recorded results from deterministic-only fallback. Errors omit raw input and secrets.

## Repository and model boundary

Repository inspection never imports, executes, installs dependencies, follows source URLs or changes the inspected tree. Allowed local roots, entry/file/byte/depth/time limits, link exclusion, secret heuristics and content digests bound the input. Only static metadata enters the recorded pipeline; its original context cannot be replaced by a decomposer output. Snapshots describe a bounded working tree, not a clean Git commit or a behavioral proof.

Each newly executed role gets a distinct context identifier and role policy separate from untrusted JSON. Strict schemas, immutable requirements/uncertainties, review findings and deterministic gates constrain outputs. Provider usage and decimal estimates are distinct. The only provider is scripted. The durable path persists intent before a role, then exact request/response/result/receipt; retries reuse completed evidence, while missing results hold. Live transport timeouts and paid retry reconciliation remain future work.

## Deployment and observability boundary

Alembic migrations and PostgreSQL/Temporal development services are exercised locally. SQLAlchemy SQLite is available only with explicit testing mode. Docker/Compose definitions are untested templates; the API image starts with deny-all authentication. No live credentials, provider writes or paid model calls are required by default tests or CI.

Durable audits contain bounded metadata, not free-form source/model text. Production trace exporters, separately measured wait/model/publication latency, retention, revocation and full service readiness remain in the backlog. See [implementation status](implementation-status.md) for precise evidence and gaps.
