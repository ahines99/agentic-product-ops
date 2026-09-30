# ADR-017: Constrained documentation delivery and prompt intake

Status: accepted; exact human approval and live PER-7-to-PER-8 local execution observed.

The user supplies a prompt and repository name. Product Ops owns requirements, ambiguity,
decomposition, proposed tickets, human approval, governed Linear publication and signed export.
Delivery OS owns execution, its own inbox/outbox and evidence. Linear remains the ticket system;
the user's later mention of Jira was explicitly clarified as Linear. No UI is added.

The generic lexical risk policy deliberately holds real requests at tier 2 or 3. PER-7 says
"deletes no tracked files", which triggers that floor. Removing security words or broadly lowering
the live-input floor would make the demonstration unsafe. The general policy is unchanged.

A separate `DocumentationPolicy` supports one exact, inert Markdown addition. A trusted,
strict `DocumentationCapability` binds every source/requirement/criterion/context field, repository,
Git base, path and content. Its full canonical digest is the policy version. It permits only a
new flat `docs/*.md` file, excludes instruction files and active Markdown constructs, and grants
no model, shell, checkout, arbitrary edit, network write, push or merge authority to the executor.
The policy allows tier 1 only when the whole specification matches this installed capability.

A fresh model review produces an immutable preview. It does not change the active specification.
An authenticated, current security approver must explicitly promote that exact preview; promotion
creates a new revision and records the human decision. Ordinary exact-specification/plan approval
is still required before publication. One explicit human response may authorize both concrete
commands if it names the exact preview and publication scope. No approval is inferred from a
ticket label, model finding, spend authorization or successful test.

The v2 envelope format stays unchanged. Its signed approval binds the capability through the
policy-version digest. The public verifier refuses a `doc-add-v1-*` policy without its exact
installed capability. Delivery OS additionally requires a current configured reviewer, valid
approval lifetime and unchanged generated Linear ticket. Generic consumers must not enroll
unknown policy versions. The public stateless verifier is vendored into Delivery OS with its
schema and license; Product Ops persistence and the reference SQLite consumer are not imported.

Delivery uses Git object plumbing with hooks, filters, fsmonitor and automatic maintenance
disabled. An atomic reference transaction verifies the pinned base and creates a review branch.
Retries produce the same commit. Exact blob bytes and a one-file addition are checked before
the branch is exposed. An immutable local change request records OPEN, UNMERGED, human-only
merge and no auto-merge. This is a local review mechanism, not a GitHub PR. It supplies the
"link or reference to the open change request" requested by PER-7's acceptance criterion.

This short constrained lane uses durable Product Ops decision records and Delivery's transactional
inbox/outbox; it does not enqueue a second general-agent Temporal plan. The existing Temporal
software lane and its additional human plan approval remain unchanged. Automated publication
and delivery are opt-in for explicitly enrolled specification IDs, preserving the existing
monitor's intake-only behavior and the per-issue spend boundary.

The initial actual Delivery adapter refuses multi-item DAGs and replacement revisions. Product
Ops may propose and publish multiple tickets, but downstream dependency scheduling, supersession
and cancellation propagation require their own acceptance work before automatic multi-ticket
execution can be claimed. This is a controlled integration milestone, not MVP completion.
