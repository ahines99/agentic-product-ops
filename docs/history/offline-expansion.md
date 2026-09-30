# Offline service expansion: commands and validation

Historical release evidence; current capability and commands are in [0.4 validation](v04-validation-record.md).

Version 0.2.0, 2026-09-28. See [implementation status](implementation-status-v0.6.md) for capabilities and exact limitations, and [remaining steps](remaining-work.md) for the path to MVP/release. No live credentials, Linear objects, paid model calls, UI or Delivery OS persistence changes were made.

## Setup and default checks

Run from the repository in PowerShell or a shell with Python available:

```sh
python -m pip install uv==0.12.18
python -m uv sync --locked --python 3.12
python -m uv run python scripts/verify.py
```

The full verifier checks lock consistency, Ruff lint/format, strict mypy, tests, local documentation links, secret scanning, unchanged generated fixtures/schemas/corpora, two byte-identical wheel/sdist builds, clean-wheel installation outside the checkout and a locked dependency vulnerability audit. Installation and audit use public registries. Application demos make no provider network requests.

For a separate Python 3.13 environment in PowerShell:

```powershell
$env:UV_PROJECT_ENVIRONMENT = '.venv-313'
python -m uv sync --locked --python 3.13
python -m uv run --python 3.13 python scripts/verify.py
Remove-Item Env:UV_PROJECT_ENVIRONMENT
```

## Demos

```sh
python -m uv run product-ops draft --input examples/feature-request.md
python -m uv run product-ops draft --input examples/ambiguous-request.md
python -m uv run product-ops roles-demo --input examples/feature-request.md
python -m uv run product-ops roles-demo --input examples/ambiguous-request.md
python -m uv run product-ops inspect-repository --root . --repository-id product-ops
python -m uv run product-ops roles-demo --input examples/feature-request.md --repository-root . --repository-id product-ops
python -m uv run product-ops demo --output out/demo-v02-1
python -m uv run product-ops verify-handoff --input out/demo-v02-1/handoff.simulated.json
python -m uv run python scripts/evaluate.py --corpus evals/fixtures/m1-routing-corpus.json --output out/routing-v02-1.json
```

Ambiguous/unknown requests intentionally exit 2 and remain held. `roles-demo` runs authored recordings, not inference. `inspect-repository` returns a bounded metadata snapshot and accepts `--expected-digest` to reject changed content. Use new demo/report output paths on repeat runs; existing evidence is not overwritten. Corpus results measure routing only.

To exercise deny-all HTTP startup (not a ready deployment):

```sh
python -m uv run uvicorn agentic_product_ops.api.app:create_app --factory --host 127.0.0.1 --port 18000
```

Health returns 200; readiness returns 503; commands without configured test identity return 401. The application has no UI and publication remains disabled.

## Explicit local runtime tests

Use a disposable PostgreSQL database whose name starts `product_ops_test`, on loopback only. Tests migrate/downgrade its schema; do not point them at valuable data. With a PostgreSQL test server on port 18432 and a separately installed Temporal CLI:

```powershell
$env:PRODUCT_OPS_TEST_DATABASE_URL = 'postgresql+psycopg://postgres@127.0.0.1:18432/product_ops_test'
python -m uv run pytest tests/runtime/test_postgres.py --no-cov -q
python -m uv run python scripts/runtime_checks.py --temporal-cli out/tools/temporal/temporal.exe
Remove-Item Env:PRODUCT_OPS_TEST_DATABASE_URL
```

The helper starts a temporary loopback Temporal server, runs restart/replay/expiry/cancel tests plus connected API/PostgreSQL/outbox/approval tests, then stops its server. Supply the path appropriate to your OS; CI uses `out/temporal-cli/temporal`. The PostgreSQL server is operator-managed. Default tests skip four runtime cases when environment variables are absent.

Local validation used PostgreSQL 17.11 obtained from the [official Windows distribution page](https://www.postgresql.org/download/windows/) and [EDB archive](https://sbp.enterprisedb.com/getfile.jsp?fileid=1260569), plus [Temporal CLI 1.9.1](https://github.com/temporalio/cli/releases/tag/v1.9.1), reporting server 1.32.0. Downloaded Temporal bytes were checked against its published SHA-256 checksum before execution. PostgreSQL used ephemeral loopback trust authentication; this is not production configuration. Only owned test infrastructure was run, never inspected repository code.

Docker/Compose provides optional development definitions with loopback published ports and a deny-all API. It was not executed locally because Docker was unavailable. Hosted GitHub Actions is defined, including PostgreSQL migrations and checksum-verified Temporal runtime tests, but no hosted run is claimed.

## Validation record

Both full verification runs passed on Windows with CPython 3.12.10 and 3.13.15 and the checked-in lock:

| Check | Result |
| --- | --- |
| Default pytest suite | 109 passed, 4 explicitly skipped on each Python version; combined statement/branch coverage rounded to 83% |
| PostgreSQL runtime | 1 passed on PostgreSQL 17.11: migration up/down/up, schema comparison, immutable triggers, concurrent commands and fake publication |
| Temporal runtime helper | 3 passed: worker restart/history replay, forged-signal expiry/cancellation, connected test API/PostgreSQL/outbox approval and lost acknowledgement recovery |
| Lint / formatting / strict typing | Pass; mypy checked 43 source/script files |
| Lock / generated artifacts | Consistent lock; fixtures, schemas and both routing corpora regenerate without byte changes |
| Reproducible packaging | Repeated wheel and sdist builds byte-identical with fixed SOURCE_DATE_EPOCH |
| Clean wheel | Fresh external venv on both Python versions; draft, recorded roles, actual local snapshot context, fake demo and handoff verification pass |
| Docs / secrets | 24 Markdown documents checked; 114 repository files scanned with default secret detectors |
| Dependency audit | No known vulnerabilities reported for exported locked dependencies |
| Routing corpus | Original 15/15 and expanded 45/45 expected routes, zero inference calls; same-context authorship |
| Hosted CI / Docker / live providers | Not exercised; no claim made |

Temporary PostgreSQL and Temporal servers started for this pass were stopped after verification. The developer helper also starts/stops its own Temporal server. Ignored local tools, test data and environments are retained, and no live credentials were written.

Coverage describes exercised code, not product completeness. A Starlette warning about its httpx TestClient compatibility is visible and unsuppressed; migrating that test transport remains a maintenance item. The Python 3.13 command explicitly specifies `--python 3.13` because the repository's default `.python-version` is 3.12; interpreter versions were checked in the final test and wheel logs.

Development failures included a deferred-annotation/closure dependency issue in FastAPI (fixed and exercised), formatter findings, a test canary assignment detected as a secret (renamed without weakening detectors), and a PowerShell byte/string mismatch reading published checksums (decoded and verified before execution). Those are engineering failures, not hidden model-evaluation failures. The original 15-case report and the new 45-case first report remain preserved; neither is independent semantic evidence.
