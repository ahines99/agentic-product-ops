# Historical version 0.2 validation record

Preserved from commit `09301145b36d7cccbd59f2449b8e1056dffb1e06`. This describes 0.2; see [current status](implementation-status.md) for later work.

Updated 2026-09-28, version 0.2.0. M0 foundation plus an offline service expansion. **MVP, M1 exit, and portfolio release are not complete.** The original [M0 validation record](m0-validation-record.md) is historical; this document is authoritative for the current tree.

## Executable capabilities and evidence

| Area | Implemented and exercised | Boundary |
| --- | --- | --- |
| Domain and policy | Strict immutable WorkSpecification, provenance, DAG, risk, ambiguity, approval, digest and scope checks | Objective constraints cannot prove semantic truth |
| Three model roles | Provider-neutral interface, separate contexts, strict structured results, findings, usage/cost receipts, cancellation and budget guards | Scripted recordings only; no actual inference or spend |
| Repository context | Bounded local reader, AST metadata/search, snapshot digest pinning, secret/injection fixtures | Read-only working tree; metadata is advisory, not semantic grounding |
| GitHub | Commit/blob identity and bounded mock API reads | MockTransport only; no live GitHub reads or authentication |
| API | Bounded FastAPI commands, server-assigned identity, tenant scope, idempotency, immutable clarifications and decisions | Explicit test identity only; default denies all; readiness and publication return 503 |
| PostgreSQL | SQLAlchemy/Alembic, immutable artifact/command/audit triggers, unique command keys, transactional outbox | Real PostgreSQL 17.11 local tests; no production deployment |
| Temporal | Durable approval wait, receipt verification, worker restart, history replay, expiry, cancellation and outbox recovery | Real local Temporal; model/revision/publication activities not connected |
| Publication | In-memory demo plus durable simulation, reservation-before-dispatch, advancing clock, restart reconciliation, cancellation | Fake Linear only; GraphQL adapter rejects real network transports |
| Handoff | Versioned exact-spec artifact, nested digests, approval binding and tier gate | Unsigned simulation; no actual Delivery OS consumer |
| Evaluation | Original 15-case report retained; expanded 45-case frozen routing report | Same-context authoring, zero model calls; not independent semantic evaluation |
| Packaging/CI | Lock, lint, formatting, strict typing, tests, docs, secret/audit checks, reproducible builds, clean-wheel smoke | Local evidence only; hosted Actions and Docker not exercised |

Current validation commands and local infrastructure evidence are in [offline expansion](offline-expansion.md). An entirely green suite does not satisfy milestone exits in the [ordered backlog](backlog.md).

Final local result: 109 default tests passed on each of Python 3.12.10 and 3.13.15, with four explicit service-test skips. All four service tests passed separately against local PostgreSQL/Temporal on Python 3.12. Lock, lint, formatting, typing, docs, secrets, dependency audit, reproducible builds and clean-wheel checks passed. Hosted CI and Docker were not run. TestClient emits one known unsuppressed deprecation warning.

## Exact known limitations

1. General natural-language extraction is absent. The CLI uses authored fixture responses; unknown requests stop for clarification. Separate role contexts are implemented but do not establish independently authored reasoning or semantic quality.
2. Model budgets reserve a conservative local estimate; they are not measured billing. There is no live provider adapter, provider tokenizer, live timeout policy, or automatic persistence of role receipts through Temporal. No model/API money was spent.
3. Local snapshots expose static names/imports/tests and file digests, not raw document/configuration bodies. Relevance and dynamic call edges remain unknown. Secret detection is heuristic; path/file checks are not a hostile-filesystem sandbox. GitHub has a mock-only adapter.
4. API authentication is a test implementation and default-deny boundary. No OIDC/OAuth, production credential management, tenant provisioning, or real human identity verification exists. Publish stays disabled even after test approval; readiness deliberately reports incomplete integration.
5. Clarification creates an immutable new revision and requires reanalysis; it never automatically clears the approval gate. The Temporal workflow handles proposal holds and approval decisions, not the complete target state graph, resumed clarification loop, model activities, publication, or handoff activities. HTTP cancellation/revocation endpoints are not implemented.
6. PostgreSQL owns records; Temporal owns workflow history. SQLite is explicitly a test double. Runtime tests use a disposable loopback PostgreSQL and local Temporal development server, not a production cluster. Docker/Compose is provided but untested here; image tags are pinned, image digests are not.
7. Durable publication is simulation-only. UNKNOWN survives restart and cannot blindly recreate; cancellation stops future reservations but cannot roll back an already reserved in-flight call. No OAuth, live reconciliation, native Linear dependency/project mapping, provider-wide exactly-once guarantee, or webhook service exists.
8. Handoffs are unsigned offline artifacts. Hashes do not authenticate their issuer. Read-only inspection of the adjacent Delivery OS public model found no digest-verifying intake; no sibling code was imported, executed, or modified. See [ADR-008](adr/008-delivery-consumer-compatibility.md).
9. Forty-five routing cases do not satisfy the separately authored 40+ semantic release corpus. Requirements quality, false resolution, human usefulness/time savings, paid-model latency/cost, external usage, and production acceptance remain unmeasured.
10. Audit records are durable, bounded metadata; production tracing/export, retention policy, key rotation and real revocation are not implemented. CLI exports are exclusive-create files, not transactional multi-file storage. Risk is a lexical floor; matching references and normalized titles do not prove truth or semantic uniqueness.

## Next milestone

Complete M1 service acceptance: connect persisted role runs and bounded reanalysis to Temporal, add a production identity/provider boundary, and obtain a separately authored adjudicated requirements/ambiguity corpus. Only then evaluate real inference with explicitly authorized credentials/budget. Linear and Delivery OS integration remain separate M4/M5 gates; initialization has not authorized live writes.
