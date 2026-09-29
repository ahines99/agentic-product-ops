# Security model

Requests, repository content, provider responses and model output are untrusted. They cannot grant authority, change policy, resolve material ambiguity without authenticated provenance, widen scope or trigger tools. The application is not a sandbox against an operator who can replace its code or database.

| Threat | Exercised control | Remaining limit |
| --- | --- | --- |
| Prompt/repository injection | Trusted role policy separated from untrusted payload; strict output; source and context preservation; inert bounded repository reads | Actual-model indirect injection not evaluated |
| Fabricated evidence | Exact excerpts, linked source/requirement/criterion IDs, snapshot and nested digests, unchanged context | Structural validity does not prove semantic correctness |
| Ambiguity laundering | Blocking questions, human-decision flags, authenticated answer receipts, additive revisions and distinct review | No independent semantic accuracy evidence |
| Stale/forged approval | Exact revision/spec/plan/scope/count/policy/expiry; stored review; actor grant binding | Deployment identity and provisioning are not configured |
| Revocation races | Durable actor/subject/token/approval revocation, grant revision checks, shared locks and per-dispatch authority | In-flight writes cannot be rolled back by cancellation |
| Wrong destination | Fixed provider origins, bounded metadata, organization/app/team/project/label mapping and repository allowlists | Live provider metadata behavior remains unexercised |
| Risk laundering | Lexical floor, immutable source/risk constraints, no downgrade during revision, security approver for high risk | Lexical checks are incomplete; general new intake stays tier 3 |
| Duplicate/uncertain mutation | Unique operation identity, approved deterministic UUID, UNKNOWN before send, exact reconciliation | No blind retry after absence; no provider-wide exactly-once claim |
| Secret/artifact exposure | SecretStr, redacted errors, heuristic exclusion, injected AES-GCM keys and authenticated row metadata | No complete DLP or deployed key custody; command/audit metadata needs DB protection |
| Tampering | Canonical nested digests, read checks, immutable PostgreSQL triggers, Ed25519 public handoff | Privileged operators remain trusted; signature alone does not prove human intent |
| Resource abuse | Input/response/file/entry/depth/time/token/call/cost/export bounds; no model tools | Production rate limits and tenant concurrency quotas not configured |

## Authority

Approval is an immutable receipt, never a boolean. It binds the exact specification and ordered plan, authenticated actor, workspace/team/repository scope, allowed mutation count and expiration. Native plan digest is an explicit approval input. Source text cannot choose approvers. Clarification receipts bind the original question, base digest/revision, answer, actor and timestamp; changed grants or revocation invalidate their authority.

Pinned RS256 JWT verification checks issuer, audience, subject, token ID, time and permitted keys. Durable grants supply roles and destinations. Untrusted role claims, remote key headers and algorithm changes are rejected. Verification/revocation failure denies. Grant/key rotation and revocation are exercised with ephemeral identities; no real login or identity provider is configured. Token revocation denies subsequent use of that token; explicit actor/subject/approval revocation or grant change invalidates existing bound authority. Public grant-administration endpoints do not exist.

PostgreSQL immutable triggers protect artifacts, commands and audits. Workspace-scoped reads recheck digests. Outbox operations carry stored receipt IDs. Cancellation and authority updates serialize with new reservations; a call already dispatched can still complete. Native service captures an authorization receipt immediately before mutation after metadata checks; late success is evidence, not permission for another write.

## External boundary

Responses, GitHub, OAuth and native Linear clients fix origins, disable redirects/environment proxies, bound responses and require explicit network/mutation configuration. Model transport also requires explicit paid-execution enablement. None is enabled by default. OAuth uses app-actor PKCE, one-use state and encrypted verifier/access/refresh records. Exchange/refresh intent precedes HTTP; uncertain token outcomes hold for reauthorization. Issue creation can use `issues:create`; native relations require broader `write`, so scope expansion must be an explicit deployment decision. Projects and labels must already exist; epic/project creation and webhooks are unavailable.

UNKNOWN is durable before a mutation. Reconciliation requires exact approved target identity/content and saved dispatch authority. Missing/conflicting lookup stays held without recreation. Models have no mutation tool. The HTTP publication endpoint remains disabled regardless of credential presence elsewhere on disk.

## Storage and environment

Optional Store encryption binds workspace, kind, ID and revision as AES-GCM authenticated data. Wrong keys or swapped ciphertext fail. Configured encryption refuses legacy plaintext; production migration/key lifecycle remains external. Only raw role requests/responses can expire from reads, preserving approved contracts and audit lineage. Expiry is not physical erasure. OAuth vault rotation retains old immutable ciphertext. Public handoffs contain approved source content and require appropriate distribution controls.

Locked dependencies, pinned CI action/uv versions and container digests, byte-identical rebuilds, hash-locked clean-wheel installation, dependency audit and secret scanning are required gates. Scanning covers tracked and nonignored untracked files; only precisely defined 64-character digest fields have a nonsecret exception. Public keys/signatures are not credentials. No live key was copied from the adjacent repository.

Local development PostgreSQL trust authentication is loopback-only and test databases are explicitly named. Restore creates and drops only its owned random test database. Temporal runs in development mode. Production DB authentication/TLS, workload isolation, key custody, tracing, incident response and physical-retention operations remain deployment acceptance requirements. See [ADR-013](adr/013-operational-artifacts-and-evaluation.md).
