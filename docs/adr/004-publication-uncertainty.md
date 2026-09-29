# ADR-004: Operation intent, UNKNOWN, and simulation limits

Status: accepted, 2026-09-28.

Context: external creates may succeed before a response is lost. Retrying a timeout can duplicate consequential work. A broadly reusable in-memory publisher could falsely imply production safety.

Decision: build a narrowly named OfflinePublisher that accepts only the bundled FakeLinear type by design and has no network implementation. Derive stable operation keys from specification ID/revision/local ID/generation; bind rendered bodies and destinations with request and plan digests. Permit generation 1 only. Validate approved operations/count/scope before each simulated call; record UNKNOWN before dispatch and stop a batch on uncertainty. Retry reconciles exact observed content or stays UNKNOWN. No nonexistence-based recreation is implemented.

Consequences: fault tests can prove the single-process fake behavior but not durable exactly-once delivery, distributed concurrency, or real Linear reconciliation. M4 must introduce transactional intent reservation, unique constraints, leases, advancing-clock authorization checks, provider timestamps, and explicit operator resolution. A fake provider class is not a security sandbox against someone changing Python code. Default CLI and CI have no live path.
