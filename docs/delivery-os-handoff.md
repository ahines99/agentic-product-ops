# Delivery OS handoff

Product Ops defines and governs work. Delivery OS plans, builds, tests, reviews implementation, and produces PR evidence. Product Ops never marks implementation complete; Delivery OS must not invent answers to unresolved product questions. No shared database or import of Delivery OS persistence classes is permitted.

## Version 1 artifact

[Handoff JSON Schema](../evals/schemas/Handoff.schema.json) defines an independently serializable envelope: schema version, explicit `offline_simulation` mode, the exact nested WorkSpecification, approval, publication plan, publication evidence, and artifact digest. The specification has its own content digest; operations and plan have their own digests. Handoff verification checks nested integrity and approval/specification/publication binding. The mode cannot be changed to claim a live handoff.

The digest is APO canonical JSON v1, not a signature. It detects accidental or unapproved changes relative to a trusted expected digest; someone who controls an artifact can recompute hashes. Real acceptance needs a trusted channel or signed receipt and an independently configured trusted issuer. No signing key, signature verification, or Delivery OS runtime integration exists in M0.

## Consumer rules

1. Reject unsupported schema/mode; a production consumer must reject offline simulation artifacts.
2. Verify artifact and nested digests against the trusted expected approval record.
3. Verify exact specification ID/revision, plan, operation evidence, actor and tenant authorization.
4. Reject material unknowns and any risk tier the consumer does not accept.
5. Persist immutable intake provenance in Delivery OS's own store.
6. If a newer approved revision arrives, record a new intake and explicitly invalidate prior planning assumptions; preserve old evidence and provider IDs. Never silently mutate an in-progress specification.
7. Record implementation evidence against exact requirements and criteria without changing their product meaning.

M0 defaults to accepted tiers 0 and 1. The authorization/financial revenue-export fixture is tier 2 and denied export. The separate documentation fixture is tier 1 and exercises export plus independent deserialization within this repository. That is a consumer-format fixture, not a tested cross-repository integration.

## Offline demonstration

```sh
python -m uv run product-ops demo --output out/demo-1
python -m uv run product-ops verify-handoff --input out/demo-1/handoff.simulated.json
```

Use a fresh output directory each run; artifacts use exclusive creation to avoid silent overwrite. `verify-handoff` validates integrity only, not authentic human approval. The demonstration's fixed clock and actor are explicit simulation inputs. Publication receipts and old revisions remain attributable in artifacts; durable revision history and cross-repository invalidation are planned in M5.
