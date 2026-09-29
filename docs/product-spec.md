# Product specification

Agentic Product Ops governs what engineering work should exist. Agentic Delivery OS executes approved work. The public interface is a versioned WorkSpecification with exact digest and publication evidence. No shared database, internal model imports, source-code execution, code changes, PR merges, or deployments belong in Product Ops.

The authoritative original text is retained in [the supplied specification](original-initialization-specification.txt). This document describes its product boundary and how initialization maps to it; it does not replace the original.

## Users and outcome

Product and engineering leads, technical product managers, engineering managers, repository maintainers, and portfolio reviewers need decision-ready work with visible uncertainty. Each specification identifies the problem, actors, objective, explicit behavior, inferred behavior, unknowns, likely components, work boundaries, acceptance evidence, dependencies, risk, and authorization scope. Confidence is descriptive; it never resolves a human decision.

## Inputs and workflow

MVP inputs are direct natural-language prompts, pasted structured notes, optional repository selection, and optional Linear team/project context. Every source is untrusted. External URLs are not fetched automatically. Later meeting, Slack, support, incident, telemetry, and other integrations are excluded from initialization.

Requirements analysis distinguishes explicit source, repository evidence, policy, safe inference, and authenticated human clarification. Material ambiguity stops progress before proposal-ready state. Nonbehavioral formatting choices may be visible assumptions. Work decomposition maps every acceptance criterion to requirements and every work item to allowed scope. An independent reviewer detects unsupported behavior, missing criteria, hidden ambiguity, overlap, inconsistent dependencies, and publication risks. Bounded revisions return to review.

Humans approve the exact specification revision and publication plan, including workspace/team/repository scope, allowed operations, policy version, and expiry. Deterministic code rechecks scope, risk, approval and cancellation at mutation time. Unknown writes are reconciled; absence of proof is never permission to retry. Handoff contains the exact approved specification, Linear identifiers, and content digests.

## Revenue export example

The original request explicitly requires CSV, current filters, administrators only, and usage analytics. Maximum rows, oversized export behavior, event schema, sensitive-field exclusion, and performance remain unresolved. [The ambiguous fixture](../examples/ambiguous-request.md) retains all five blockers.

[The complete fixture](../examples/feature-request.md) explicitly supplies these decisions in its source text. It decomposes backend export, frontend action, authorization, analytics, and regression validation into five linked work items. This is authored fixture content, not a measured model extraction or a record of real human clarification. Repository context is absent because no real repository was inspected. The separate documentation fixture demonstrates low-risk simulated handoff; the revenue example remains tier 2 and cannot be handed off under the default tier-0/1 consumer policy.

## Contract invariants

- Strict Pydantic 2 contracts reject unknown fields and scalar coercion. Arrays become immutable tuples in memory.
- Source digest binds exact UTF-8 intake bytes. S0 stores the complete source; additional source statements must be exact excerpts.
- Provenance references, globally unique IDs, criterion-to-requirement mappings, coverage, and acyclic local dependencies are validated.
- A WorkSpecification includes unresolved questions, visible assumptions, optional advisory repository evidence, deterministic risk assessment, work items, approval policy, and producer metadata.
- Acceptance criteria carry explicit provenance and required verification evidence. Generated criteria are requirements for evidence, not proof of correctness.
- Every changed revision yields a new digest; approvals cannot carry forward automatically.

See [schemas](../evals/schemas/WorkSpecification.schema.json) and [state machine](state-machine.md).

## Non-goals and release gates

No UI, microservices, vector database, Jira/GitHub Issues publication, Slack/support/meeting integration, autonomous prioritization, customer-commitment inference, live provider execution, or productivity-savings claims are included. M0 passing tests is not MVP, portfolio, or production completion. M4 requires real authorized Linear writes with fault evidence; M5 requires real Delivery OS consumption of the approved digest; M6 requires at least 40 authored cases, measured quality, preserved failures, and a public case study.
