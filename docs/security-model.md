# Security model

## Trust boundaries

User requests, pasted notes, repository content, future issue comments, and model output are untrusted data. They cannot select policy, authenticate an actor, approve a specification, widen workspace/team/project/repository scope, downgrade risk, grant tool capabilities, or request secret disclosure. M0 has no network client, secret configuration, model runtime, or repository executor. The local operator and Python process can modify code and files; M0 is not a sandbox against a malicious operator.

| Threat | Implemented control | Remaining boundary |
| --- | --- | --- |
| Source instruction injection | Exact-fixture digest routing; unknown input holds for clarification | Real model role isolation/evaluation in M1 |
| Malicious repository text | Advisory typed evidence cannot alter server policy; regression test | Actual bounded repository reader in M2 |
| Fabricated citations | Exact intake excerpts and provenance reference validation | Semantic truth and real snapshot verification not implemented |
| Hidden ambiguity | Blocking questions, human-decision flags, inferred behavior checks | General semantic ambiguity detection needs model + independent review |
| Forged clarification | Resolved proposal text cannot grant authority; M0 gate denies it | Authenticated clarification receipts and immutable revision service |
| Stale/forged approval | ID/revision/digest/plan/scope/actor/policy/time/count validation | Actor argument is simulated, not authentication |
| Model-chosen unauthorized team | Server-side allowlists and exact approved operation plan | Live metadata validation and tenant-scoped OAuth |
| Low-risk laundering | Conservative text-derived risk floor; work risk cannot undercut spec | Lexical rules incomplete; high-risk semantic review required |
| Duplicate or lost writes | Stable keys; conflicting digests rejected; UNKNOWN and reconcile-or-hold | Durable intent, concurrency, provider reconciliation in M4 |
| Source text in Markdown | HTML/Markdown escaping and body bounds | Provider-specific formatting must be validated before live release |
| Secret leakage through errors | Structured fixed error messages omit Pydantic input values | Production structured redaction and token storage |
| Artifact tampering | Nested digests and exact approved-spec binding | Signatures/authentication and trusted transport not implemented |
| Resource abuse | CLI byte limits, strict field limits, bounded operation count | Service-level quotas, concurrency and request budgets |
| Cancellation | Fake publisher stops future fake calls; terminal lifecycle cancellation | Durable acceptance/dispatch race coordination in Temporal |

## Approval and write boundary

Approval is a structured receipt, never a boolean. It binds actor, decision, specification ID/revision/digest, workspace, exact teams/repositories, plan digest, ordered operation keys, expiry, mutation count, and policy version. High-risk proposals also require a configured security approver. Confidence never supersedes human decisions. Policy is supplied by trusted code, not parsed from source content.

The offline simulator checks authorization for each fake operation using an explicitly supplied test clock. A live service must use a trusted advancing clock and recheck expiry, revocation, cancellation, tenant scope, and remaining mutation budget immediately before each network dispatch. M0 does not authenticate the simulated actor or guarantee real-time expiry during a batch. Live approval/publication/handoff lifecycle transitions are disabled.

## External write safety

Stable logical identity is SHA-256 of `[specification_id, revision, local_item_id, generation]`. M0 supports generation 1 only. A second request with the same key and different request digest is a conflict. UNKNOWN is recorded before simulated dispatch. A lost response stops subsequent operations; retries reconcile exact operation content or remain UNKNOWN. Missing fake lookup results are not proof of nonexistence. A new publisher process loses this evidence, so it must never be used with a real provider.

Production must transactionally reserve intent and approval budget before dispatch, enforce unique operation keys and leases, retain provider request/object IDs and timestamps, and preserve old revision evidence. Cancelled in-flight remote work may still finish; cancellation prevents future dispatch rather than promising rollback. Webhooks remain disabled until signature verification, receipt persistence, deduplication, bounded bodies, asynchronous processing, explicit event validation, and fast acknowledgement are implemented.

## Dependency and repository hygiene

`uv.lock` pins runtime, development, and build-backend dependencies; CI uv and action revisions are pinned. Package verification builds without isolation using the locked backend environment. CI performs secret scanning, dependency vulnerability audit, tests, and isolated wheel installation. The secret scan includes tracked and nonignored untracked files, all default detectors, one worker, and no network verification. Only exact JSON digest fields containing 64 lowercase hexadecimal characters are excluded as reviewed nonsecret artifacts; fixtures themselves are not excluded. Scans are useful controls, not proof of absence. The foundation intentionally avoids loading `.env`, credentials, source URLs, or untrusted repository code. No live tickets or model calls are authorized by initialization.
