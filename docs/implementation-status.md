# Implementation status

Version 0.6.0, 2026-09-30. **Not an MVP.** The project's own release gate (an independently
authored and graded evaluation of at least 40 cases) has not been met. Everything below is what
exists and what has actually been exercised. Earlier status text is kept in
[history](history/implementation-status-v0.6.md).

## What works, and how it was exercised

| Capability | Evidence | Boundary |
| --- | --- | --- |
| Strict, content-hashed WorkSpecification contracts; traceability and dependency checks | Unit and property tests | Structure, not semantic correctness |
| Requirements analysis, clarification questions, decomposition and a separate reviewer with Claude | 6-call smoke (2026-09-29), PER-7 live run, [16-case evaluation](validation.md#model-evaluation) | Cases written by another Claude context; keyword checks, not human grading |
| Ambiguity gate: stop and ask instead of guessing | Evaluation: 4 of 4 ambiguous requests stopped | Over-asks: stopped on 11 of 11 well-specified requests |
| End-to-end proposal quality on general requests | Evaluation round 2: 0 of 15 answered cases reached an approvable proposal | Readiness gate rejects reviewed inferences; model output held in 7 cases. Calibration (R11) is open |
| Exact human approval bound to specification, plan, operations and expiry; renewal only after expiry | API and publisher tests | One local operator identity |
| Governed Linear publication with per-write re-authorization, one mutation gate and read-only reconciliation | PER-8 created live; mock-transport fault tests; PostgreSQL concurrency test | One live ticket |
| Signed, versioned handoff to Agentic Delivery OS | PER-7: Delivery OS verified the envelope and produced the exact approved change, which was reviewed and merged | Single-file documentation change only |
| Linear intake by signed webhook and polling; explicit supersession of edited issues | Live webhook registration and one genuine event (PER-7); API tests | Local tunnel, no uptime target |
| Durable workflow on PostgreSQL and Temporal with a transactional outbox | Service tests on real PostgreSQL 17 and a Temporal dev server, locally and in hosted CI | Development services, not production |
| Spend control reserved before every model call | All paid runs stayed under their caps | Token-based estimates; invoices not reconciled |
| Static repository inspection (no code execution) | Local snapshots used in the smoke and PER-7 | GitHub reader mock-tested only |

## Not done

**Needs an owner decision, money or another repository:**

1. A decision on whether the readiness gate may accept inferred requirements that an independent
   review has passed, followed by calibration on a held-out set (backlog R11).
2. An independent 40-case semantic study with human grading, and a usefulness or time-saving
   measurement with real users.
3. A risk policy that lets general model proposals, not only the constrained documentation lane,
   reach a Delivery OS handoff.
4. Delivery OS support for multi-ticket delivery and cross-system cancellation.
5. A per-request inference budget before continuous analysis is enabled.
6. A second approver identity and least-privilege Linear credentials for any shared deployment.
7. Any production deployment: hosting, login, TLS, monitoring and recovery objectives.

**Deliberately not built:** a command that declares an unobserved write absent and resends it,
and handoff of a publication whose writes were authorized by two different approvals. See
[ADR-021](adr/021-publication-recovery-and-write-gate.md).

## Where things are

- Current evidence and commands: [validation](validation.md).
- Live end-to-end record: [PER-7](per7-validation-record.md).
- Ordered backlog with acceptance criteria: [backlog](backlog.md).
- Decisions: [ADRs](adr/README.md). Superseded plans and versioned records: `docs/history/`.
