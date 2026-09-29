# Security model

## Trust boundaries

Requests, notes, repository bytes, issue comments and model output are untrusted data. They cannot authenticate actors, approve work, choose policy, widen tenant/team/repository scope, downgrade risk or obtain mutation capabilities. Deterministic code retains authority. This application is not a sandbox against an operator who can modify its own code/database.

| Threat | Implemented control | Remaining boundary |
| --- | --- | --- |
| Source injection | Exact fixture routing; separate role contexts; strict schemas; unknowns hold | No live model or independent semantic evaluation |
| Repository injection | Bounded static reads, links excluded, document/config bodies omitted, advisory evidence cannot change policy | Metadata names are still untrusted; no semantic relevance proof |
| Secret exposure | Hidden/excluded paths, sensitive-content heuristics, no raw file bodies in model context, redacted errors | Heuristics are not complete DLP; filesystem checks are not an OS sandbox |
| Fabricated citations | Exact source excerpts, validated refs, digested snapshots, unchanged repository-context check | Matching references does not prove semantic truth |
| Hidden ambiguity | Blocking questions, human-decision flags and inferred-behavior gates | General ambiguity detection needs evaluated inference |
| Forged clarification | Test-authenticated receipt, immutable new revision, mandatory reanalysis hold | Production identity and resumed analysis not connected |
| Stale or forged approval | Exact ID/revision/digest/plan/scope/actor/policy/time/count checks, immutable decision per revision | Test identity only; default ingress denies all |
| Unauthorized destination | Trusted scope allowlists, canonical plan, per-operation authorization | Live metadata and tenant OAuth absent |
| Risk laundering | Lexical floor includes resolutions; work risk cannot undercut spec | Paraphrases can evade lexical rules; adjudicated semantic risk needed |
| Duplicate or lost writes | Durable unique keys, content conflicts, UNKNOWN before dispatch, reconcile-or-hold after restart | Fake provider only; no live exactly-once claim |
| Artifact tampering | Nested digests, stored-read integrity checks, PostgreSQL immutable-record triggers | Hashes are not signatures; privileged database operators remain trusted |
| Resource abuse | Bounded API body stream, CLI files, model calls/bytes/cost, repository entries/files/depth/bytes/time | Production rate limits/concurrency quotas absent |
| Cancellation race | Persisted cancellation under reservation lock; Temporal workflow cancellation signal | Already reserved calls may finish; no HTTP revocation service |

## Approval and write boundary

Approval is a structured receipt, not a boolean. It binds actor, decision, exact specification ID/revision/digest, workspace, teams/repositories, plan digest, ordered operation keys, expiry, mutation count and policy version. High-risk work also needs a configured security approver. Confidence cannot resolve a human decision. Policy comes from trusted configuration, never source text.

FastAPI takes identity from its authenticator, not a request-supplied actor. Default authentication denies every command. An optional pinned-key JWT adapter verifies RS256 issuer/audience/time/subject/token-ID claims and asks a mandatory revocation callback; backend failure denies. Trusted subject mapping supplies roles/scope, ignoring those token claims as authority. Remote-key headers and algorithm changes are rejected. Only ephemeral test signatures have been exercised; there is no deployed identity service. There is no arbitrary state patch, approval-by-comment or automatic publication. Readiness and publish return 503.

Approval additionally requires persisted proposal/review evidence for the exact specification and policy. Clarification receipts create new revisions and outbox starts, but cannot grant their own approval or invent acceptance criteria. API cancellation commits receipt, control, audit and signal atomically. The control row serializes approval/clarification with role/publication reservation. Previously committed reservations may finish; future ones fail. Token revocation alone does not revoke existing approval receipts; specification cancellation is the explicit invalidation path.

PostgreSQL commits immutable command results, artifacts, audit metadata and workflow outbox jobs together. Triggers reject UPDATE/DELETE of immutable records. Tenant-scoped reads verify stored digests. Temporal decision signals contain only receipt references; activities load and revalidate them against current specification/policy/time. Lost start/signal acknowledgements reconcile exact workflow/receipt identity.

## External write safety

Stable logical identity is SHA-256 of `[specification_id, revision, local_item_id, generation]`; only generation 1 is currently supported. A reused key with changed request content conflicts. The original in-memory demo uses an explicit fixed clock and loses its records on process exit. It must never be attached to a real provider.

The durable simulation persists UNKNOWN before dispatch. A unique operation and locked control row serialize reservation/cancellation. Authorization uses an advancing clock before each operation. A crash after reservation but before a send can remain uncertain; absent lookup is not proof of nonexistence. Reconciliation verifies exact identity/content or holds, never blindly recreates. Cancellation prevents new reservations but does not roll back an already reserved call. External writes are not exposed by the API or Temporal workflow.

Live publication still requires real actor/OAuth scope and revocation checks, tenant metadata, provider-backed reconciliation and controlled fault tests. Mock GraphQL and GitHub adapters reject network transports. Webhooks remain absent until signature verification over original bounded bytes, durable receipt/deduplication, validation and asynchronous processing are implemented.

## Dependency and local environment hygiene

`uv.lock` pins runtime/development/build dependencies. CI uv and action revisions are pinned. Builds use the locked backend, compare repeated artifact bytes, and install the wheel outside the checkout with hash-locked dependencies. Secret scanning covers tracked and nonignored untracked files, default detectors, one worker, and no network verification. Only exact JSON digest fields containing 64 lowercase hexadecimal characters have a reviewed nonsecret exception. Fixtures are not excluded.

Local PostgreSQL trust authentication is restricted to an ephemeral loopback test server, with test database names checked before destructive migration tests. It is not a deployment authentication recommendation. Temporal tests use a local development server. Downloaded Temporal tooling is checked against published release SHA-256 values. Docker templates remain untested; images use fixed tags rather than verified immutable digests. Public dependency downloads/auditing use network access, but no model/provider money or live credentials are required.

No inspected repository is imported, executed, installed, or allowed to supply a shell command or source URL. AST parsing is advisory and bounded by file limits. File identity checks reduce normal races but do not provide hostile-filesystem isolation. Production tracing, retention, signing, identity/revocation and incident operations remain documented gaps.
