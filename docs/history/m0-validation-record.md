# Historical M0 validation record

Preserved from commit `527459ec9110f3306e27f8179ca48b4929f248b8`. This describes version 0.1.0; see [current implementation status](implementation-status-v0.6.md) for subsequent changes.

Status: M0 offline foundation. Updated 2026-09-28. MVP and portfolio release are **not complete**.

## Executable today

- Strict version-1 WorkSpecification, intake, source/provenance, unresolved question, assumption, repository evidence, risk, acceptance criteria, work item, approval, audit, plan, operation evidence, and handoff contracts.
- Immutable nested values, source/content/plan/request/artifact digests, exact source excerpts, references, coverage, scope, and DAG validation.
- Conservative lexical risk floor, material ambiguity and inferred-behavior gates, duplicate-title checks, deterministic lifecycle transitions with unavailable authenticated paths denied.
- Content-bound approval validation with actor/scope/policy/time/count checks using explicit simulated identity and clock.
- `draft`, `validate`, `demo`, and `verify-handoff` CLI commands; exact fixture lookup and clarification fallback.
- In-memory fake publication with stable operation keys, duplicate suppression, request-digest conflict detection, lost-response UNKNOWN/reconciliation, and cancellation.
- Versioned, digested offline handoff and exact-spec verification; default risk-tier restriction.
- Frozen 15-case routing corpus, preserved first report, adversarial/contract/integration tests, reproducible fixture/schema generation, CI definitions and developer checks.

## Evidence categories

| Category | Status |
| --- | --- |
| Implemented | Offline foundation listed above |
| Tested locally | See local validation record below |
| Hosted GitHub Actions | Configured; not run or claimed |
| Real PostgreSQL/Temporal | Not implemented or tested |
| Live Linear | No credentials, API calls, or tickets created |
| Live model | No calls or spend; fixture routing only |
| Real repository grounding | No reader or repository snapshot inspected |
| Actual Delivery OS consumption | Not exercised; only in-repository consumer-format verification |
| External use / independent human validation | None |
| Production accepted | No |

## Local validation record

Final local verification used Windows, CPython 3.12.10 and 3.13.15, and the checked-in uv lock. `python -m uv run python scripts/verify.py` passed on both environments:

| Check | Result |
| --- | --- |
| Lock consistency | Pass; runtime, development and build dependencies locked |
| Ruff lint / formatting | Pass |
| mypy strict | Pass |
| pytest | 78 passed on each Python version; combined statement/branch coverage rounded to 90% |
| Frozen routing evaluation | 15/15 expected outcomes; zero model/provider calls; same-context authorship |
| Fixture/schema/corpus regeneration | Unchanged bytes |
| Repeated package builds | Wheel and sdist each byte-identical across two builds with fixed SOURCE_DATE_EPOCH |
| Clean wheel | Fresh venv outside checkout, locked hashed dependencies, console entry point, valid/ambiguous draft, demo and handoff verification pass on both Python versions |
| Docs links | 19 Markdown documents checked; local targets/anchors pass; external URLs not fetched by checker |
| Secret scan | Pass across all repository-owned nonignored files; default detectors, reviewed digest-line exception, no network verification |
| Dependency audit | No known vulnerabilities reported for exported locked runtime/development/build dependencies |
| Hosted CI | Definition provided for Linux/Python 3.12 and 3.13; no hosted run claimed |

During development, initial failures were missing README build metadata, syntax/format/type errors, overly broad scanner traversal/default worker count, missing uv on PATH for isolated installation, and an unavailable cached Python 3.13 dependency wheel. The final scanner is bounded to repository files and one worker. Smoke setup permits registry downloads of hash-locked dependencies; the application exercises remain offline. Strict literal validation was tightened to reject boolean/integer coercion. The 15-case first evaluation report is preserved unchanged. Development/tooling errors are not represented as model-evaluation failures.

## Exact known limitations

1. The CLI performs no general natural-language analysis. Only three exact source digests match authored fixtures; unknown text stops at clarification. Line-ending and whitespace changes intentionally count as changed input.
2. There is no model provider interface, analyst/decomposer/reviewer execution, independent semantic review, clarification authentication, cost receipt service, or model outage/budget lifecycle.
3. Risk checks are lexical floors with possible false positives and missed paraphrases. Matching source IDs does not prove semantic support; duplicate detection recognizes normalized titles, not semantic overlap.
4. RepositoryContext is a schema and synthetic security test only. No local/GitHub adapter, pinned snapshot verification, AST discovery, retrieval, or secret-safe repository ingestion exists.
5. No FastAPI, authenticated identity, OAuth, database, migrations, Temporal, durable audit, distributed locking, webhooks, or production observability is implemented. Their intended state ownership remains unchanged.
6. Fake publication is single-process in-memory. It loses state on restart and has no concurrency or real provider exactly-once guarantee. The simulation clock does not advance during a batch. Production lifecycle publication transitions are disabled.
7. No real Linear objects, native relationships, project provisioning, or team metadata have been tested. Approved generation is fixed at 1. UNKNOWN never retries creation without proof; operator resolution is planned.
8. Handoff is explicitly offline, digested but unsigned. Hashes do not authenticate a human, issuer, or source. Consumer parsing is within this repository, not Delivery OS; real revision invalidation is planned.
9. CLI demo files use exclusive creation but multi-file export is not transactional or a tamper-proof store. Trusted output paths are operator-selected. File bounds/symlink checks are best-effort local hygiene, not a hostile-filesystem sandbox.
10. Corpus authoring is same-context; 15 routing cases are not the required 40+ independently authored release corpus. Semantic quality, human usefulness/savings, real latency/cost, external use, and production acceptance are unmeasured.
11. Python 3.12 and 3.13 are supported; 3.14 is intentionally excluded pending compatibility checks. Default CI requires dependency downloads/audit network access, but no paid API or credentials.

## Next milestone

M1: provider-neutral structured requirements/ambiguity analysis, separate independent-review context, authenticated clarification and approval receipts, decimal usage/cost accounting, and a frozen separately authored corpus. Add PostgreSQL/Temporal/ingress through I01–I05 before making durable service claims. See [ordered backlog](../backlog.md) for exact acceptance criteria.
