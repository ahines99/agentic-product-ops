# Agentic Product Ops

Agentic Product Ops is a governed AI-assisted requirements and work-decomposition system. It converts ambiguous product requests into evidence-linked requirements, unresolved questions, acceptance criteria, and proposed Linear work items. Humans approve the exact specification before any external write. Approved work can then be handed to Agentic Delivery OS for controlled implementation and independent verification.

**Current release: M0 offline foundation, not a completed MVP.** The executable uses authored fixtures, strict contracts, and deterministic safety gates. It does not call models, read repositories, authenticate humans, or connect to Linear. The publication demo uses an in-memory fake provider and explicitly simulated approval.

Product Ops defines and governs approved work. Delivery OS executes approved work. They share a versioned public artifact contract, never a database or internal persistence models.

## Quick start

Install Python 3.12 or 3.13 and uv, then run from this repository:

```sh
python -m pip install uv==0.12.18
python -m uv sync --locked --python 3.12
python -m uv run product-ops draft --input examples/feature-request.md
python -m uv run product-ops draft --input examples/ambiguous-request.md
python -m uv run product-ops demo --output out/demo-1
```

The ambiguous draft emits `AWAITING_CLARIFICATION` and exits 2. An unrecognized input also stops for clarification. The demo uses the low-risk documentation fixture, validates simulated approval, suppresses duplicate fake writes, and exports a digested handoff. No command performs a live external write.

```sh
python -m uv run ruff check .
python -m uv run ruff format --check .
python -m uv run mypy
python -m uv run pytest
python -m uv build --no-build-isolation
python -m uv run python scripts/wheel_smoke.py
python -m uv run python scripts/check_docs.py
python -m uv run python scripts/secret_scan.py
python -m uv export --locked --no-emit-project --format requirements-txt --output-file out/requirements.txt --quiet
python -m uv run pip-audit -r out/requirements.txt --disable-pip --no-deps
```

Or run every local gate with `python -m uv run python scripts/verify.py`. This also verifies unchanged fixture/schema regeneration and byte-identical sdist/wheel builds. Use a fresh demo output directory for each run; existing evidence files are never silently replaced.

## Read the design

- [Product specification](docs/product-spec.md), [initialization plan](docs/plan.md)
- [Architecture](docs/architecture.md), [state machine](docs/state-machine.md)
- [Security model](docs/security-model.md), [ADRs](docs/adr/README.md)
- [Linear integration](docs/linear-integration.md), [Delivery OS handoff](docs/delivery-os-handoff.md)
- [Evaluation methodology](docs/evaluation-methodology.md)
- [Implementation status and limits](docs/implementation-status.md), [ordered backlog](docs/backlog.md)
- [Contributing](CONTRIBUTING.md)

The foundation validates structure and objective invariants, not semantic correctness. Lexical risk rules are a conservative floor, not a complete classifier. Hashes prove byte integrity, not human identity or authenticity. Unknown outcomes stop publication; they never trigger blind retries. Hosted CI, live providers, cross-repository consumption, and human value remain unverified until separately exercised.
