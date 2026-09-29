# Implementation status

Version 0.4.0, 2026-09-29. **Authorized offline initialization and engineering are complete; MVP, M1 semantic acceptance and production/portfolio acceptance are not complete.** See [final validation](v04-validation-record.md), [engineering checklist](offline-completion-plan.md), [ordered backlog](backlog.md), and [remaining external steps](remaining-work.md). Historical M0/0.2/0.3 documents retain evidence for those releases only.

| Area | Executable and exercised | Evidence boundary |
| --- | --- | --- |
| Contracts/policy | Strict immutable WorkSpecification, exact source/provenance, DAG, digest, risk, ambiguity, scope, approval and revision checks | Objective structure is not semantic correctness |
| Analysis/revisions | Distinct analyst/decomposer/reviewer contexts; durable intent/input/output/usage; initial extraction and authenticated additive clarification; bounded review/restart/cancellation | Authored provider responses only; no actual inference |
| Responses adapter | Strict structured output, input-token preflight, bounded transport, usage/cost reservation, refusal/timeout/uncertainty holds | Mock HTTP; no billing or quality evidence |
| Repository context | Allowlisted local AST/static metadata, immutable digest binding, GitHub commit/tree/blob checks, lexical grounding coverage | GitHub mock HTTP; static metadata cannot prove behavior |
| API/authority | Bounded idempotent commands, exact review/plan approval, current grants, JWT verification, durable revocation, key overlap/retirement, cancellation | Ephemeral identities; default deny, ready/publish 503 |
| Persistence | PostgreSQL/Alembic immutable triggers, transactional command/outbox, concurrency controls, optional AES-GCM artifacts and raw-role read expiry | Real local PostgreSQL; no deployment key custody or physical purge |
| Orchestration | Temporal approval waits, revision workflows, stored receipt verification, restart/replay and cancellation | Real local development Temporal; no automatic live publication |
| Linear | OAuth PKCE/single-use state/encrypted secrets, scoped native issues/dependencies, per-dispatch authority and durable reconciliation | Mock transport only; no live tickets or provider guarantees |
| Handoff | Signed public v2 envelope and independent reference consumer preserving original bytes, rejecting stale/unsafe input | Separate SQLite reference store; actual Delivery OS unchanged |
| Operations | Redacted bounded metadata/metrics, pinned containers, isolated backup/restore with trigger and row-fingerprint checks | Local development evidence; no production traces/SLOs |
| Evaluation | 15/45-case routing evidence; frozen semantic contracts, all-attempt adjudication, denominators/category scoring and reviewer attestations | Same-context examples; no independently measured semantic/human value |
| Release checks | Both supported Pythons, lint/format/types, schema/docs/secrets/audit, reproducible builds and isolated wheel smoke | Local only; Actions configured, no Git remote/hosted run |

## Exact limitations

1. CLI draft/roles-demo use authored fixtures; unknown requests hold. General initial extraction exists through configured services but only mock Responses was exercised. New general intake remains tier 3, with security approval requirements and no tier-0/1 handoff promotion.
2. No live model call or spending occurred. Token preflight and provider-reported usage are transport-tested, not verified against actual billing. Configured prices yield estimates. Missing role/token exchange completion evidence holds; no operator-resolution HTTP endpoint or blind automatic retry exists.
3. Local context contains bounded static symbols/imports/tests and file digests, not complete semantics. Lexical risk/relevance checks can miss paraphrases. Secret heuristics are not complete DLP and filesystem checks are not an OS sandbox. GitHub commit/tree association relies on trusted TLS/provider metadata, not independent signed-commit verification.
4. Production identity/login, tenant provisioning, deployment keys, scopes, TLS and rate/concurrency controls are unconfigured. Authority methods are an operator control-plane library, not a public administration UI/API. Ephemeral token/key tests cannot establish real human approval.
5. Default HTTP ingress denies identities, readiness remains false and publication returns 503. Revision/model service components and native publisher are not assembled into an enabled production write workflow. Calls already dispatched can finish after cancellation; future dispatches are denied.
6. Linear metadata/mutation/reconciliation behavior is tested with mock HTTP only. Actual normalization, permissions, rate limits and outages remain unverified. Relations need `write`; narrower issue-create permission alone is insufficient. No epic/project creation, parent hierarchy, webhooks, republish generation policy or semantic duplicate detector exists. UNKNOWN absence remains held, never blindly recreated.
7. Signed v2 acceptance requires explicitly pinned issuer/key/audience and expected digest. The separate reference consumer is not installed in Delivery OS and cannot invalidate actual downstream execution plans. No sibling source was changed or executed. Legacy v1 remains unsigned simulation.
8. Storage encryption is explicit and optional. Legacy plaintext migration, external key custody/recovery, physical purge and legal retention are deployment work. Raw request/response read expiry retains ciphertext. Commands/outbox/audit metadata require database protection; manifests and metrics reject workspaces above their 10,000-row bound. No production collector or measured human-wait latency exists.
9. PostgreSQL/Temporal/container/restore checks used disposable development services. No production cluster, restore objective, incident exercise, deployed service or cross-version workflow replay was accepted. Hosted CI could not run without a remote; the configured Actions workflow is not a hosted result.
10. No independent 40+ semantic corpus, actual-model indirect-injection evaluation, real human usefulness/editing-time study, or live integration acceptance exists. Reviewer signatures authenticate attestations, not truth. The semantic report always leaves MVP completion false. Green tests and authored case counts cannot close these gates.
11. Legacy CLI multi-file demo export is exclusive-create but not an atomic directory transaction; a partial failed export must be retained or rerun into a new directory. TestClient emits one unsuppressed upstream deprecation warning. Docker reported missing Git provenance metadata under WSL; this did not affect image build/probe and is not claimed as image attestation.

## Next milestone

M1 semantic/service acceptance: choose deployed identity/trust configuration, freeze independently authored/adjudicated requirements and ambiguity cases, and authorize an explicit model/budget run through the implemented durable path. Preserve first failures, held ambiguities and actual receipts. M4 live Linear and M5 actual Delivery OS remain separate gates; credential discovery does not authorize them.
