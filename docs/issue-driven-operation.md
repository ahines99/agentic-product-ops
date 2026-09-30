# Issue-driven operation

The intended user input is a basic Linear issue and repository name. The agent operates the local infrastructure, intake, evidence and commands. Users should not prepare specification JSON, manage worker terminals or copy digests. Product decisions, unresolved ambiguity and exact work approval remain human decisions under the current policy.

For example: “Use OPS-17, repository example.” Alternatively, put `Repository: example` in the issue description. `OPS-17` is illustrative, not a ticket created by this project.

## Executable now

Version 0.5.1 provides authenticated Linear source reading, name-to-local-repository resolution, bounded static snapshots, durable idempotent intake, source-edit conflict detection, budget-disabled holds, source freshness gates and a combined API/worker launcher. Existing analyst/decomposer/reviewer and governed publication paths remain available under their existing authorizations.

The operator agent configures `repository_search_roots` in its private profile. A name must match exactly one immediate child Git directory across these roots. Additional accessible repositories can be configured without expanding the issue's authority. No cloning or target repository code execution occurs. Remote-only names are not automatically resolved; the older pinned GitHub selector remains separate.

Implementation commands for the agent, from the checkout with the locked environment installed:

```powershell
.\.venv\Scripts\python.exe -m agentic_product_ops.pilot.cli run
.\.venv\Scripts\python.exe -m agentic_product_ops.pilot.cli run-issue --issue OPS-17 --repo example
```

`run` combines API and worker and requires the existing local database and Temporal services. It replaces separate `serve` and `worker` processes; the agent must avoid running both arrangements concurrently. The worker prints readiness once and records a heartbeat without dumping source text or credentials.

The intake receipt reports `queued` when paid execution is enabled or `held_paid_execution_disabled` otherwise. A hold creates no workflow dispatch and consumes no model budget. The agent can resume with the existing digest-bound `analyze` command after appropriate execution authorization. The original smoke allowance is not a continuing inference allowance.

## Current limits

- The new issue lookup path is mock-transport tested; no user-selected live issue has been supplied for acceptance yet.
- Single-operator retries reuse one issue intake. Edits conflict; automatic supersession is not implemented. Source deletion, edits or provider outages block subsequent approval/publication/handoff. A remote edit can still race a successful freshness check.
- There is no background Linear watcher yet. Creating an issue alone does not currently trigger Product Ops. Watcher enrollment, generated-issue exclusion and recovery are the next integration milestone.
- Exact work approval remains required. No live writes, fresh model calls or Delivery OS execution are implied by an intake receipt.
- Actual Delivery OS acceptance, independent semantic evaluation, continuing spend policy and hosted CI remain open. This release is not autonomous MVP completion.

See [ADR 015](adr/015-issue-driven-intake.md), [implementation status](implementation-status.md) and the dependency-ordered [backlog](backlog.md).
