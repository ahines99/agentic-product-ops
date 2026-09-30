# v0.5.1 issue-driven intake validation

Date: 2026-09-29 local time. This is engineering validation, not MVP or unattended-operation acceptance.

## Exercised

- Python 3.12 and 3.13: 265 passed and five service-dependent skips in each default suite. The separately configured PostgreSQL/Temporal suite passed 12 tests, including all five skipped cases. Seven overlap the default suite; these are not 12 additional unique tests.
- New recorded-transport/security coverage: exact Linear origin and query; tenant, actor, team and issue identity; bounded source; URL/path/command rejection; missing/conflicting/ambiguous repository names; atomic source binding; duplicate submission; edited source and reduced team authority holds; inert prompt injection; no outbox while paid execution is off; unavailable source hold; source change stops the next native write; launcher cleans up its sibling on exit/failure.
- Ruff lint/format, strict mypy, docs links, schema export, secret scan, locked dependency audit, package build, reproducible sdist/wheel and clean-wheel smoke passed locally.
- The initial wheel smoke accidentally selected the old installed 0.5.0 version. The script now reads the checkout's project version and asserts the installed wheel version outside the checkout. The corrected smoke exercised 0.5.1 and the new `run-issue` CLI entry point.
- Combined API/worker process started locally on the existing port 18009. Health returned OK, worker heartbeat was recent, operator identity active, and pending outbox count zero. Repository-name roots were privately configured for the existing Portfolio Projects directory. PostgreSQL/Temporal use the existing pilot services; tests used a separate disposable `product_ops_test_v051` database.
- The user's current publication setting is enabled, but no exact work approval was supplied and no publication was requested. Paid execution remains disabled. Six historical model calls and $2.341864 reserved spending are unchanged.

## Evidence boundary

No real Linear issue was selected during this change. Source lookup is recorded-transport tested; earlier live Linear evidence covers identity/team discovery only. No new model inference, live ticket write, handoff to actual Delivery OS or hosted CI run occurred. No webhook/poller, source-edit supersession, unattended eligibility policy or reboot recovery was implemented. The running service does not turn issue creation into automatic execution. The existing Starlette TestClient deprecation warning remains.

Private diagnostic logs are ignored under `out/`: `verify-v051.log`, `tests-v051-313.log`, `services-v051.log`, `reproduce-v051-final.log`, `wheel-v051-final.log`, and `pilot-run-v051.*.log`. They are local evidence, not release artifacts. See [operation](issue-driven-operation.md), [ADR 015](adr/015-issue-driven-intake.md) and [status](implementation-status.md).
