# v0.5.2 local monitor validation

Date: 2026-09-29 local time. Scope: steps 1-4, connection and no-execution acceptance.

## Implemented and exercised locally

- Isolated webhook-only FastAPI listener, raw-body signature and timestamp checks, organization/team bounds, request limits, commit-before-acknowledgment and redacted failures.
- Encrypted durable event/result/retry journals, stable deduplication, cursor overlap, bounded pagination, cursor retention after provider/persistence failure, and restart recovery.
- New-issue enrollment, old-backlog and generated-output exclusion, source re-fetch, repository-name lookup and existing edited-source/approval holds.
- A limited Windows login task named `AgenticProductOpsPilot`, supervised API/worker/monitor and existing isolated PostgreSQL/Temporal infrastructure. An owned stale tunnel is cleaned up after service failure. No machine reboot or pre-login service claim is made.
- Official Cloudflare cloudflared 2026.9.3 Windows binary downloaded from its GitHub release and checked against the release asset SHA-256. Private configuration pins that digest. No paid tunnel or hosting subscription was provisioned.

## Live external evidence

The existing API key's viewer/admin/organization/team scope was verified. One explicitly owned Issue webhook was registered, then updated after tunnel-address rotation. Readback verified the same owned webhook UUID, configured team, enabled state and current URL. Unrelated webhooks were not changed. Read-only scoped reconciliation succeeded and found no eligible new issues.

Signed synthetic, pre-enrollment notifications were sent through the public HTTPS tunnel. Original and duplicate both returned HTTP 200; a bad signature returned 401; `/v1/intakes`, `/health`, `/docs` and `/openapi.json` returned 404. The synthetic event was persisted once and excluded without fetching a fake issue. Source text did not become authority.

A durable pending synthetic event survived a service restart and reached its expected excluded result. Its polling cursor did not move backward. The temporary URL changed and the same owned webhook was updated. An additional forced pilot-process failure was recovered by the supervisor; one current owned tunnel remained. Startup initially failed because Windows PowerShell treated Docker stderr progress as fatal; the corrected launcher now uses the native exit code.

**No genuine Linear-origin issue notification has yet been observed.** The synthetic probe is not presented as that evidence. No live issue/comment was created or edited. No new model calls or Delivery OS execution occurred. Both execution/publication settings are disabled; historical smoke reservations remain $2.341864 across six calls.

## Repository validation

Both Python 3.12 and 3.13 default suites pass 281 tests, with five explicitly service-dependent skips. The separate PostgreSQL/Temporal suite passes all 12 tests, including those five skipped cases; seven overlap the default suite. Ruff, formatting, strict mypy, docs links, schema checks, secret scanning, locked dependency audit, reproducible package builds and clean-wheel checks pass locally. The clean wheel imports the new monitor/listener outside the checkout. Hosted CI remains unrun; no Git push occurred. The existing Starlette TestClient deprecation warning remains.

Private evidence is ignored under `out/` and `.local/pilot/`: validation logs, `monitor-probe.json`, `restart-probe.json`, `restart-result.json`, `monitor-health.json` and service/tunnel logs. No secret or raw Linear issue body is copied into this public record.

## Remaining acceptance boundary

A real newly created Linear issue is needed to observe provider-origin delivery. Later continuing-inference operation, governed source supersession, independent semantic evaluation and actual Delivery OS consumption remain open. The local Quick Tunnel has no production availability guarantee; the machine must be awake and signed in. These checks do not establish autonomous MVP completion. See [monitor runbook](../linear-monitor.md) and [ADR 016](../adr/016-local-linear-monitor.md).
