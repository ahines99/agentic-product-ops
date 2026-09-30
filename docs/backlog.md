# Dependency-ordered implementation backlog

The later [PER-7 live integration record](per7-validation-record.md) supersedes historical
claims below about missing human approval, genuine Linear events, live publication and actual
Delivery acceptance. The [current continuation](prompt-to-delivery.md#dependency-ordered-continuation)
tracks the remaining multi-ticket, revision, budget and independent acceptance work.

Local prompt-entry continuation (dependency order):

| ID | Work | Depends on | Status | Acceptance criteria |
| --- | --- | --- | --- | --- |
| C01 | Local prompt/repository console and versioned execution briefs | Prompt intake and native plans | Implemented; browser visual acceptance open | Scoped sessions, held-state feedback, exact-plan approval, per-item coverage and unchanged legacy payloads pass HTTP/contract tests; packaged assets are present. |
| C02 | Budget allocation and policy-isolated worker routing | C01 | Open | A newly authorized per-request allowance is reserved before inference; two profiles cannot consume each other's work; restart/retry preserves the same reservation. |
| C03 | Independent detailed-ticket acceptance | C02 | Open | Fresh authorized prompts produce repository-grounded, implementable scope and evidence; independent cases detect unsupported requirements and unresolved ambiguity; first failures are preserved. |
| C04 | Approved multi-item delivery and supersession | C03, existing signed handoff | Open | Atomic admission, durable dependency scheduling and cancellation/revision invalidation pass real producer/consumer checks without duplicate starts. |
| C05 | Hosted review and operational acceptance | C04 | Open | Explicitly authorized GitHub App publication, human merge, hosted CI and independent product acceptance are evidenced. |

No live Linear tickets were created. IDs are local planning identifiers. Version 0.4 completed credential-free engineering; version 0.5 adds the local pilot rows below; `Offline done` does not mean live, independent semantic, human or production acceptance. Dependencies refer to earlier work and cannot be skipped because a schema exists. Rows marked partial/open retain explicit external acceptance work; see [remaining sequence](remaining-work.md) and [validation](v04-validation-record.md).

| ID | Work / milestone | Depends on | Status | Acceptance criteria |
| --- | --- | --- | --- | --- |
| B01 | Project/domain naming, M0 | — | Done M0 | Package/CLI use Product Ops name; docs preserve Delivery OS execution boundary. |
| B02 | Strict WorkSpecification, M0 | B01 | Done M0 | Unknown fields/coercion rejected; version, IDs, nested immutable records and JSON round trip tested. |
| B03 | Canonical digest, M0 | B02 | Done M0 | Stable canonical vectors; changed content/revision invalidates digest; self-field excluded only. |
| B04 | Intake source model, M0 | B03 | Done M0 | Exact UTF-8 source digest and immutable intake validated; incorrect source rejected. |
| B05 | Requirements provenance, M0 | B04 | Done M0 | Provenance-specific refs validated; exact source excerpts; fabricated refs rejected. |
| B06 | Unresolved questions, M0 | B05 | Done M0 | Complete answer/actor/time tuple required; blockers hold; confidence never overrides decision. |
| B07 | Risk policy, M0/M1 | B06 | Partial acceptance | Lexical floor and conservative general-intake tier 3 exercised; independently adjudicated semantic risk must still avoid underclassification. |
| B08 | Lifecycle, M0/M1 | B07 | Offline done; deployed acceptance open | Deterministic graph, real Temporal history/waits/restart/replay, bounded reviewed revisions and cancellation exercised; deployed end-to-end acceptance remains. |
| B09 | Approval contract, M0/M1 | B03, B08 | Offline done; identity acceptance open | Exact revision/digest/plan/scope/expiry/count, authenticated ephemeral identity, durable grants and approval revocation exercised; local operator identity configured in P01; real human approval and deployment-specific acceptance remain. |
| B10 | Audit schema, M0/M1 | B09 | Offline done | Immutable durable metadata/artifact writer, trace IDs, redacted exports and PostgreSQL trigger/restore checks exercised; production collector remains external. |
| B11 | Provider-neutral model interface, M1 | B10 | Local Anthropic smoke exercised; semantic acceptance open | Strict distinct roles, Responses/Anthropic token preflight and structured output, bounded transport/budget, intent/usage persistence and uncertainty holds tested; six actual Anthropic calls retained in P03/P04. |
| B12 | Requirements-analysis prompt contract, M1 | B11 | Partial acceptance | Trusted role configuration separate from source, exact provenance and authenticated additive clarification revisions tested; independent semantic accuracy required. |
| B13 | Independent review prompt contract, M1 | B12 | Partial acceptance | Distinct reviewer context, preserved blocking findings and bounded two-attempt revision tested; actual independently evaluated inference required. |
| B14 | Model cost/usage receipts, M1 | B11 | Offline done; billing acceptance open | Durable usage/request/model/prompt IDs, decimal estimates, token-preflight boundary and separate role duration implemented; six live Anthropic calls and token receipts recorded in P03; actual billing reconciliation remains open. |
| B15 | Evaluation fixture format, M0 | B05, B06 | Done M0 | Strict source/category/expectation/authorship schema and digest verification exercised. |
| B16 | First 15 authored cases, M0/M1 | B15 | Partial | 15 same-context M0 routing cases exist; independently authored semantic gold cases required before M1 exit. |
| B17 | Corpus freeze/report preservation, M0 | B16 | Done M0 | Digest detects corpus change; report writer refuses overwrite; first run retained. |
| B18 | Repository snapshot abstraction, M2 | B05, B17 | Offline done | Content digest pin/recheck, advisory evidence and explicit unknowns implemented; working-tree identity is not a clean Git commit. |
| B19 | Read-only local repository adapter, M2 | B18 | Offline done | Allowlisted bounded files, link/path checks, inert source tests, no execution/install/write; heuristic secret exclusion and no raw bodies in context. |
| B20 | GitHub snapshot adapter, M2 | B19 | Offline done; live read acceptance open | Fixed authenticated origin, pinned commit/tree/blob association, blob recomputation and response/path/time bounds tested with mock HTTP; authorized real read required. |
| B21 | Bounded file search, M2 | B19 | Offline done | Local byte/file/entry/depth/time bounds, exclusions, metadata search and explicit unknowns tested. |
| B22 | Python AST/import mapping, M2 | B21 | Offline done | Parse without import/exec, static names/tests/route functions and imports; dynamic edges remain unknown. |
| B23 | Repository-injection regressions, M0/M2 | B18 | Partial acceptance | Inert malicious local files, secret exclusion, static evidence constraints and mocked role injection tests pass; actual-model indirect injection/relevance evaluation required. |
| B24 | Work decomposition schema/engine, M0/M3 | B02, B13, B22, B23 | Partial acceptance | Distinct decomposition and review, bounded initial/revision paths, immutable provenance and requirements exercised; independent coherence/grounding judgment required. |
| B25 | Acceptance traceability, M0/M3 | B24 | Partial | Structural references/coverage validated; independently reviewed criteria have observable evidence and correct provenance. |
| B26 | Dependency validator, M0 | B24 | Done M0 | Unknown/self/duplicate/cyclic edges rejected; local and top-level representations agree. |
| B27 | Duplicate-ticket detector, M0/M3 | B24 | Partial | Normalized same-title detection exists; semantic overlap findings retained and independently evaluated. |
| B28 | LinearPublicationPlan, M0/M3 | B25, B26, B27 | Offline done; live acceptance open | Native issue and blocking-relation plan binds UUIDs, operation order/prerequisites/digests/budget; projects/labels preexisting, epic creation explicitly denied; actual provider acceptance required. |
| B29 | OAuth/app configuration, M4 | B09, B28 | Offline done; deployment acceptance open | App-actor PKCE, single-use state, tenant/config binding, AES-GCM token vault and uncertain exchange/refresh holds tested; local pilot selects API-key authentication instead; OAuth remains unused and optional. |
| B30 | Linear API adapter, M4 | B29 | Offline done; live acceptance open | Bounded fixed-origin metadata/create/reconcile API tested for exact content/scope and uncertain outcomes; authorized live fixture publication still required. |
| B31 | Team/project/repository/label allowlists, M0/M4 | B28, B29 | Offline done; tenant acceptance open | Current organization/app/team/project/label and repository grants rechecked immediately before mutation; mocked cross-scope failures denied; actual mapping acceptance required. |
| B32 | Publication authorization service, M4 | B09, B30, B31 | Offline done; live acceptance open | Stored review/spec/approval/plan, current grants/revocation, expiry/cancel, prerequisites and budget checked per operation with immutable dispatch snapshot; pilot publisher assembled in P05, disabled pending human approval and live authorization. |
| B33 | Stable operation keys, M0/M4 | B03, B28 | Offline done | Stable keys/UUIDs, unique durable intent and shared reservation locks; real PostgreSQL concurrency and fake/mock restart exercised; no provider-wide exactly-once claim. |
| B34 | UNKNOWN reconciliation, M4 | B30, B32, B33 | Offline done; provider acceptance open | Native ID/content/destination reconciliation requires dispatch evidence; absent/conflicting responses hold UNKNOWN without retry; actual provider lookup acceptance required. |
| B35 | External-write fault tests, M0/M4 | B34 | Offline done; live acceptance open | Mock partial batch, late response, metadata-time revocation, lost response, restart, expiry and cancellation tests pass; controlled real-provider evidence required. |
| B36 | Delivery OS handoff schema, M0/M5 | B03, B09, B28 | Offline done | Signed public v2 envelope, pinned key/digest/audience, tier/ambiguity/provenance and complete publication binding; independent reference store rejects unsafe/stale artifacts. |
| B37 | Cross-repository handoff fixture, M5 | B35, B36 | Reference done; actual consumer open | Independent no-producer-import consumer preserves original bytes and supersedes reference work; actual Delivery OS adapter must consume exact digest in its own model/store and invalidate real stale plans. |
| B38 | 40+ corpus and evaluation, M6 | B13, B14, B17, B24, B37 | External acceptance open | At least 40 separately authored/adjudicated semantic cases across ten categories with actual configs/first failures/usage; 45 routing cases and two scoring templates do not qualify. |
| B39 | Evaluation report generator, M0/M6 | B17, B38 | Offline tooling done; study open | Frozen semantic contracts, explicit prediction/criterion judgments, denominators/category reports, preserved first attempts and optional signed attestations exercised; independent study/rubrics remain external. |
| B40 | Portfolio release documentation, M6 | B39 | Offline case study done; release acceptance open | Reproducible honest native-mock/signed-reference case study documented; publish/tag acceptance release only after quality/live/human milestones and destination authorization. |

## Infrastructure prerequisites

| ID | Task | Depends on | Offline evidence and remaining acceptance criteria |
| --- | --- | --- | --- |
| I01 | FastAPI and identity | B02-B10 | Bounded authenticated/idempotent commands, durable grants/revocation and ephemeral JWTs pass; deployed human identity and factory configuration still required. |
| I02 | PostgreSQL/SQLAlchemy/Alembic | I01 | Real migrations, immutable triggers, command/operation concurrency, backup/restore fingerprints and restored-trigger denial pass; production DB/TLS/ACL acceptance remains. |
| I03 | Temporal orchestration | I02 | Real approval wait/restart/replay, digest-bound revised analysis, receipt validation, timeout and cancellation pass; automatic live publication assembly remains disabled. |
| I04 | Pinned container stack and CI | I03 | Digest-pinned Docker/Compose build/start/probe pass; API healthy but intentionally unready/default deny. Actions matrix/service/container jobs supplied; remote configured; hosted run requires an authorized push. |
| I05 | Artifacts and observability | I02, I03, B14 | Optional AES-GCM artifacts, raw-role access expiry, immutable metadata manifest and separate role/publication durations tested; production key custody, physical purge and collector/SLO acceptance remain. |

## Milestone exits

M0: package builds, lint/type/test pass, typed offline CLI works without API calls. **Complete.**

M1: frozen independently authored requirements/ambiguity corpus, explicit clarifications, preserved unsupported findings and durable authenticated lifecycle. Engineering exists; local Anthropic smoke and local identity exercised; independent semantic acceptance remains open.

M2: pinned read-only repository context and injection tests. Offline boundaries complete; actual-provider indirect injection and semantic grounding acceptance remain open.

M3: coherent grounded decomposition with traceable criteria. Structural/revision/native-plan tooling complete; independent quality acceptance remains open.

M4: actual approved Linear creation with durable idempotency/fault evidence. Mock-tested implementation complete; live authorization/acceptance absent.

M5: actual exact-digest Delivery OS intake in its own persistence. Signed public contract/reference consumer complete; actual downstream integration absent.

M6: 40+ independent semantic evaluations, measured claims/usefulness, case study and tagged portfolio release. Scoring/case-study engineering complete; actual study, human evidence and release acceptance absent.


## Local pilot continuation (v0.5)

These dependency-ordered rows update the earlier offline evidence with actual pilot scope. A completed engineering row does not close the corresponding live/semantic milestone.

| ID | Work | Depends on | Status | Acceptance criteria/evidence |
| --- | --- | --- | --- | --- |
| P01 | Private local operator/profile | I01, I02, B09 | Exercised locally | Explicit revocable operator grant, owner-private files, encrypted separate pilot DB, loopback scope; no key in tracked example. |
| P02 | Ticket-defined repository | P01, B19, B31 | Local read exercised | Both policy/grant opt in; one absolute Git path or fixed-host pinned GitHub selection; exact snapshot binds work; no code execution. GitHub live acceptance open. |
| P03 | Anthropic aggregate allowance | P01, B11, B14 | Live smoke exercised | Explicit Opus 5.5 model, token preflight, no tools/retries, durable reservations across restart/concurrency and immutable terms. Six calls under $10; usage retained, billing unverified. |
| P04 | General intake and separate review | P02, P03, B12, B13 | Engineering smoke passed | Two first failures retained, provenance/digest constraints remain strict, final proposal and native plan generated; no automatic approval. Independent semantic acceptance open. |
| P05 | API-key native publisher assembly | P01, P04, B30-B35 | Assembled; writes not exercised | Live read-only org/actor/team discovery passed. Publication switch remains off; exact approval, policy, grant and per-write rechecks required. Actual mutation/reconciliation acceptance remains open. |
| P06 | Explicit human risk reassessment | P04, B07, B09 | Recorded-provider tests pass | Security operator supplies exact base digest/tier/reason; floor cannot be lowered; immutable new revision and fresh reviewer; stale/revoked/cancelled inputs denied; no reused approval. Live human decision open. |
| P07 | Independent evaluation kit | P04, B38, B39 | Protocol ready; study open | Original ten categories restored; at least 40 independently authored frozen cases plus all-attempt adjudications and separately authorized inference required. Same-context smoke does not qualify. |
| P08 | Release checks and runbook | P05-P07, I04 | Local checks recorded | Both Pythons, services, build/wheel/reproducibility/docs/secrets; exact local setup/demo and limitations documented. Remote configured, no authorized push or hosted result. |
| P09 | Issue plus repository entry point | P01, P02, P04 | Implemented; live issue acceptance open | Fixed-origin read-only source; tenant/actor/team validation; unambiguous short local name; atomic source/spec binding; stable per-operator issue replay; edited source denied at approval and each write; disabled inference queues nothing. |
| P10 | Continuous Linear enrollment | P09 | Monitoring acceptance implemented; real issue observation and supersession open | Signed webhook plus bounded durable polling; explicit enrollment excludes old backlog/generated outputs; encrypted inbox/cursor/retry history; live owned registration and synthetic delivery/restart checks; no model spending. Source edits hold pending governed supersession. Continuing-inference mode requires separate implementation/authorization. |
| P11 | Approved work reaches Delivery OS | P05, P10, B36 | Open; agent-owned implementation | Actual consumer validates pinned signing identity, audience, exact digest, freshness/revocation and scope; separate persistence; duplicate/replayed handoffs rejected; human merge boundary retained; exercise real consumer before claiming completion. |
| P12 | Unattended eligibility policy | P07, P10, P11 | Open; explicit policy decision required | Independently evaluated eligibility, ambiguity/risk holds, bounded spend, revocation and incident recovery; automatic approval unavailable until an explicit policy authorizes its scope; an issue alone never supplies that policy. |
