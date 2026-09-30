# Version 0.5 validation record

Date: 2026-09-29. This record extends the completed [v0.4 offline record](v04-validation-record.md). No MVP, independent semantic quality, live publication or Delivery OS acceptance is claimed.

## Live engineering smoke

The [public receipt](../../evals/reports/anthropic-smoke-2026-09-29.json) binds all three configurations and their role receipts. Private full artifacts remain in encrypted pilot PostgreSQL and `.local/pilot/`; source and repository bodies are not published in the receipt.

| Attempt | Result | Paid calls | Preserved outcome |
| --- | --- | --- | --- |
| `anthropic-pilot-v1` | REVISION_REQUIRED | 2 | Mixed source/evidence provenance rejected during composition. Completed outputs recovered from durable records without inference and the failure persisted. |
| `anthropic-pilot-v2` | PAUSED | 3 | Provenance guidance corrected; reviewer output rejected because its digest field contained prose. |
| `anthropic-pilot-v3` | PROPOSED | 1 additional | Exact-digest echo guidance and constraint descriptions; prior valid extraction/decomposition reused; fresh reviewer returned six advisory findings and no blockers. |

Final specification: `dddf28ad-2d90-4d44-a622-995f4a25531b`, revision 2, digest `760cefddfd8afd9ba16d95a7f228f28548aa3971c563226f83715545a7a5db7b`. Six requirements, one work item, tier 3. Native plan: one issue operation, digest `0bce3334ef84795133350a0c2f04d3420a336c254f35040cd0fee288246c89b7`. Zero human approvals, zero Linear mutations, zero actual Delivery OS intakes.

All six calls used `claude-opus-5-5` under the same **$10 total** authorization. Observed usage: 78,037 input and 10,821 output tokens. Durable reservations: **$2.341864**. Configured conservative-rate estimate ($8/$20 per million): **$0.840716**. Published standard-rate estimate ($4/$20): **$0.528568**. **Actual billing has not been verified.** Estimates include failed outputs; cached role replays are not counted twice. See [model pricing](https://platform.claude.com/docs/en/models/overview). Paid execution was disabled and owned API/worker processes stopped after the smoke.

Read-only Linear identity discovery verified the configured organization/actor/team with the existing API key. The configured API returned the preserved proposal and denied disabled publication with HTTP 403. Readiness returns 503 with paid execution disabled. No live ticket-write or risk-reassessment human decision was made.

## Local verification

Logs are in ignored `out/v05-*` files. `scripts/verify.py` completed successfully on Python 3.12.10.

| Check | Result |
| --- | --- |
| Python 3.12.10 default suite | 243 passed; 5 explicit service skips |
| Python 3.13.15 default suite | 243 passed; 5 explicit service skips |
| Isolated PostgreSQL/Temporal/revision suite | 12 passed, including the 5 default skips |
| Ruff lint/format and strict mypy | Passed; mypy checked 79 source files |
| Docs, public schema, fixture regeneration | Passed; 39 Markdown documents checked; regeneration unchanged |
| Secret scanning and locked dependency audit | Passed; no known dependency vulnerabilities reported |
| Package build and reproducibility | Wheel and sdist built; byte-identical across two builds |
| Clean-wheel smoke | Passed outside source checkout; locked dependencies, both CLI entrypoints and offline flows |
| Hosted CI | Not run; no push authorized or performed |

Combined branch coverage was 79% in the Python 3.12 default suite; coverage does not establish product quality. The final added publisher-assembly test covers disabled publication, UNKNOWN followed by reconciliation and repeated idempotent success. Spending tests cover concurrent reservations, restart, uncertainty, immutable terms and reporting. Risk tests cover new reviewed revisions, stale digest/floor denial, blocking review and mid-review revocation.

The first service run reused `product_ops_test` from earlier development and failed on stale outbox work. That log is retained as `out/v05-runtime.log`. A fresh `product_ops_test_v05` database passed all 12 PostgreSQL/Temporal/revision tests, including restart, cancellation and replay. Seven overlap the default suite; five are the service-dependent skips. The actual pilot database `product_ops_pilot` was never used or dropped by those tests.

The previously observed v0.4 container/restore checks remain historical evidence. They are not relabeled as a new v0.5 image build. Hosted Actions have not run because nothing was pushed. One upstream Starlette TestClient deprecation warning remains unsuppressed.

## Exact setup and checks

```powershell
python -m pip install uv==0.12.18
python -m uv sync --locked --python 3.12
python -m uv run python scripts/verify.py
```

The verification script checks lock, Ruff lint/format, strict mypy, tests, docs, public handoff schema, secrets, unchanged fixture regeneration, byte-identical builds, package build, isolated clean-wheel behavior and dependency audit. It makes no paid model calls. The wheel smoke also checks the new `product-ops-pilot` entrypoint outside the checkout.

For Python 3.13 in a separate Windows environment:

```powershell
$env:UV_PROJECT_ENVIRONMENT='.venv-313'
$env:UV_PYTHON='3.13'
python -m uv sync --locked --python 3.13
python -m uv run pytest --no-cov -q
Remove-Item Env:UV_PROJECT_ENVIRONMENT
Remove-Item Env:UV_PYTHON
```

For service checks, start pinned local PostgreSQL/Temporal and create a **fresh disposable** database whose name starts with `product_ops_test`. Substitute that database's name below; never use `product_ops_pilot`. Reusing an old test database's outbox with a different Temporal history/policy is not an isolated test run.

```powershell
$env:PRODUCT_OPS_TEST_DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:18432/product_ops_test_FRESH'
$env:PRODUCT_OPS_TEST_TEMPORAL_ADDRESS='127.0.0.1:18233'
python -m uv run pytest tests/runtime tests/integration/test_revisions.py --no-cov -q
Remove-Item Env:PRODUCT_OPS_TEST_DATABASE_URL
Remove-Item Env:PRODUCT_OPS_TEST_TEMPORAL_ADDRESS
```

Offline examples and retained pilot evidence:

```powershell
python -m uv run product-ops draft --input examples/feature-request.md
python -m uv run product-ops draft --input examples/ambiguous-request.md
python -m uv run product-ops demo --output out/demo-v05-NEW
python -m uv run product-ops-pilot status
python -m uv run product-ops-pilot evidence --id dddf28ad-2d90-4d44-a622-995f4a25531b
```

The ambiguous offline command intentionally exits 2. Demo output paths must be new. Pilot status/evidence read the preserved database without inference. Full setup and future human approval commands are in [local pilot](../local-pilot.md); exact remaining acceptance steps are in [remaining work](remaining-work.md).

## Repository state

Work is on local `main`. Origin is `https://github.com/ahines99/agentic-product-ops.git`. No push, hosted run, release tag or live ticket creation occurred. Use `git log -1 --oneline` and `git status --short` for the exact final commit and working-tree state; private `.local/`, virtual environments, build output and check logs remain ignored.
