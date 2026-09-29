# ADR-010: Reviewed revisions, explicit provider execution, durable authority

Status: accepted, 2026-09-29. Extends ADR-009 without changing Product Ops/Delivery OS ownership.

## Decision

Clarification answers are immutable typed receipts bound to the original question, specification, revision, digest, actor and timestamp. Model output cannot create authenticated answers. Reanalysis preserves original requirements and questions, permits additive requirements with clarification provenance, and creates a new digest-bound proposal. Clearing a requirement's human-decision flag requires an answered associated question. Two review attempts and a shared call/cost budget bound the loop. Each failed review is retained. Concurrent activities cannot repeat unfinished role intents or write competing terminal results. Cancellation and revision checks run again before promotion.

An unrecognized, unchanged empty intake seed may undergo initial extraction exactly once. Its placeholder question describes missing offline capability, not a product decision. Initial extraction replaces that placeholder with source-bound requirements and actual questions; it cannot fabricate resolutions. New material unknowns persist as an unapproved revision. Subsequent revisions use the stricter additive rule. Initial extraction retains the seed's tier 3 classification; a model cannot reduce it. This conservatively limits automatic downstream handoff.

Responses is an optional explicitly configured adapter. Network execution requires an explicit paid-execution flag and credential; no key or model is discovered from the environment. Every call has fresh role-separated context, strict structured output, no tools and `store=false`. A token-count preflight checks the actual request against the runner's reserved input ceiling before generation. Configured prices estimate cost; they do not establish billing. Refusal, incomplete output, transport errors and uncertain outcomes hold without automatic retry. Provider schema normalization does not replace strict local contract validation. Mock transport exercises the wire format; no paid request has been made.

Pinned JWT verification can resolve subjects through durable server-owned grants. Grants bind workspace, issuer, subject, actor, roles, teams, repositories, revision and validity. Operator administration is an internal control-plane capability, never a model tool or HTTP command. Grant changes invalidate earlier grant-bound approval/clarification authority. Actor, subject, token and approval revocation are immutable receipts. Checks and revocations share a database lock at command/dispatch boundaries. Calls reserved before revocation may finish; later reservations are denied. Revoking a session token prevents future ingress with that token; revoking an actor or individual approval invalidates its publication authority. Pinned key rotation uses explicit overlap and retirement, never a token-supplied discovery URL.

GitHub reads require explicit repository mapping and immutable commit SHA. The adapter checks returned commit/tree identities and recomputes fetched Git blob hashes, bounds traversal and responses, excludes sensitive paths/content, and never executes inspected code. TLS/provider responses bind the commit-to-tree association; this is not independent commit-signature verification. Lexical metadata matching reports numerator, denominator and missing requirements without claiming semantic understanding.

## Consequences and evidence

Default API identity still denies all, publication remains disabled and readiness remains 503. Production identity/deployment choices remain external. Tests use ephemeral identity, mock HTTP, SQLite doubles and separately enabled real PostgreSQL/Temporal. No test is evidence of semantic model quality or independent human usefulness.

Protocol references: [Responses structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [token counting](https://developers.openai.com/api/docs/guides/token-counting), [GitHub commits](https://docs.github.com/en/rest/git/commits), [GitHub trees](https://docs.github.com/en/rest/git/trees).
