# Implementation status

Updated 2026-09-29, version 0.3.0. Offline foundation plus durable recorded analysis, revision reanalysis, cancellation and a pinned-key identity adapter. **MVP, M1 exit, and portfolio release are not complete.** [M0](m0-validation-record.md) and [0.2](v02-validation-record.md) records are historical; this document is authoritative for the current tree.

## Executable capabilities and evidence

| Area | Implemented and exercised | Boundary |
| --- | --- | --- |
| Domain and policy | Strict immutable WorkSpecification, provenance, DAG, risk, ambiguity, approval, digest and scope checks | Objective constraints cannot prove semantic truth |
| Three model roles | Provider-neutral interface, distinct contexts, structured results/findings, durable intents/requests/responses/usage receipts, cached recovery and uncertainty hold | Scripted recordings only; no actual inference or spend |
| Repository context | Bounded local reader, AST metadata/search, snapshot digest pinning, secret/injection fixtures | Read-only working tree; metadata is advisory, not semantic grounding |
| GitHub | Commit/blob identity and bounded mock API reads | MockTransport only; no live GitHub reads or authentication |
| API | Bounded commands, tenant scope, idempotency, immutable decisions, persisted-review prerequisite, revision reanalysis and cancellation | Default denies all; readiness and publication return 503 |
| Identity | Pinned RSA signed-token verification, issuer/audience/time/key checks, server-owned subject/role mapping, fail-closed revocation callback | Ephemeral test signatures only; no deployed identity provider, provisioning or key rotation |
| PostgreSQL | SQLAlchemy/Alembic, immutable artifact/command/audit triggers, unique command keys, transactional outbox | Real PostgreSQL 17.11 local tests; no production deployment |
| Temporal | Durable recorded analysis, approval wait, receipt verification, worker restart/replay, API cancellation and revision-specific reanalysis through outbox | Real local Temporal; semantic revision and live publication/handoff remain absent |
| Publication | In-memory demo plus durable simulation, reservation-before-dispatch, advancing clock, restart reconciliation, cancellation | Fake Linear only; GraphQL adapter rejects real network transports |
| Handoff | Versioned exact-spec artifact, nested digests, approval binding and tier gate | Unsigned simulation; no actual Delivery OS consumer |
| Evaluation | Original 15-case report retained; expanded 45-case frozen routing report | Same-context authoring, zero model calls; not independent semantic evaluation |
| Packaging/CI | Lock, lint, formatting, strict typing, tests, docs, secret/audit checks, reproducible builds, clean-wheel smoke | Local evidence only; hosted Actions and Docker not exercised |

Current validation commands and local infrastructure evidence are in [offline expansion](offline-expansion.md). An entirely green suite does not satisfy milestone exits in the [ordered backlog](backlog.md).

Version 0.3 passed 130 default tests on each supported Python version (3.12.10 and 3.13.15), plus all four separately enabled local PostgreSQL/Temporal service tests on Python 3.12. Lock, lint, formatting, typing, docs, secrets, dependency audit, reproducible builds and clean-wheel smoke passed. Evidence and exact commands are in [durable governance](durable-governance.md). Hosted CI and Docker have not been run. TestClient emits one known unsuppressed deprecation warning.

## Exact known limitations

1. General natural-language extraction is absent. The CLI uses authored fixture responses; unknown requests stop for clarification. Separate role contexts are implemented but do not establish independently authored reasoning or semantic quality.
2. Model budgets reserve a conservative local estimate, not measured billing. Role receipts now persist through the Temporal preparation activity; there is no live provider, provider tokenizer or live retry/billing policy. An intent without a completed result holds for operator resolution. No automatic paid retry or operator-resolution endpoint exists.
3. Local snapshots expose static names/imports/tests and file digests, not raw document/configuration bodies. Relevance and dynamic call edges remain unknown. Secret detection is heuristic; path/file checks are not a hostile-filesystem sandbox. GitHub has a mock-only adapter.
4. Signed-token verification is implemented using pinned public keys and server-controlled grants, but only locally generated test tokens have been exercised. OIDC discovery/login, key rotation, real tenant provisioning, production revocation storage and deployed human identity remain absent. Identity-token revocation does not automatically invalidate previously issued approval receipts; specification cancellation is the current explicit invalidation control. Publish/readiness remain disabled.
5. Clarification creates an immutable revision and queues reanalysis, with ten clarification revisions allowed. Authored recordings retain blockers rather than interpreting new answers or creating new acceptance criteria. Fully semantic clarification/review loops are not implemented. Cancellation has an authenticated API command and durable control shared with role/publication reservation; calls reserved before cancellation can finish. The full target workflow still lacks live publication/handoff activities.
6. PostgreSQL owns records; Temporal owns workflow history. SQLite is explicitly a test double. Runtime tests use a disposable loopback PostgreSQL and local Temporal development server, not a production cluster. Docker/Compose is provided but untested here; image tags are pinned, image digests are not.
7. Durable publication is simulation-only. UNKNOWN survives restart and cannot blindly recreate; cancellation stops future reservations but cannot roll back an already reserved in-flight call. No OAuth, live reconciliation, native Linear dependency/project mapping, provider-wide exactly-once guarantee, or webhook service exists.
8. Handoffs are unsigned offline artifacts. Hashes do not authenticate their issuer. Read-only inspection of the adjacent Delivery OS public model found no digest-verifying intake; no sibling code was imported, executed, or modified. See [ADR-008](adr/008-delivery-consumer-compatibility.md).
9. Forty-five routing cases do not satisfy the separately authored 40+ semantic release corpus. Requirements quality, false resolution, human usefulness/time savings, paid-model latency/cost, external usage, and production acceptance remain unmeasured.
10. Audit records contain bounded metadata; immutable role artifacts also retain source/output data and need production access/retention/encryption policy. Production tracing/export and deployment key management are absent. CLI exports are exclusive-create files, not transactional multi-file storage. Risk remains a lexical floor. Activity database/recording work is synchronous inside the preparation activity; live inference needs a nonblocking execution strategy. Cross-version workflow replay has not been tested.

## Next milestone

Complete M1 semantic/service acceptance: implement evaluated clarification-to-requirement revision, a real provider boundary and deployed identity/revocation configuration, then use a separately authored adjudicated corpus with explicitly authorized model credentials/budget. Recorded orchestration and identity-verification components now exist; they do not establish semantic quality or real human identity. Linear/Delivery OS remain separate M4/M5 gates.
