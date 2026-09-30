# Local Linear monitor

Version 0.5.2 connects newly created issues in the configured team to durable Product Ops intake. It currently runs in **acceptance mode: no paid execution, publication, approval or Delivery OS execution**. The operator agent owns setup and diagnostics. Users need not edit JSON or manage terminals.

## Operation

The webhook listener on loopback port 18010 exposes only `/webhooks/linear` through the temporary HTTPS tunnel. The operator API stays on loopback port 18009. Signed events enter an encrypted durable inbox before acknowledgment. The monitor fetches current issue data, reads `Repository: name`, excludes generated output and pre-enrollment backlog, and submits authenticated local intake. Missing information and changed sources hold. Eligible intake is stored without a workflow dispatch while execution is disabled.

Every five minutes, a scoped, paginated API query reconciles changes since the durable cursor with a two-minute overlap. At most 20 pages of 50 issues are accepted per scan; exhaustion holds the cursor and appears as a poll error. Per-event transient failures retry with persisted backoff up to ten attempts, then remain held for operator diagnosis. Historical finished events remain immutable and replay cannot reopen them.

The Windows `AgenticProductOpsPilot` scheduled task runs `scripts/run_local_pilot.ps1` at login under the existing user, without elevation or a stored password. It starts the established `apo-offline-g07` infrastructure, keeps WSL available and supervises the combined Python process. Failed processes restart; the one owned Linear webhook is updated to the new temporary address. This is login startup, not a pre-login Windows service or an always-on deployment.

## Operator diagnostics and acceptance commands

```powershell
Get-ScheduledTask -TaskName AgenticProductOpsPilot
Get-Content .local/pilot/monitor-health.json
.\.venv\Scripts\python.exe -m agentic_product_ops.pilot.cli status
.\.venv\Scripts\python.exe scripts/probe_linear_monitor.py
```

The probe sends a signed **synthetic, pre-enrollment** event through the public HTTPS endpoint, repeats it, checks invalid signature denial and verifies operator routes remain unavailable. It creates no real ticket and cannot trigger model inference. A synthetic event is not evidence that Linear itself sent an issue notification.

Private `monitor-health.json` reports heartbeat time, webhook registration, last successful reconciliation, pending queue age, processing/retry/hold counts and redacted failures. Poll and registration failures retain durable state. `.local/pilot/service-*.log`, `infrastructure.log` and `tunnel.log` support diagnosis. Secrets live in the separate private `monitor-secrets.json`; never display or commit that file. Provider webhook ID and enrollment time persist across restarts.

## Remaining limits

The tunnel is temporary and free, with no production availability guarantee. The machine must be awake and signed in. There is no independent external uptime alerting. Changed sources require governed resolution; automatic supersession and automatic resumption after later budget authorization remain future work. Source freshness still gates approval, publication and handoff. Enabling a paid flag does not activate this acceptance monitor for autonomous execution.

Live registration and synthetic delivery are separate from a genuine Linear-origin issue event. That last acceptance observation requires a new real issue from the user, or explicit authorization to create a disposable test issue. No issue creation is performed during steps 1-4. See [ADR 016](adr/016-local-linear-monitor.md) and [implementation status](implementation-status.md).
