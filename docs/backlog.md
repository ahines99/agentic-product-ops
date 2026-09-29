# Dependency-ordered implementation backlog

No live Linear tickets were created. IDs below are local planning identifiers. `Done M0` means executable local foundation coverage, not independent, live, or production acceptance. `Partial` distinguishes a schema/simulator from its production service. Dependencies reference earlier entries; work cannot skip its prerequisites merely because a schema exists.

| ID | Work / milestone | Depends on | Status | Acceptance criteria |
| --- | --- | --- | --- | --- |
| B01 | Project/domain naming, M0 | — | Done M0 | Package/CLI use Product Ops name; docs preserve Delivery OS execution boundary. |
| B02 | Strict WorkSpecification, M0 | B01 | Done M0 | Unknown fields/coercion rejected; version, IDs, nested immutable records and JSON round trip tested. |
| B03 | Canonical digest, M0 | B02 | Done M0 | Stable canonical vectors; changed content/revision invalidates digest; self-field excluded only. |
| B04 | Intake source model, M0 | B03 | Done M0 | Exact UTF-8 source digest and immutable intake validated; incorrect source rejected. |
| B05 | Requirements provenance, M0 | B04 | Done M0 | Provenance-specific refs validated; exact source excerpts; fabricated refs rejected. |
| B06 | Unresolved questions, M0 | B05 | Done M0 | Complete answer/actor/time tuple required; blockers hold; confidence never overrides decision. |
| B07 | Risk policy, M0/M1 | B06 | Partial | M0 lexical floor and tier gates tested; M1 adjudicated semantic risk cases cannot underclassify sensitive work. |
| B08 | Lifecycle, M0/M1 | B07 | Partial | M0 graph/guards/cancellation tested; production durable history and authenticated command transitions added. |
| B09 | Approval contract, M0/M1 | B03, B08 | Partial | M0 exact ID/revision/digest/plan/scope/expiry/count checked; authenticated identity and revocation receipts required. |
| B10 | Audit schema, M0/M1 | B09 | Partial | Trace/intake/spec/workflow/operation refs defined; append-only durable writer, redaction and query tests added. |
| B11 | Provider-neutral model interface, M1 | B10 | Planned | Strict role input/output; fake provider; budget/outage fail without provider mutations. |
| B12 | Requirements-analysis prompt contract, M1 | B11 | Planned | Trusted policy/config separate from source; citations and unresolved choices preserved on frozen cases. |
| B13 | Independent review prompt contract, M1 | B12 | Planned | Distinct context receives all evidence; cannot edit/publish; blocking unsupported findings preserved. |
| B14 | Model cost/usage receipts, M1 | B11 | Planned | Provider usage separate from decimal estimated cost; config versions and request IDs retained; no hidden reasoning. |
| B15 | Evaluation fixture format, M0 | B05, B06 | Done M0 | Strict source/category/expectation/authorship schema and digest verification exercised. |
| B16 | First 15 authored cases, M0/M1 | B15 | Partial | 15 same-context M0 routing cases exist; independently authored semantic gold cases required before M1 exit. |
| B17 | Corpus freeze/report preservation, M0 | B16 | Done M0 | Digest detects corpus change; report writer refuses overwrite; first run retained. |
| B18 | Repository snapshot abstraction, M2 | B05, B17 | Partial | Advisory identity/evidence/unknown schema exists; immutable revision pin and content verification required. |
| B19 | Read-only local repository adapter, M2 | B18 | Planned | Bounded allowlisted files; reject path escape/symlinks; no execution/install/writes; omit secrets. |
| B20 | GitHub snapshot adapter, M2 | B19 | Planned | Tenant/repository allowlists, immutable commit identity, bounded authenticated read API and failure tests. |
| B21 | Bounded file search, M2 | B19 | Planned | Byte/file/depth/time limits enforced; exclusions tested; truncation/uncertainty explicit. |
| B22 | Python AST/import mapping, M2 | B21 | Planned | Parse bytes without import/exec; discover tests/routes where static; dynamic edges marked unknown. |
| B23 | Repository-injection regressions, M0/M2 | B18 | Partial | Synthetic evidence policy-inert test exists; malicious actual snapshot fixtures cannot change policy or exfiltrate. |
| B24 | Work decomposition schema/engine, M0/M3 | B02, B13, B22, B23 | Partial | Typed work items exist; distinct decomposition context produces coherent grounded ticket boundaries. |
| B25 | Acceptance traceability, M0/M3 | B24 | Partial | Structural references/coverage validated; independently reviewed criteria have observable evidence and correct provenance. |
| B26 | Dependency validator, M0 | B24 | Done M0 | Unknown/self/duplicate/cyclic edges rejected; local and top-level representations agree. |
| B27 | Duplicate-ticket detector, M0/M3 | B24 | Partial | Normalized same-title detection exists; semantic overlap findings retained and independently evaluated. |
| B28 | LinearPublicationPlan, M0/M3 | B25, B26, B27 | Partial | M0 deterministic plan/digests/bounds tested; native parent/project/relationship semantics validated. |
| B29 | OAuth/app configuration, M4 | B09, B28 | Planned | Authenticated tenant/app identity, least privilege, encrypted token handling, no secrets in model/log context. |
| B30 | Linear API adapter, M4 | B29 | Planned | Explicit tested GraphQL transport; bounded requests; controlled live fixture creates approved objects only. |
| B31 | Team/project/repository/label allowlists, M0/M4 | B28, B29 | Partial | M0 deny-default allowlists; production tenant metadata and per-command rechecks required. |
| B32 | Publication authorization service, M4 | B09, B30, B31 | Partial | Pure approval validator exists; advancing clock, actor auth, cancellation/revocation and transaction budget before each write. |
| B33 | Stable operation keys, M0/M4 | B03, B28 | Partial | Keys and conflict checks in fake; durable unique constraints, leases and concurrent duplicate commands tested. |
| B34 | UNKNOWN reconciliation, M4 | B30, B32, B33 | Partial | Fake reconcile-or-hold exists; real marker/content lookup, provider IDs/timestamps, proven nonexistence or operator hold. |
| B35 | External-write fault tests, M0/M4 | B34 | Partial | In-memory lost response tested; crash/restart, concurrency, partial batches, late response and accepted cancellation tested durably. |
| B36 | Delivery OS handoff schema, M0/M5 | B03, B09, B28 | Partial | Digested simulation contract verified; real provider metadata and trusted issuer/signature policy required. |
| B37 | Cross-repository handoff fixture, M5 | B35, B36 | Planned | Actual Delivery OS consumes exact approved digest in own store, rejects bad tier/unknowns, invalidates stale revisions. |
| B38 | 40+ corpus and evaluation, M6 | B13, B14, B17, B24, B37 | Planned | At least 40 separately authored cases across all ten categories; failures, gold annotations, configs and denominators preserved. |
| B39 | Evaluation report generator, M0/M6 | B17, B38 | Partial | M0 routing report exists; M6 precision/recall, false resolution, quality, reliability, cost/latency and stratification reproducible. |
| B40 | Portfolio release documentation, M6 | B39 | Planned | Public realistic end-to-end case study, limitations, tagged release; claims trace to measured evidence only. |

## Infrastructure prerequisites inserted before M1 service completion

These are concrete runtime tasks omitted from the initial numbered list but required by the specified architecture. B11–B14 may be developed offline, but M1 service acceptance depends on I01–I04.

| ID | Task | Depends on | Acceptance criteria |
| --- | --- | --- | --- |
| I01 | FastAPI command ingress/authentication | B02–B10 | Authenticated actors/tenants; idempotency payload conflicts; no state patch; bounded requests and redacted errors. |
| I02 | PostgreSQL/SQLAlchemy/Alembic | I01 | Immutable revision/approval/audit tables; unique command and operation keys; migrations up/down on real PostgreSQL in CI. |
| I03 | Temporal workflows and cancellation | I02 | Approval wait/restart, bounded revisions, accepted cancellation and timeout survive worker restart; state ownership documented. |
| I04 | Container/local integration stack | I03 | Non-secret Docker/Compose stack starts reproducibly; readiness checks actual dependencies; isolated fault CI is separate from offline CI. |
| I05 | Durable artifact/audit/observability | I02, I03, B14 | Content-addressed immutable bytes, append-only events, trace linkage, redaction, separate wait/model/publication metrics. |

## Milestone exits

M0: package builds, lint/type/test pass, typed offline fixture CLI works without API calls. M1: frozen independently authored requirements/ambiguity corpus, explicit clarifications, preserved unsupported findings, and durable authenticated lifecycle. M2: pinned read-only repository context and injection tests. M3: coherent grounded decomposition with traceable criteria. M4: actual approved Linear creation with durable idempotency/fault evidence. M5: actual exact-digest Delivery OS intake. M6: 40+ evaluations, measured claims, case study, and tagged portfolio release.
