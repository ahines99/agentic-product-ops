# Linear integration

Version 0.4 implements native GraphQL planning, OAuth PKCE/encrypted token storage and durable publication orchestration, exercised with mock HTTP transport. No live request or ticket creation has occurred. The HTTP publish route remains disabled. The original in-memory demo and `FAKE-` records remain explicitly simulated.

## Identity and scope

Trusted configuration maps local workspace/team/project/label aliases to provider UUIDs and binds the Linear organization and app actor. The adapter reads current organization, viewer, team, project team membership and label scope before mutation. Source text cannot change these bindings. OAuth uses app actor, PKCE S256, one-use state, fixed redirect/origin and encrypted secrets. Durable exchange/refresh intent prevents uncertain automatic repeats. Default OAuth scope is read plus issue creation; native relation writes require `write` and an explicit operator decision.

Provider facts were checked against [OAuth](https://linear.app/developers/oauth-2-0-authentication), [app actor authorization](https://linear.app/developers/oauth-actor-authorization), [GraphQL](https://linear.app/developers/graphql), and the official SDK schema during implementation. Mock conformance is not live compatibility acceptance.

## Native plan v2

`build_native_plan` deterministically renders approved issues and blocking issue relations. All mutations, including relations, count against the approved budget and ordered operation keys. Issue prerequisites precede relations. Native target UUIDs derive from stable operation identity; content, destination, generation and order are digest-bound. Only generation 1 is supported. Projects/labels are preexisting allowlisted metadata. Epics/project creation, parent hierarchy and semantic duplicate detection are not implemented.

Descriptions contain objective, context, requirements, acceptance criteria, dependencies, risks, repository context, open questions and exact attribution. Markdown is rendered as inert content. The reviewer approves the exact spec and plan; there is no second content generation at send time. GET plan supports inspection; native approval requires that digest.

## Durable authorization and uncertainty

NativePublisher requires stored current specification, passing review, exact approval and plan, and the same durable Authority store. Per-operation gates recheck revision, expiration, cancellation, revocation, scope, prerequisite evidence and mutation budget. UNKNOWN is committed before HTTP. Metadata checks precede a final authority callback, which records an immutable dispatch authorization snapshot. A late success is saved, but cannot permit subsequent writes after expiry or revocation.

Reconciliation reads exact deterministic target IDs and compares complete content/destination/labels or relation direction. It requires saved dispatch authority. Missing objects are not proof of nonexistence; absence, conflicts, timeouts and uncertain authorization remain UNKNOWN. No blind recreation, automatic paid retry, or provider-wide exactly-once guarantee is claimed. Tests cover restart/lost response, partial batches, metadata-time revocation, late completion, expiry, native dependencies and held conflicts.

The separate API/Temporal default runtime never calls NativePublisher automatically. Enabling a live assembly requires a deployment identity/scope decision, explicit write authorization and controlled acceptance evidence. The user-identified adjacent repository contains credentials; that does not authorize reusing them here or issuing tickets.

Webhooks and hosted MCP publication are not implemented. Native handoff consumes successful publication receipts without executing delivery work. See [ADR-011](adr/011-native-linear-publication.md), [status](implementation-status.md) and [remaining steps](remaining-work.md).
