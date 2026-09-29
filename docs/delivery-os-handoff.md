# Delivery OS handoff

Product Ops governs approved work. Delivery OS plans, implements, tests and produces PR evidence. They exchange a versioned public artifact, never internal persistence classes or a shared database. No Product Ops code marks implementation complete.

## Signed v2 public contract

The [public JSON schema](../src/product_ops_handoff/handoff-v2.schema.json) covers complete immutable WorkSpecification, approval, native publication plan, publication receipts, per-operation dispatch authority, clarification provenance, issuer/audience/key ID and expiry. Nested canonical digests and the envelope digest bind content. Ed25519 signs `AgenticProductOps/Handoff/v2` followed by a NUL byte and the ASCII payload digest. Operator-pinned issuer keys and an expected artifact digest establish the receiver's trust inputs.

The producer reloads current stored artifacts, checks authority/review, validates approval at recorded dispatch times and permits only tiers 0/1 with no material unknowns. Mock publication is explicitly marked. A late-observed successful write can be represented only with valid historical dispatch authority; it never creates fresh approval.

`product_ops_handoff.consumer.ReferenceConsumer` uses public schema plus independent digest, scope, provenance, ambiguity, risk, DAG, operation and receipt checks. It imports no `agentic_product_ops` module. It defaults to rejecting mock evidence, pins issuer/audience/key/digest, rejects expiry and stale revisions, retains original envelope bytes and records superseded reference work in its own SQLite database. It refuses a database containing unrelated tables. It never executes work.

Tests exercise independently imported consumer code, tampered and re-signed unsafe artifacts, exact byte preservation, separate persistence, stale/superseding revisions and risk/ambiguity rejection. This is an executable reference adapter, not integration into the actual adjacent Delivery OS. Actual downstream plan invalidation must be wired into that application's own execution model and independently accepted. [ADR-012](adr/012-signed-public-handoff.md) records the boundary.

## Legacy v1 demonstration

The [v1 schema](../evals/schemas/Handoff.schema.json) remains an unsigned `offline_simulation` contract. Its hashes prove integrity relative to an expected digest, not identity. The following uses a fixed-clock low-risk documentation fixture and fake publication:

```sh
python -m uv run product-ops demo --output out/demo-1
python -m uv run product-ops verify-handoff --input out/demo-1/handoff.simulated.json
python -m uv run pytest tests/integration/test_signed_handoff.py --no-cov -q
```

Use a new directory for each legacy demo. The signed integration tests use ephemeral keys and mock GraphQL, never live approval, credentials or downstream execution. The tier-2 revenue/export fixture remains ineligible for handoff. M5 requires actual Delivery OS consumption; the reference consumer cannot satisfy that exit.
