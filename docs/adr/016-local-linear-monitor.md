# ADR 016: Durable local Linear monitoring in an acceptance-only lane

Status: Accepted, 2026-09-29. Extends [ADR 015](015-issue-driven-intake.md).

## Decision

Implement issue webhooks and five-minute incremental reconciliation in the existing monolith. The public listener has only `/webhooks/linear`; it is a separate loopback port from the operator API. It verifies HMAC-SHA256 over bounded raw bytes, a signed timestamp within 60 seconds, issue shape, organization and configured team before saving a minimal event. Source prose never enters the notification journal. A successful acknowledgment follows durable commit. Body collection and database acknowledgment have time limits; uncertain completion returns a failure and retry deduplication handles a later commit.

Use the existing encrypted Product Ops artifact store as an immutable inbox, result journal, retry journal and poll cursor. Event identity derives from validated issue/version/action fields, not the unsigned delivery header. Cursor advancement follows complete bounded pagination and durable receipt of every event. Reconciliation overlaps its previous cursor by two minutes. Failed or over-budget scans retain the cursor. This is at-least-once delivery with idempotent intake, not an exactly-once provider guarantee. Ten failed processing attempts end in a durable operator hold; they do not vanish or silently authorize retries forever.

Enrollment has a fixed timestamp. Old backlog is excluded. Re-fetch current source using the API key and verify scope before any intake. Exclude known publication provider IDs and Product Ops attribution markers to prevent loops, even if the generated issue contains a repository line. Missing repository declarations, source changes, conflicting selections and revoked authority hold under existing gates. Source edits do not automatically supersede specifications in this release.

Steps 1-4 authorize connection and acceptance tests, not more model spending or ticket publication. The monitor therefore requires both paid execution and publication disabled before submitting eligible intake. Intake persists with no workflow dispatch. This acceptance lane must be deliberately revised before later unattended inference is enabled; flipping a budget flag alone is insufficient.

## Local deployment

Use an official checksum-pinned `cloudflared` binary and a free Quick Tunnel to the isolated webhook listener. A private UUID identifies the one owned webhook. Register/update only that ID, only the configured team and Issue resource. After uncertain registration, re-read the inventory before retrying the same ID. Never modify unrelated webhooks. The secret stays in an owner-private file and is not passed on the process command line. Recheck registration every five minutes; failed registration retries after one minute.

A limited, interactive-user Windows scheduled task starts at login. Its supervisor starts the existing isolated Docker Compose PostgreSQL/Temporal services, retains WSL availability, launches API/worker/monitor, cleans up an owned stale tunnel after a crash, and restarts failed service processes. A named mutex prevents duplicate supervisors. Public routes never proxy to operator routes. Logs and heartbeat/status files stay private and contain no issue body or credentials.

Quick Tunnels have temporary addresses and no production availability guarantee. They are appropriate for this local acceptance pilot, not a production hosting claim. A restart can cause a delivery gap while the owned webhook URL is updated; reconciliation covers current eligible issues missed during that gap. A logged-out, sleeping or disconnected machine cannot execute immediately. Permanently deleted unseen issues are not reconstructed by polling; existing source freshness gates block unavailable enrolled work. A capped scan or exhausted retry is visible and held rather than skipped.

## Evidence boundary

Live administrator discovery, webhook registration/readback, reconciliation and signed synthetic HTTPS delivery can be tested without creating a Linear issue. Synthetic delivery is explicitly distinguished from a genuine Linear-origin issue event. Unit/integration tests cover edits, failures, pagination, duplicate delivery, generated-output exclusion and restart evidence. No paid call, issue/comment write, automatic approval or Delivery OS execution is part of this acceptance.

References: [Linear webhooks](https://linear.app/developers/webhooks), [Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).
