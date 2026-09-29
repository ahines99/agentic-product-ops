# Provider, clarification and authority engineering evidence

Historical intermediate increment dated 2026-09-29. Superseded release totals and final commands are in [0.4 validation](v04-validation-record.md). See [completion checklist](offline-completion-plan.md) and [ADR-010](adr/010-revisions-providers-and-durable-authority.md).

Default suite before adding the separately enabled Temporal revision test: 175 passed, 4 skipped. The new service-only test adds one default skip. Real service run: PostgreSQL invariant test 1 passed; Temporal/connected governance plus revision suite 11 passed. This includes concurrent revision attempts, two-attempt review exhaustion, preserved first failure, stale revision approval denial and a new approval after a reviewed clarification revision. Test fixtures initially queried unrelated rows in the shared disposable PostgreSQL database; those assertions were corrected to the specific specification/execution and the service run then passed. No product gate was relaxed.

Responses transport tests cover role separation, tool absence, token preflight before generation, local strict-schema rejection, usage bounds, refusal, incomplete output, malformed/oversized content, redirects, rate limiting, server failures and timeout. They use authored responses, not inference. The integrated initial-generation test drives mock Responses through durable roles into either a proposal or persisted ambiguity. General intake remains tier 3.

Authority tests exercise signed ephemeral JWTs, subject resolution through durable grants, token revocation before replay of an idempotent command, actor/subject/approval/grant changes after the first fake publication operation, scoped grants and pinned-key overlap/retirement. Readiness remains false. No production identity is configured.

GitHub tests authenticate only to MockTransport, pin commit/tree/blob identities, reject malformed/changed/oversized content and redirects, and exclude vendor/hidden/deep files before fetching. Grounding reports are lexical matches over static metadata. They preserve missing-evidence counts and never execute code or pass document instructions as authority.

## Commands

```powershell
python -m uv sync --locked
python -m uv run pytest --no-cov -q
python -m uv run ruff check .
python -m uv run ruff format --check .
python -m uv run mypy
$env:PRODUCT_OPS_TEST_DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:18432/product_ops_test'
python -m uv run pytest tests/runtime/test_postgres.py --no-cov -q
python -m uv run python scripts/runtime_checks.py --temporal-cli out/tools/temporal/temporal.exe
Remove-Item Env:PRODUCT_OPS_TEST_DATABASE_URL
```

The explicitly named PostgreSQL database must be disposable; its invariant test resets test tables. The runtime helper starts and stops its own loopback Temporal process. Downloaded tools are local ignored artifacts; see [prior service setup](offline-expansion.md). No live provider or downstream worker is started by these commands.

The offline `ground --specification <json> --snapshot <json>` command requires a specification already bound to the exact snapshot digest. It reports retrieval coverage; it cannot attach evidence or approve work.
