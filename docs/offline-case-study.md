# Offline case study: approved documentation work

This reproducible case study uses the low-risk documentation request in [handoff-request.md](../examples/handoff-request.md). The business intent is decomposed into documented work with traceable acceptance evidence. It deliberately avoids claiming revenue-export tier-2 work is safe for the tier-0/1 handoff consumer.

1. Intake persists the exact request and specification under an ephemeral authenticated test actor. Authored analyst/decomposer/reviewer results are saved as immutable evidence; deterministic scope, ambiguity, risk and coverage checks must pass.
2. The native plan renders exact issues and dependency relations, including every mutation in its digest and count. The test actor explicitly approves that plan and specification revision. This is simulated human input, not an actual human-review study.
3. NativePublisher records intent and UNKNOWN before dispatch, checks current scope/identity/expiry/cancellation, then invokes mock GraphQL. Fault variants exercise lost responses, held absence, exact reconciliation, revocation during metadata reads, partial batches and late completion without additional authority.
4. The signed exporter loads exact stored approval/plan/receipts and historical dispatch evidence. An ephemeral Ed25519 key signs the public v2 envelope; production key custody is not configured.
5. An independently imported reference consumer verifies a pinned test key, audience, exact expected digest, tier, source/traceability and publication binding. It retains original artifact bytes in its own SQLite store. A newer revision supersedes old reference work; stale revisions and re-signed unsafe artifacts fail. No downstream implementation executes.

```sh
python -m uv run pytest tests/integration/test_native_publication.py tests/integration/test_signed_handoff.py --no-cov -q
python -m uv run pytest tests/integration/test_revisions.py tests/integration/test_initial_generation.py --no-cov -q
python -m uv run product-ops demo --output out/case-study-v1
python -m uv run product-ops verify-handoff --input out/case-study-v1/handoff.simulated.json
```

The first test command exercises native mock publication and signed v2 reference intake. The CLI commands are the simpler unsigned v1 demo, clearly labeled simulation. Clarification tests separately show an ambiguous request remaining held until an authenticated answer and fresh bounded review produce a new revision; old approval cannot authorize it. The semantic scoring example retains an intentionally failed first attempt to demonstrate reporting discipline.

Actual paid inference, live Linear, actual Delivery OS intake and human usefulness are unmeasured. This case demonstrates enforceable offline boundaries and reproducible component behavior, not production or MVP acceptance.
