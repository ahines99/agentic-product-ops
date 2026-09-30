# Architecture

The [v0.5 local pilot](local-pilot.md) assembles these components in the same monolith: loopback API, private single-operator identity, PostgreSQL, Temporal, Anthropic structured roles and an explicitly guarded native Linear publisher. Ticket-selected repositories require server and durable-grant opt-in. [ADR-014](adr/014-local-anthropic-pilot.md) records the pilot choices and preserved authority boundary. It does not add a shared Delivery OS store or execution service.

Agentic Product Ops is a modular monolith. Models propose; deterministic code owns lifecycle gates, ambiguity, risk, scope, approval, idempotency and external writes. Product Ops defines approved work. Delivery OS executes it in its own persistence.

```mermaid
flowchart LR
    Source[Untrusted request] --> Roles[Analyst / decomposer / reviewer]
    Repo[Bounded static repository evidence] --> Roles
    Roles --> Gates[Strict contracts and deterministic gates]
    Gates --> Store[Immutable PostgreSQL records and outbox]
    Store --> Temporal[Temporal durable waits and activities]
    Temporal --> Human[Exact specification and plan approval]
    Human --> Publisher[Governed publication service]
    Publisher --> Artifact[Signed public handoff]
    Artifact --> Consumer[Independent reference intake store]
```

These are exercised component connections, not a claim of deployed end-to-end service. The offline CLI runs authored recordings; the configured pilot has exercised Anthropic roles with a bounded live smoke. The Responses adapter remains mock-tested. Native publication is wired to the configured pilot's guarded HTTP handler but has only mock mutation evidence and never runs automatically from Temporal. The reference consumer is not installed in Delivery OS.

The [issue-driven entry point](issue-driven-operation.md) adds read-only Linear lookup and local repository-name resolution. A source snapshot is stored atomically with its initial specification. Paid-disabled intake creates no dispatch; issue edits conflict and block later approval/publication/export. The combined launcher owns API and worker lifetimes. There is no continuous Linear watcher yet; [ADR 015](adr/015-issue-driven-intake.md) defines this boundary.

## Ownership and modules

| Module | Responsibility |
| --- | --- |
| `domain/`, `policies/` | Frozen Pydantic contracts, source/digest/provenance/DAG validation, additive revision rules, risk and approval |
| `adapters/model/`, `services/revisions.py` | Distinct roles, strict structured output, token preflight and cost reservation, bounded reviewed revisions |
| `services/durable_analysis.py` | Intent-before-call, immutable request/response/result/usage, cached recovery, uncertain-call hold |
| `adapters/repository/`, `services/grounding.py` | Inert local AST reads, pinned GitHub metadata, lexical evidence coverage and explicit gaps |
| `api/`, `services/authority.py`, `adapters/identity/` | Authenticated commands, server-owned grants, pinned JWT keys, durable revocation, encrypted OAuth vault |
| `adapters/persistence/` | PostgreSQL records, immutable triggers, control locks, command results and transactional outbox; optional artifact encryption |
| `workflows/` | Temporal history, approval waits, stored-receipt validation, restart/replay, revision outbox and cancellation |
| `adapters/linear/`, `services/native_publication.py` | Scoped native issue/relation plan, OAuth PKCE, exact metadata checks, per-write authority and UNKNOWN reconciliation |
| `services/signed_handoff.py`, `product_ops_handoff/` | Signed public envelope and separately persisted reference intake without producer imports |
| `services/operations.py`, `evaluation/` | Bounded redacted exports, routing evidence and explicitly adjudicated semantic reports |

PostgreSQL owns immutable artifacts and command/operation evidence. Temporal owns durable orchestration history and waits; no second editable lifecycle column can override it. Commands commit outbox and records together. Signals contain stored receipt IDs, never authoritative booleans. Revision-specific workflows cannot approve superseding content. Role/publication reservations and command changes share control locks. Current authority is rechecked after provider metadata reads immediately before native mutation.

## Command surface

Implemented: intake, intake/specification/review/plan reads, repository snapshot reads, clarification, approve, reject and cancel. Commands are bounded, tenant scoped and idempotent. Native approval requires the exact rendered plan digest. Snapshot intake can require the exact inspected digest; arbitrary repository selection additionally requires both policy and durable operator opt-in. The short-name route resolves only configured local roots. Approval additionally requires persisted passing review. Clarification creates new immutable provenance and requires fresh analysis/review.

The factory defaults to deny-all identity and disabled publication/readiness. The pilot supplies private operator identity, guarded publication and heartbeat-based readiness. Publication/handoff GET routes read records if present. No UI or arbitrary state PATCH exists. Production identity and deployed readiness remain external deployment work.

## Untrusted inputs and execution

Repository inspection never imports, runs, installs dependencies from, writes to, or follows URLs embedded in source. Only bounded static metadata enters role context. GitHub pins commit/tree/blob associations and recomputes blob hashes; provider TLS metadata supplies commit-to-tree association, not an independently verified signed commit. Lexical matches do not prove semantic relevance. Local file checks are not an OS sandbox.

Runtime configuration is operator owned. Each role receives a distinct context and trusted policy separate from untrusted JSON. Model output can suggest decomposition, never identity, state, policy or approvals. Two review attempts and a shared call/cost budget bound revisions. Calls with missing completion evidence hold rather than silently repeat billable work. Blocking findings and first failures are retained.

## Operations

Pinned development containers, real PostgreSQL/Temporal integration and isolated backup/restore are exercised. SQLite is an explicit test double, plus the independent reference consumer's own store. AES-GCM protects configured artifact/operation payloads; raw role access expiry preserves immutable ciphertext and audit metadata. Metadata exports separate role and publication duration; no production collector or human-wait instrumentation is claimed. See [status](implementation-status.md), [validation](v04-validation-record.md), and [ADRs](adr/README.md).
