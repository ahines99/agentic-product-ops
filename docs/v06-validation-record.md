# Version 0.6.0 validation record

Date: 2026-09-30. Branch `feature/finalize-offline-engineering`, built on
`feature/documentation-handoff` (`b7b78f6`). Not merged into `main`, not pushed.

Scope: the recovery and hardening changes in
[ADR-021](adr/021-publication-recovery-and-write-gate.md). No paid model call, no Linear request,
no Delivery OS change and no change to the running pilot services was made.

## Results

| Check | Python 3.12.10 | Python 3.13.15 |
| --- | --- | --- |
| `uv lock --check`, ruff lint and format, strict mypy (95 files) | Pass | Pass |
| pytest (default, no services) | 348 passed, 5 skipped | 348 passed, 5 skipped |
| Docs links (54 documents), schema export, secret scan (233 files) | Pass | Pass |
| Fixture regeneration and two byte-identical builds | Pass | Pass, same hashes |
| Clean-wheel smoke outside the checkout | Pass | Pass |
| `pip-audit` of the locked export | No known vulnerabilities | No known vulnerabilities |

Build hashes: wheel `d51e2ed0be7c9a5809fe1d72cfe7963e8f26ed0b4ea02d4dd151ffc68eb2249f`,
sdist `aeb2cd99d3ce563338d4a2396316dba830359a531cc97361e349e08373ed9a63`.

The five default skips are the service tests. They were run separately on Python 3.12 against a
disposable PostgreSQL 17.11 instance (fresh database, port 18977) and a temporary Temporal dev
server started by `scripts/runtime_checks.py`:

| Service check | Result |
| --- | --- |
| `tests/runtime/test_postgres.py` | 1 passed |
| `scripts/runtime_checks.py` (Temporal, connected API/PostgreSQL/Temporal, revisions) | 16 passed |
| `scripts/backup_restore_check.py` on the populated test database | Restored; immutable trigger verified |

Reusing a test database across runs makes two connected tests fail on leftover rows. That was
already true before this change; use a fresh database name for each run, as earlier records say.

Offline CLI: `draft` on the feature request exits 0, on the ambiguous request exits 2;
`roles-demo`, `demo` and `verify-handoff` exit 0. `product-ops-pilot --help` lists `state`,
`reconcile`, `grant-renew` and `revoke`.

Commands (PowerShell; the service steps need the checkout's `out/tools` binaries):

```powershell
python -m uv sync --locked --python 3.12
python -m uv run python scripts/verify.py
$env:UV_PROJECT_ENVIRONMENT = '.venv-313'
python -m uv sync --locked --python 3.13
python -m uv run --python 3.13 python scripts/verify.py
Remove-Item Env:UV_PROJECT_ENVIRONMENT
# Disposable PostgreSQL on a private port, then a fresh database per run
out/tools/postgres/pgsql/bin/initdb -D <scratch>/pgdata -U postgres --auth=trust -E UTF8
out/tools/postgres/pgsql/bin/pg_ctl -D <scratch>/pgdata -o "-p 18977 -c listen_addresses=127.0.0.1" -w start
out/tools/postgres/pgsql/bin/createdb -h 127.0.0.1 -p 18977 -U postgres product_ops_test_v06
$env:PRODUCT_OPS_TEST_DATABASE_URL = 'postgresql+psycopg://postgres@127.0.0.1:18977/product_ops_test_v06'
python -m uv run pytest tests/runtime/test_postgres.py --no-cov -q
python -m uv run python scripts/runtime_checks.py --temporal-cli out/tools/temporal/temporal.exe
python -m uv run python scripts/backup_restore_check.py --pg-bin out/tools/postgres/pgsql/bin --url $env:PRODUCT_OPS_TEST_DATABASE_URL --output <scratch>/backup-v06
Remove-Item Env:PRODUCT_OPS_TEST_DATABASE_URL
out/tools/postgres/pgsql/bin/pg_ctl -D <scratch>/pgdata -m fast stop
```

## What these results do not show

- Nothing here touched live Linear. Reconciliation, renewal, the write gate and supersession were
  exercised with `httpx.MockTransport` recordings and recorded source issues.
- The running pilot still runs the 0.5.2 code. Its behaviour changes only after merge and restart.
- Hosted CI has not run; everything above is a local Windows run.
- Service tests used a disposable PostgreSQL instance and a temporary Temporal dev server started
  from the checkout's tools, not the pilot's own services.
