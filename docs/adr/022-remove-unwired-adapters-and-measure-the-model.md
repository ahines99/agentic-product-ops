# ADR-022: Remove unwired adapters, consolidate records and measure the model

Status: accepted, 2026-09-30.

## Context

A review of version 0.6.0 found that the project carried code and documents that did no work,
while the part that matters most, the quality of the model's requirements analysis, had never
been measured. Specifically:

- Several adapters were exercised only by their own tests and were not wired into any runtime:
  the OpenAI Responses provider, the Linear OAuth flow with its secret vault, RS256 JWT login,
  a mock GraphQL publisher, a durable simulation publisher and an operational-metrics helper.
- Six versioned validation records, several completed plans and three layers of status text
  made the current state hard to find.
- The only semantic evidence was one smoke request and one live ticket.

## Decisions

**Remove unwired code.** The modules above and their dedicated tests are deleted, and PyJWT is
dropped as a dependency. `UnknownOutcome` stays because the native publisher uses it. Tests that
used the removed pieces as scaffolding were ported to production paths:

- Initial generation is tested with a recorded in-process provider instead of the OpenAI transport.
- The PostgreSQL concurrency test now runs eight concurrent `NativePublisher` instances with a frozen
  clock and requires exactly one send per operation, exercising the exclusive dispatch authority
  from ADR-021 against real row locks.
- Authority tests keep the grant and scope checks; token revocation is covered by the local
  operator tests.

Git history keeps the removed code. If a hosted deployment is chosen later, least-privilege Linear
OAuth and multi-user login should be rebuilt against that deployment's actual identity provider
rather than revived unchanged.

**Keep the core infrastructure.** PostgreSQL, Temporal, the outbox, signed handoffs and encrypted
storage stay. They carry the project's central claim that model output never reaches an external
write without exact, current human authority, and they are exercised by live and service tests.

**Consolidate documents.** Superseded plans and versioned validation records move to
`docs/history/` unchanged. `docs/implementation-status.md` is rewritten as the single current
status, and `docs/validation.md` summarizes current evidence.

**Measure the model.** `scripts/run_model_eval.py` runs real initial analysis on an authored case
file and scores it with the deterministic checks in `evaluation/model_eval.py`. It requires an
explicit flag, a key file and a hard spend cap that is reserved durably before each call, and it
replays finished cases instead of paying again. The cases were written in a separate model context
that saw no outputs. The report keeps every raw proposal and every failure.

## Consequences

- The evaluation is keyword-based and its cases were written by another Claude context, so it is
  evidence of behaviour, not an independent semantic adjudication. The 40-case independent study
  in the evaluation kit remains the MVP gate.
- Anyone who needs OAuth, JWT or an OpenAI provider must rebuild them.
