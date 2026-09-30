# Local operator pilot

Version 0.5 adds `product-ops-pilot` alongside the unchanged offline commands. Read [ADR-014](adr/014-local-anthropic-pilot.md) and [observed evidence](v05-validation-record.md). This is a local development pilot, not an accepted MVP or a hosted deployment.

## Existing installation

Alex's private profile is `.local/pilot/pilot.json`; the Anthropic credential is `.local/anthropic.env`. The tracked `.env.example` contains only placeholders. Linear uses the existing sibling `.local/linear.env` by explicit path. Never paste or put keys in command arguments, tracked examples, logs, or tickets. The profile contains paths, not those API keys. Keep `pilot-secrets.json` and the database together for recovery; regenerating its storage key makes existing artifacts unreadable.

The completed smoke used model `claude-opus-5-5`, authorization `alex-2026-09-29-smoke-1`, maximum $10, and local API port **18009** (18001 was occupied). Paid execution is now disabled. Publication is disabled. API/worker processes were stopped after the smoke; PostgreSQL/Temporal development services are separate. The private profile remains reusable. Inspect its status without contacting a model:

```powershell
python -m uv sync --locked --python 3.12
python -m uv run product-ops-pilot status
python -m uv run product-ops-pilot evidence --id dddf28ad-2d90-4d44-a622-995f4a25531b
```

## New machine setup

Start the pinned local PostgreSQL/Temporal services from the checkout with `docker compose up --detach --wait postgres temporal`. Create a separate database named `product_ops_pilot` on the loopback PostgreSQL server. The stock compose ports are 18432 and 18233. Store keys in owner-private files before initializing. Substitute only the local credential paths/team ID/explicit authorized budget below; no key value belongs on the command line. Initialization makes a read-only Linear organization/viewer/team query and migrates the explicit database.

```powershell
python -m uv run product-ops-pilot init --database-url 'postgresql+psycopg://postgres@127.0.0.1:18432/product_ops_pilot' --linear-key-file 'C:\private\linear.env' --linear-team 'YOUR-TEAM-UUID' --anthropic-key-file 'C:\private\anthropic.env' --spend-authorization 'YOUR-AUTHORIZATION-ID' --maximum-spend '10'
```

Paid execution defaults off. `--allow-paid-execution` is for a newly authorized budget/run. Do not change authorization IDs or raise a stored maximum to bypass an exhausted allowance. Migration initialization needs this checkout's `alembic.ini` and migration directory; the installed wheel's CLI imports/help work independently, but it does not embed deployment migrations. Failed partial identity initialization requires operator recovery; never delete/recreate its keys blindly.

Run two separate terminals when needed:

```powershell
python -m uv run product-ops-pilot serve
python -m uv run product-ops-pilot worker
```

The API binds `127.0.0.1` using the profile port. `/health` reports configured-pilot liveness. `/ready` checks storage, recent local worker heartbeat, active operator and paid-execution flag; it is explicitly scoped to local intake, not provider billing, Linear write permissions or downstream acceptance. It returns 503 after the smoke because paid execution is disabled. Stop foreground processes with Ctrl+C. Do not restart duplicate workers to resolve a held call.

## Ticket-selected repository and review

An input file can begin with exactly one `Repository:` line containing an absolute local Git working-tree path, or `github:OWNER/REPO@40_HEX_COMMIT`. The optional `--repository` value must agree with that line. Public GitHub reads use fixed `api.github.com`; private repositories additionally need an explicitly configured private GitHub credential reference. Missing/inaccessible repositories hold; no checkout or code execution occurs.

```powershell
python -m uv run product-ops-pilot intake --input path/to/request.txt --command-id request-001
python -m uv run product-ops-pilot show --id SPECIFICATION-UUID
python -m uv run product-ops-pilot review --id SPECIFICATION-UUID
python -m uv run product-ops-pilot plan --id SPECIFICATION-UUID
```

The first command can spend only while the profile and ledger authorize it. The other commands read stored data. Unknowns remain blocking until an authenticated answer is supplied; answers create revised work and require a new review:

```powershell
python -m uv run product-ops-pilot answer --id SPECIFICATION-UUID --revision 2 --digest EXACT-DIGEST --question Q1 --answer 'Your product decision' --command-id answer-001
```

`analyze --id ... --revision ... --digest ... --command-id ...` is an explicit local operator reanalysis command after a reviewed implementation/configuration change; durable completed roles are reused, and uncertain intents are never repeated automatically. Each runtime result is retained under its configuration. Changing a command ID alone does not clear a held result. Raw role evidence has bounded retention in encrypted storage.

The security operator may request a justified risk change using `risk --id ... --revision ... --digest ... --tier 1 --reason 'Your assessment' --command-id risk-001`. This can spend for a fresh reviewer. It cannot cross the deterministic floor or grant approval. It was tested with recorded providers, not exercised as a live human decision.

## Approval and external publication

Alex must read the exact current specification, advisory findings and native plan. Approval binds their revision, digest, plan digest, scope and operations. The smoke generated a proposal, not that approval. These commands are for the operator's later explicit decision:

```powershell
python -m uv run product-ops-pilot approve --id SPECIFICATION-UUID --revision 2 --digest EXACT-DIGEST --plan-digest EXACT-PLAN-DIGEST --command-id approval-001
python -m uv run product-ops-pilot reject --id SPECIFICATION-UUID --revision 2 --digest EXACT-DIGEST --plan-digest EXACT-PLAN-DIGEST --command-id rejection-001
```

Recovery and identity commands added in version 0.6.0:

```sh
python -m uv run product-ops-pilot state --id SPECIFICATION-UUID
python -m uv run product-ops-pilot reconcile --id SPECIFICATION-UUID
python -m uv run product-ops-pilot run-issue --issue PER-123 --supersedes OLD-SPECIFICATION-UUID
python -m uv run product-ops-pilot grant-renew --days 30
python -m uv run product-ops-pilot revoke --kind approval --identity APPROVAL-UUID
```

`reconcile` reads Linear and never writes; it works with publication disabled and after an approval has expired. `grant-renew` makes approvals bound to the previous grant stale. `revoke` cannot be undone. `state`, `reconcile` and `run-issue` need the running API; `grant-renew` and `revoke` act on the profile database directly. The running services keep the code they were started with until restarted.

Approvals expire after 30 minutes by default. Live publication additionally requires the operator's deliberate `allow_publication` profile setting and API restart, followed by `publish --id ... --command-id ...`. This switch is not an approval: missing, stale, revoked, expired, ambiguous or changed plans still fail. Native publication rechecks current authority before each write and reconciles unknown outcomes without blind recreation.

After complete approved publication, `handoff --id ... --output NEW-PATH.json` exports the signed public envelope only if the exact stored specification is eligible (tiers 0/1). Delivery OS must separately verify its pinned issuer/public key, audience and expected digest in its own store. This command neither installs a downstream adapter nor executes work.

## Review the completed smoke

Specification `dddf28ad-2d90-4d44-a622-995f4a25531b`, revision 2, is preserved in the private database. `.local/pilot/smoke-specification.json`, `smoke-review.json`, `smoke-plan.json`, `smoke-corrected-result.json`, `smoke-final-result.json` and `smoke-accounting.json` provide local review copies. The files produced by Windows PowerShell redirection are UTF-16; database artifacts use canonical JSON. The [public receipt](../evals/reports/anthropic-smoke-2026-09-29.json) intentionally contains metadata and outcome counts only. First failures remain in the encrypted database and public outcome record. No independent semantic score is claimed.
