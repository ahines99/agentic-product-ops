# ADR-026: Pause the webhook before stopping; one worker per workspace

Status: accepted, 2026-09-30.

## Context

The pilot was stopped by ending its Windows login task. Its temporary tunnel went away while the
Linear webhook stayed enabled and pointed at it, so Linear recorded repeated failed deliveries and
disabled the webhook. Separately, the main pilot and the prompt-console profile share one database
and workspace; running both workers would let each start the other's queued work under the wrong
server policy.

## Decisions

- `pause_webhook` disables only the owned webhook, after the same organization, administrator and
  team checks as registration, through the single Linear write gate.
- `product-ops-pilot stop` pauses the webhook first, then ends and disables the login task.
  `start` enables and runs the task; registration re-points and re-enables the webhook.
  `webhook-pause` pauses without stopping.
- The monitor pauses the webhook in its shutdown path. A hard kill or crash skips this; the next
  start recovers, and polling reconciles events missed in between.
- Profiles gain `worker_enabled`. The main pilot, which only monitors, runs without a worker, so
  the console's worker is the only one serving the shared workspace.

## Consequences

- Planned stops no longer get the webhook disabled by Linear.
- Unplanned outages can still cause failed deliveries until the next start; nothing is lost
  because polling covers the gap.
- Two profiles that both need workers must use separate workspaces.
