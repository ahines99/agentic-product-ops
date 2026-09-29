# ADR-005: Public handoff independent of Delivery OS persistence

Status: accepted, 2026-09-28.

Context: the complete revenue feature requires authorization and financial data, hence tier 2, while automatic handoff should accept only risk tiers explicitly supported by Delivery OS. A demonstration must not lower risk to appear end-to-end.

Decision: export an independently serializable version-1 envelope containing the exact approved WorkSpecification, approval, plan, and successful publication receipts with digests. The envelope is permanently labeled offline simulation in M0. Keep default consumer tiers 0 and 1; the revenue fixture is denied export. Use a separate explicit documentation request at tier 1 for the simulated handoff. Do not import or share Delivery OS persistence.

Consequences: format verification is executable, but no real Delivery OS consumer has run. M5 adds trusted transport/signing policy, real cross-repository intake, immutable revision invalidation, and provider metadata binding. Product Ops never marks implementation complete. Delivery OS must reject unresolved product choices rather than reinterpret them.
