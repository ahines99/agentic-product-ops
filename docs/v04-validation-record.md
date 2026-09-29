# Version 0.4 validation record

Dated 2026-09-29. Local evidence only. No paid inference, live Linear publication, production identity, actual Delivery OS intake, hosted CI or MVP acceptance is claimed. All source inspection remained inert. The sibling credential file was inspected for presence only; its value was not printed, copied or configured.

## Results

- Default suite: **212 passed, 5 service-dependent skips on each of Python 3.12.10 and 3.13.15**. Separate environment selection was verified through each clean-wheel interpreter.
- Real containerized PostgreSQL 17.11 and Temporal CLI 1.9.1: 12 tests passed across runtime and revision suites. Seven are also ordinary revision tests; five are service-dependent scenarios, not 12 additional unique tests.
- Docker through WSL Ubuntu: digest-pinned build/start passed, non-root API reports health 200, readiness 503, unauthenticated command 401 and publication disabled. Host image Python is 3.12.14. The one-shot Temporal volume owner initialization was needed for its UID-1000 process.
- Populated PostgreSQL custom-format backup restored into a separate owned random database. All logical table fingerprints matched and a restored immutable trigger rejected mutation. Restore database removed; ignored dump/report retained. Backup report contained 196 artifacts, 31 audit rows, 2 commands, 8 controls and 7 outbox rows; publication operation table was empty in this service fixture. Native mock operations are exercised separately in integration tests.
- Backup SHA-256: `95e719c443064537cc10db62469538d6ab7b8be02bc0fca57ecc8b1749734053`. The report is local `out/backup-g07/610a72ea4dfe43e08f38bbd07eb15af3.json`; source records were not overwritten.
- Direct CLI replay also passed: valid drafts/roles exit 0, ambiguous drafts/roles exit 2, static snapshot/grounding, legacy publication/handoff, semantic scoring and 45-case routing. Evidence is retained locally in `out/v04-demo-c7bf987f`.
- Native publication and signed-handoff integration tests were additionally rerun with encrypted Store payloads: 20 passed on each Python version, including reconciliation and independent consumer paths.
- Owned development containers and the verified task-owned WSL keepalive were stopped after the final successful probe; named volumes and ignored evidence were retained.
- One upstream TestClient/httpx deprecation warning remains unsuppressed. Docker WSL build could not capture Git provenance metadata; no image attestation is claimed.

All local release gates passed on both supported Pythons: lock, Ruff lint/format, strict mypy (70 source files), docs/local links, frozen public schema, secret scan, dependency audit (no known vulnerabilities), fixture regeneration, two byte-identical sdist/wheel builds and isolated clean-wheel smoke. Raw ignored logs are `out/v04-verify-312.log` and `out/v04-verify-313.log`. Both interpreters produced identical artifact hashes for the same source. Final documentation/metadata reconciliation also passed repeated packaging checks; cryptography is declared directly without changing the already tested locked version. Hosted Actions remains unverified because the repository has no remote.

## Setup and complete local checks

```sh
python -m pip install uv==0.12.18
python -m uv sync --locked --python 3.12
python -m uv run python scripts/verify.py
```

A separate PowerShell Python 3.13 environment must set `UV_PYTHON` so nested uv commands do not fall back to `.python-version`:

```powershell
$env:UV_PROJECT_ENVIRONMENT = '.venv-313'
$env:UV_PYTHON = '3.13'
python -m uv sync --locked --python 3.13
python -m uv run --python 3.13 python scripts/verify.py
Remove-Item Env:UV_PROJECT_ENVIRONMENT
Remove-Item Env:UV_PYTHON
```

The verifier checks lock, Ruff lint/format, strict mypy, tests, local doc links, frozen public schema, default-detector secret scan, unchanged generated fixtures/corpora, byte-identical repeated sdist/wheel builds, isolated hash-locked wheel installation and dependency audit. Clean-wheel checks include recorded CLI flows, semantic scoring and the public consumer/schema resource without producer import. Public dependency downloads/auditing are networked; demos do not call model/provider APIs.

## Offline demonstrations

```sh
python -m uv run product-ops draft --input examples/feature-request.md
python -m uv run product-ops draft --input examples/ambiguous-request.md
python -m uv run product-ops roles-demo --input examples/feature-request.md
python -m uv run product-ops roles-demo --input examples/ambiguous-request.md
python -m uv run product-ops inspect-repository --root . --repository-id product-ops
python -m uv run product-ops roles-demo --input examples/feature-request.md --repository-root . --repository-id product-ops
python -m uv run product-ops demo --output out/demo-v04-1
python -m uv run product-ops verify-handoff --input out/demo-v04-1/handoff.simulated.json
python -m uv run product-ops evaluate-semantic --corpus examples/semantic/corpus.json --attempts examples/semantic/attempts.json --adjudications examples/semantic/adjudications.json
python -m uv run python scripts/evaluate.py --corpus evals/fixtures/m1-routing-corpus.json --output out/routing-v04-1.json
python -m uv run pytest tests/integration/test_native_publication.py tests/integration/test_signed_handoff.py --no-cov -q
```

Ambiguous/unknown input intentionally exits 2. Use fresh demo/report output paths; v1 evidence files refuse overwrite. `ground --specification <json> --snapshot <json>` requires a specification already bound to that exact snapshot and reports static coverage only. Native signed v2 is exercised by the test command; legacy demo remains explicitly unsigned simulation.

## Container and real service checks

Use only the disposable development database named here. Runtime migration tests alter its schema. With Docker available:

```sh
docker compose -p apo-local up --build --detach --wait
python -m uv run python scripts/container_probe.py
```

Then in PowerShell:

```powershell
$env:PRODUCT_OPS_TEST_DATABASE_URL = 'postgresql+psycopg://postgres@127.0.0.1:18432/product_ops_test'
$env:PRODUCT_OPS_TEST_TEMPORAL_ADDRESS = '127.0.0.1:18233'
python -m uv run pytest tests/runtime tests/integration/test_revisions.py --no-cov -q
python -m uv run python scripts/backup_restore_check.py --pg-bin out/tools/postgres/pgsql/bin --url $env:PRODUCT_OPS_TEST_DATABASE_URL --output out/backup-v04
Remove-Item Env:PRODUCT_OPS_TEST_DATABASE_URL
Remove-Item Env:PRODUCT_OPS_TEST_TEMPORAL_ADDRESS
docker compose -p apo-local down
```

`--pg-bin` must point to installed PostgreSQL 17 client tools on your OS; the path above is the downloaded local Windows tool layout, not a tracked dependency. Backup needs a populated service-test database. It writes an exclusive custom dump, creates/restores/checks/drops only its own random database and preserves source data. Do not substitute a production database.

In this Windows workspace Docker is inside WSL: prefix Docker commands with `wsl -d Ubuntu-22.04 --exec`, pass `--project-directory '/mnt/d/Code/Personal/Portfolio Projects/agentic-product-ops'`, and keep that distribution running during checks. The actual owned project was `apo-offline-g07`; it is stopped after validation without removing its named volumes. Native alternative: set the PostgreSQL test URL and run `python -m uv run python scripts/runtime_checks.py --temporal-cli out/tools/temporal/temporal.exe`; the helper manages only its own temporary Temporal process.

## Corrections preserved as evidence

Tests exposed and corrected a shared-database fixture that queried unrelated runs, a revision fixture that bypassed migration-installed immutability triggers, and a repository snapshot assertion that used the context field name instead of the snapshot field name. No product approval/ambiguity gate was weakened. Secret scanning identified newly checked-in result/input/output hashes; only exact named JSON SHA-256 fields were added to the existing narrow nonsecret exception, leaving detectors and other content enabled.

The [case study](offline-case-study.md), [implementation status](implementation-status.md), [backlog](backlog.md) and [external next steps](remaining-work.md) describe what these results do and do not establish.
