# ADR 015: Issue-driven intake with separate approval authority

Status: Accepted, 2026-09-29.

The operator wants to supply a basic Linear issue and a repository name, with Product Ops handling intake and planning. Terminal commands, copied JSON and process management are implementation responsibilities, not the intended product interaction. Creating an issue is not approval of a specification that does not yet exist.

## Decision

Add authenticated `POST /v1/intakes/linear` and the operator automation command `run-issue`. A fixed read-only GraphQL query resolves an identifier, UUID or exact Linear issue URL; URL text never becomes a network destination. Organization, API-key actor, issue identity and team are verified. A short repository name resolves to exactly one Git directory under operator-configured absolute roots. Missing, conflicting, ambiguous or linked paths hold. An issue may include `Repository: name`; an explicit name must agree with that declaration.

The source snapshot and initial specification commit in the same Product Ops transaction. Within the current single-operator pilot, a stable issue-ID command key deduplicates retries. Source content and provider update time are bound to that command. Editing an enrolled issue conflicts instead of overwriting an existing specification. Source revalidation is required before approval, explicit analysis, publication, each native mutation dispatch and signed handoff. Unavailable sources fail closed. This adds freshness checks, not an atomic transaction with Linear: an external edit can race the final check. No exactly-once cross-service claim is made.

Paid execution disabled means intake is stored without an outbox dispatch. Explicit analysis can resume that intake after separately authorized execution is configured. Replaying the intake returns its original receipt; it does not start a second workflow. Issue text cannot enable inference, increase a budget, lower risk, grant approval or authorize publication. Generic intake still starts at tier 3. Source edits require a future governed supersession flow or explicit operator resolution; automatic edit-to-revision conversion is not implemented.

The `run` launcher owns the API and worker together and closes its sibling task when either exits. Existing PostgreSQL and Temporal remain dependencies. Service installation and reboot recovery are not claimed.

## Consequences and next boundary

The interaction is issue plus repository, followed only by substantive ambiguity answers and the existing approval decision. Product Ops defines approved work; Delivery OS executes it using its own persistence. This release does not add a watcher, webhook ingress, automatic approval, a Delivery OS consumer or merge authority.

The next automation milestone must introduce durable event enrollment, authenticated delivery or bounded polling, event deduplication, source-edit supersession, generated-issue loop prevention, restart recovery and an explicit continuing spending policy before unattended operation is enabled. Eligibility for automatic approval requires a separately approved policy and evidence; source text is never that policy.

Linear's [GraphQL documentation](https://linear.app/developers/graphql) defines issue lookup by UUID or identifier. Its [rate-limit guidance](https://linear.app/developers/rate-limiting) favors webhooks for continuing updates. The local entry point uses one bounded read per submission or freshness check; it does not scan the team's backlog.
