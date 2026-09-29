# Durable governance continuation (0.3)

Date: 2026-09-29. Version 0.2's verified expansion was committed as `09301145b36d7cccbd59f2449b8e1056dffb1e06`. This continuation connects recorded analysis to durable approval and adds cancellation plus a pinned-key identity adapter. [ADR-009](adr/009-durable-recorded-governance.md) explains the authority and recovery decisions.

## Executable behavior

1. API intake commits an immutable specification and workflow outbox job. Default identity denies access; tests inject an explicit authenticator.
2. Outbox dispatch starts Temporal. Its preparation activity runs the three authored roles, persists each intent/request/response/result/receipt and retains objective findings. A completed step is reused across activity/worker retries with original evidence. An incomplete intent holds, without blind provider execution.
3. Approval is denied until the exact specification has persisted proposal/review evidence. Trusted policy still checks ambiguity, risk, scope, actor, plan, expiry and mutation count. A signed token or recorded reviewer never bypasses these gates.
4. Clarification writes a new immutable revision and queues a revision-specific workflow. Reanalysis preserves answers and unresolved blockers. Arbitrary answers cannot become invented requirements; the semantic revision engine is still unfinished.
5. `POST /v1/specifications/{id}/cancel` accepts an exact revision/digest plus idempotency key from an authorized approver. It atomically persists cancellation and its outbox signal. Future approvals/clarifications and role/publication reservations fail. An already reserved call may finish; old evidence remains intact.
6. The optional JWT adapter verifies RS256 signatures with pinned public keys, exact issuer/audience, mandatory time/subject/token-ID claims, short lifetime and a required revocation callback. Roles and tenant scope come from trusted subject mapping. No remote key URL is followed; revocation-backend failure denies authentication. Only in-memory test keys/tokens have been exercised.

The API's review endpoint now returns persisted recorded results, including holds, when available. It labels deterministic fallback separately. Publication, readiness and live model calls remain disabled. There is no login UI, OAuth setup, live credential or paid API execution.

## Commands

```sh
python -m uv sync --locked --python 3.12
python -m uv run python scripts/verify.py
python -m uv run pytest tests/integration/test_durable_analysis.py tests/integration/test_api_store.py tests/security/test_identity.py --no-cov -q
python -m uv run product-ops roles-demo --input examples/feature-request.md --repository-root . --repository-id product-ops
```

Use the [runtime setup commands](offline-expansion.md#explicit-local-runtime-tests) with a disposable loopback PostgreSQL database and installed Temporal CLI. The connected test now exercises persisted analysis before approval, premature-approval denial, lost acknowledgement recovery, API cancellation and revision-specific clarification reanalysis. The helper stops its temporary Temporal server. Docker and hosted Actions remain unexercised.

## Validation and remaining boundaries

Both full verifier runs passed on Windows with CPython 3.12.10 and 3.13.15:

| Gate | Local result |
| --- | --- |
| Default suite | 130 passed, 4 explicit runtime skips on each interpreter; combined statement/branch coverage rounded to 82% |
| Real PostgreSQL | 1 passed: migrations/schema/immutability, concurrent commands and fake publication |
| Real Temporal + connected service | 3 passed: restart/replay, expiry/forged signal/cancellation, API-to-PostgreSQL-to-recorded-analysis-to-approval, lost acknowledgement, API cancellation and clarification revision reanalysis |
| Lint, formatting, typing | Pass; strict mypy checked 47 source/script files |
| Lock, fixtures, schemas, corpora | Consistent lock; regeneration unchanged |
| Packaging | Repeated wheel/sdist byte-identical with fixed build timestamp; external clean-wheel smoke passes on both interpreters |
| Docs and secrets | 27 Markdown documents checked; 123 repository files scanned with default secret detectors |
| Dependency audit | No known vulnerabilities reported for exported locked dependencies |
| Hosted CI, Docker, live providers, actual Delivery OS intake | Not exercised |

The four runtime tests were run on Python 3.12 against PostgreSQL 17.11 and Temporal CLI 1.9.1/server 1.32.0. Test servers started for this work were stopped afterward. The Starlette/httpx TestClient deprecation warning remains visible; it is not a failed assertion and is not suppressed. Public package installation/auditing used network access; no model calls or money were spent.

The original 15- and 45-case routing reports remain unchanged; no semantic-quality or independent-authorship claim has been added. See [current status](implementation-status.md) and [remaining steps](remaining-work.md) for exact gaps. In particular, semantic answer-to-requirement revision, live model execution/reconciliation, deployed identity/revocation/key rotation, live Linear, trusted downstream intake and production operations are not complete.
