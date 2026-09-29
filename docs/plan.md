# Initialization plan and scope

Source of truth: [original initialization specification](original-initialization-specification.txt), supplied 2026-09-28. Its M0 instructions define the executable scope. The requested boundary remains:

Natural-language intent → extracted requirements → explicit ambiguity → repository-aware decomposition → acceptance criteria → proposed Linear work → human approval → governed publication → versioned Delivery OS handoff.

M0 implements the contract and deterministic control foundation and simulates later boundaries. General analysis, actual repository grounding, identity authentication, persistence, live publication, and cross-repository consumption are future work. This interpretation resolves the broad vertical-slice vision against the explicit initialization instructions without pretending fixture routing completes the product.

Completed sequence:

1. Read supplied specification and inspect empty workspace.
2. Create the Python modular-monolith package and locked build/tool dependencies.
3. Define strict immutable public contracts, canonical digests, traceability and dependency validation.
4. Implement fail-closed lifecycle, risk floors, authorization scopes, and approval validation.
5. Add exact-fixture draft CLI, clarification fallback, and fake publication/handoff harness.
6. Exercise adversarial inputs, stale approval, duplicate commands, response loss, and cancellation.
7. Freeze 15 same-context authored routing cases and preserve the first report.
8. Document architecture, threats, lifecycle, integrations, ADRs, status, and dependency-ordered backlog.
9. Run local checks on supported Python versions, isolated wheel smoke, secret/dependency checks, and deterministic regeneration; commit the clean foundation.

Evidence and actual outcomes are recorded in [implementation status](implementation-status.md). Future gates remain in [backlog](backlog.md). No credentials or paid APIs are needed for M0.

## Authorized offline continuation

The subsequent instruction to continue without user input authorized a service expansion: recorded analyst/decomposer/reviewer contexts, bounded local repository metadata, mock GitHub/GraphQL contracts, test-authenticated command ingress, PostgreSQL migrations/immutable records/outbox, Temporal approval waiting and replay, durable fake publication, and a larger routing corpus. These now have executable local evidence. [ADR-007](adr/007-offline-service-expansion.md) supersedes the original runtime deferral; [offline expansion](offline-expansion.md) records commands and results. Live inference, identity, Linear publication and real Delivery OS intake remain distinct unfinished gates, not implied by local green tests.
