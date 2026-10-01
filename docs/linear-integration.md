# Linear integration

The local pilot uses an explicit Linear API key, as selected by the operator. An earlier OAuth flow was never wired and was removed in 0.6.0 ([ADR-022](adr/022-remove-unwired-adapters-and-measure-the-model.md)). Organization/viewer/team/admin discovery, one owned webhook's registration/update and read-only reconciliation succeeded live. The work publisher is disabled in the private profile and still requires exact current human approval before each native operation. No live ticket/comment writes have been exercised; webhook configuration is the only live mutation performed. See [monitor operation](linear-monitor.md), [pilot commands](local-pilot.md) and [ADR-014](adr/014-local-anthropic-pilot.md).

Version 0.4 introduced native GraphQL planning and durable publication orchestration, exercised with mock HTTP transport. Version 0.5 wired a guarded pilot publication handler and exercised read-only identity discovery; no live ticket creation occurred. Version 0.5.1 adds [issue-driven intake](issue-driven-operation.md), currently exercised with mock source transport. The original in-memory demo and `FAKE-` records remain explicitly simulated.

## Recovery after expiry or uncertainty (version 0.6.0)

These paths are covered by mock-transport tests only. See [ADR-021](adr/021-publication-recovery-and-write-gate.md).

| Situation | What the operator does | What the system guarantees |
| --- | --- | --- |
| A write timed out and the approval has since expired | `product-ops-pilot reconcile --id ID` | Exact-ID reads only. An observed object is recorded as succeeded. Nothing is created. |
| Preflight failed before the write was sent | Publish again under a valid approval | The intent is dispatched once. A concurrent attempt conflicts on the dispatch-authority record. |
| The approval expired before publication finished | Approve the same revision, digest and plan again, then publish | Accepted only after expiry. The earlier approval authorizes nothing further. |
| A revised specification is approved after an earlier revision wrote tickets | Decide by hand; optionally enable `allow_revision_republication` in the profile | Default is a hold before any provider call. |
| The source issue was edited | `product-ops-pilot run-issue --issue ID --supersedes OLD-SPECIFICATION-ID` | The stale specification is cancelled and the edit enrolled in one transaction. Refused if the stale one has publication writes. |
| A dispatched write can never be observed | None available | It stays `UNKNOWN`. There is no command that permits a resend. |

`product-ops-pilot state --id ID` reports the derived lifecycle state.

## Ticket format and pickup contract (version 0.6, 2026-10-01)

Profiles using `pilot-execution-v2` start each description with `Repository: <name>`. A plan
adds the `delivery-ready` label, and a `Handoff: sha256:<digest>` line, only when the handoff
policy allows the specification's tier and the profile binds the label (`delivery-label`). Delivery
OS fetches the signed handoff from `GET /handoffs/<digest>` with its separate read-only credential
(`handoff-reader-init`); see [ADR-028](adr/028-pull-handoff-contract-with-delivery-os.md). See the [roadmap](roadmap.md) for the full contract and
[ADR-027](adr/027-ticket-pickup-contract-product-ops-side.md).

## Identity and scope

Trusted configuration maps local workspace/team/project/label aliases to provider UUIDs and binds the Linear organization and app actor. The adapter reads current organization, viewer, team, project team membership and label scope before mutation. Source text cannot change these bindings. Every mutation passes one adapter gate that requires declared intent, enabled writes and a write-capable scope.

Provider facts were checked against [GraphQL](https://linear.app/developers/graphql) and the official SDK schema during implementation. Mock conformance is not live compatibility acceptance.

## Native plan v2

`build_native_plan` deterministically renders approved issues and blocking issue relations. All mutations, including relations, count against the approved budget and ordered operation keys. Issue prerequisites precede relations. Native target UUIDs derive from stable operation identity; content, destination, generation and order are digest-bound. Only generation 1 is supported. Projects/labels are preexisting allowlisted metadata. Epics/project creation, parent hierarchy and semantic duplicate detection are not implemented.

Descriptions contain objective, context, requirements, acceptance criteria, dependencies, risks, repository context, open questions and exact attribution. Markdown is rendered as inert content. The reviewer approves the exact spec and plan; there is no second content generation at send time. GET plan supports inspection; native approval requires that digest.

## Durable authorization and uncertainty

NativePublisher requires stored current specification, passing review, exact approval and plan, and the same durable Authority store. Per-operation gates recheck revision, expiration, cancellation, revocation, scope, prerequisite evidence and mutation budget. UNKNOWN is committed before HTTP. Metadata checks precede a final authority callback, which records an immutable dispatch authorization snapshot. A late success is saved, but cannot permit subsequent writes after expiry or revocation.

Reconciliation reads exact deterministic target IDs and compares complete content/destination/labels or relation direction. It requires saved dispatch authority. Missing objects are not proof of nonexistence; absence, conflicts, timeouts and uncertain authorization remain UNKNOWN. No blind recreation, automatic paid retry, or provider-wide exactly-once guarantee is claimed. Tests cover restart/lost response, partial batches, metadata-time revocation, late completion, expiry, native dependencies and held conflicts.

The API/Temporal default runtime never calls NativePublisher automatically. The configured pilot requires its publication switch, exact human approval and current authority. Credential loading from the user-specified private file is configured; possession of that key does not authorize creating tickets. Issue-origin work additionally revalidates the source before each mutation dispatch. Controlled live write acceptance remains open.

The [local webhook monitor](linear-monitor.md) and reconciliation are implemented in acceptance mode. Registration/reconciliation and synthetic HTTPS delivery have live evidence; a real Linear-origin issue notification is still unobserved. Hosted MCP publication is not implemented. Native handoff consumes successful publication receipts without executing delivery work. See [ADR-011](adr/011-native-linear-publication.md), [ADR 016](adr/016-local-linear-monitor.md), [status](implementation-status.md) and [remaining steps](implementation-status.md).
