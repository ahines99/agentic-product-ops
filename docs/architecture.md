# Architecture

A modular monolith keeps product authority in deterministic code. Pydantic contracts are the only runtime dependency during M0. Adding unused FastAPI, PostgreSQL, Temporal, containers, or empty adapter directories would imply capabilities that do not exist; [ADR-001](adr/001-offline-foundation.md) defers those runtimes until executable milestones need them.

```mermaid
flowchart LR
    Input[Untrusted intent] --> Draft[Offline fixture router]
    Draft --> Contract[Strict WorkSpecification]
    Contract --> Gates[Risk, ambiguity, scope, review checks]
    Gates --> Plan[Deterministic publication plan]
    Plan --> Approval[Simulated approval validation]
    Approval --> Fake[In-memory fake Linear and fault harness]
    Fake --> Artifact[Versioned digested offline handoff]
```

The diagram shows executable M0 modules, not live infrastructure. Drafting returns an authored proposal or a clarification hold. Objective review checks are not an independent model reviewer. Fake publication and handoff are isolated simulation functions, never network adapters.

## Module responsibilities

| Module | Responsibility |
| --- | --- |
| `domain/contracts.py` | Strict schemas, source integrity, canonical digest, traceability and graph validation |
| `policies/validation.py` | Server policy, risk floor, ambiguity/review gates, scope and approval binding |
| `workflows/lifecycle.py` | Explicit transition graph and pure foundation guards |
| `services/drafting.py` | Exact source digest lookup and fail-closed unknown-input fallback |
| `adapters/linear/offline.py` | Deterministic bounded descriptions, operation identities, fake writes/reconciliation |
| `adapters/artifacts/handoff.py` | Public handoff export and integrity verification |
| `evaluation/harness.py` | Frozen corpus identity and objective routing outcomes |
| `cli.py` | Bounded local file input, JSON output, simulated demo |

## Planned production design

FastAPI receives authenticated commands with idempotency keys; it never accepts arbitrary state patches. PostgreSQL stores immutable intakes, source artifacts, specification revisions, clarification receipts, agent runs, review findings, approvals, publication intent, observed Linear work items, handoff records, and append-only audits. Temporal owns durable lifecycle history, long waits, retries, bounded loops, and cancellation. SQLAlchemy/Alembic own schema/migration discipline. Content-addressed artifact storage holds large evidence bytes. Models propose through strict provider-neutral interfaces in separate analyst, decomposition, and reviewer contexts. No model receives Linear credentials or a mutation capability.

| Concern | Production authority | M0 representation |
| --- | --- | --- |
| Source/specification | PostgreSQL immutable revisions | Packaged JSON fixtures and frozen objects |
| Lifecycle | Temporal history | Pure transition validator |
| Approval | Authenticated PostgreSQL receipt + workflow checks | Explicit simulated identity only |
| Linear issue state | Linear | In-memory fake objects |
| Mutation intent/reconciliation | PostgreSQL | In-memory operation records |
| Repository state | GitHub/source provider | Advisory schema, synthetic security tests only |
| Audit | Append-only PostgreSQL events | Strict schema only |
| Large artifacts | Content-addressed storage | Exclusive-create local demo files |

The simulator is single-process and has no crash, concurrency, lease, or durable recovery guarantee. It is not a replacement persistence model. Delivery OS has its own storage and implementation provenance. It imports the public handoff, not these Python persistence classes.

## Planned HTTP surface

`POST /v1/intakes`, `GET /v1/intakes/{id}`, `POST /v1/specifications/{id}/clarifications`, `GET /v1/specifications/{id}`, `GET /v1/specifications/{id}/review`, `POST /v1/specifications/{id}/approve`, `POST /v1/specifications/{id}/reject`, `POST /v1/specifications/{id}/publish`, `GET /v1/publications/{id}`, `GET /v1/handoffs/{id}`, `GET /health`, and `GET /ready` remain planned. Command idempotency must reject key reuse with different payload digests. No HTTP server is implemented.

## Repository context and observability

M2 pins snapshot identity, bounds file counts/bytes, rejects path escape and symlinks, excludes secrets, and uses read-only tree/AST inspection. No dependency installation, subprocess execution, or URL fetch arises from repository content. Evidence describes likely components, tests, unknown edges, and confidence; it never proves correctness.

AuditEvent includes trace, intake, specification/revision, workflow, agent-run, operation, and provider-request identifiers without free text. Future structured tracing measures intake-to-proposal, clarification wait, model latency/cost, work/requirement/question/finding counts, revision loops, duplicate suppression, stale approvals, and publication outcomes. M0 has structured redacted CLI error output; no telemetry backend or durable audit writer exists. Fixed-precision decimal cost and provider usage must be separate future receipts, with no hidden chain-of-thought.
