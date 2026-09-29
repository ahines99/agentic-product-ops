# Linear integration

Version 0.2 retains the deterministic LinearPublicationPlan and in-memory demo, and adds a durable simulation plus a mock-only GraphQL issue-create adapter. The adapter requires MockTransport and rejects real networking. OAuth, live credentials, actual Linear IDs, webhooks and hosted MCP publication are absent. IDs beginning `FAKE-` are simulation evidence only.

## Planned production adapter

Use Linear's explicit GraphQL API from deterministic services. OAuth should request only the capabilities needed to read relevant metadata and create approved issues; `issues:create` is available as a narrower mutation scope. App actor authorization can attribute actions to the application; persist the workspace-specific app identity. Recheck exact current scope/actor behavior during M4 against [OAuth documentation](https://linear.app/developers/oauth-2-0-authentication), [app actor authorization](https://linear.app/developers/oauth-actor-authorization), and [GraphQL documentation](https://linear.app/developers/graphql). These references were consulted during initialization on 2026-09-28. No credentials were configured and no provider endpoint was exercised.

Never give an analyst, decomposer, or reviewer a Linear mutation tool. A proposal may suggest IDs, but trusted policy validates workspace/team/project/repository/label scope and canonical rendering. M0 has no project or label allowlist entries and defaults to one offline workspace/team. The real adapter must discover and validate tenant metadata, not reuse fixture identifiers.

## Publication plan and template

Every operation contains local work ID, approved team/project/labels, title, escaped Markdown description, logical operation key, and request digest. Plan digest covers its operations and generation. The issue description has Objective, Context, Requirements, Acceptance criteria, Dependencies, Risks / constraints, Repository context, Open questions, and an attribution footer with specification ID/revision/digest and operation marker. Blocking questions prevent plan construction. Dependencies are local references in the M0 description; native Linear parent/relationship mapping is not implemented. Epic/project semantics need explicit M4 validation.

The complete deterministic plan is approved, rather than allowing a second model generation at mutation time. Changed text, destinations, labels, count, ordering, or generation invalidates approval. M0 allows generation 1 only. An intentional later republish requires a governed generation/revision policy; changing a generation to bypass deduplication is not allowed.

## Idempotency and uncertainty

Logical operation identity is the canonical digest of `[specification_id, revision, work_item_local_id, publication_generation]`. Request digest binds destination and rendered content. The fake publisher stores attempt 1, status, provider object/request IDs, and observed timestamp. Duplicate successful commands return prior evidence. Key reuse with different content fails.

The harness records UNKNOWN before fake dispatch. A simulated lost response can leave an object created remotely. It stops subsequent operations and reconciles on another command by exact operation identity and complete content equality. Unavailable, absent, or conflicting lookup data leaves UNKNOWN and never causes a second create. No authoritative nonexistence retry is implemented.

Production must transactionally persist intent, attempts, authorization snapshot, bounded request body, provider timestamps, and reconciliation records; use unique constraints and dispatch leases across workers. Recheck approval with a real clock before every external write. A cancellation accepted after a write is in flight cannot guarantee remote rollback. Tests against a fake do not establish real Linear exactly-once semantics.

The new durable harness exercises stored request/intent/evidence, unique keys, row-locked reservation, an advancing approval clock, persisted cancellation and restart recovery. UNKNOWN is committed before a fake call. Repeated successful calls return stored evidence; uncertain calls only reconcile. PostgreSQL tests exercise concurrent command and fake-publication submissions; the restart/fault harness uses a SQLite test double. Neither proves live provider behavior. API publication remains disabled. The mock GraphQL adapter tests explicit variables, bounded response parsing and exact team/title/body equality without retries.

## Webhooks and MCP

Webhooks are deferred. If enabled, verify signatures over original bounded bytes, persist receipt before asynchronous work, deduplicate delivery identifiers, explicitly validate event/action, acknowledge quickly, and tolerate redelivery. Creating/managing webhook subscriptions may require elevated privileges; do not widen normal publication scopes just to provision them. See [Linear webhooks](https://linear.app/developers/webhooks). Hosted MCP remains an optional operator tool; production publication stays behind this application's tested adapter.

M4 exit requires actual authorized fixture publication, stale/rejected/expired approval denials, durable fault recovery, provider evidence, and controlled budget. None is claimed from M0 simulations.
