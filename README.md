# Agentic Product Ops

**Local prompt entry:** open the [prompt console](docs/local-prompt-console.md) at
`http://127.0.0.1:18013` using the local launch shortcut. Enter a prompt and repository name,
review detailed ticket proposals, answer questions and approve the exact plan. New paid analysis
is currently held pending a fresh budget; the page reports this explicitly.

The unreleased [prompt-to-delivery integration](docs/prompt-to-delivery.md) adds prompt plus
repository-name intake and an approval-bound local documentation handoff. The approved PER-7
workflow created PER-8 and Delivery OS produced the exact, unmerged local change. See the
[live validation record](docs/per7-validation-record.md). This does not establish MVP completion.

Agentic Product Ops is a governed AI-assisted requirements and work-decomposition system. It converts ambiguous product requests into evidence-linked requirements, unresolved questions, acceptance criteria, and proposed Linear work items. Humans approve the exact specification before any external write. Approved work can then be handed to Agentic Delivery OS for controlled implementation and independent verification.

**Current version: 0.5.2, monitored local pilot; MVP acceptance is incomplete.** Linear webhooks and periodic API reconciliation now feed a durable intake inbox. The local monitor runs in acceptance mode with paid execution and publication disabled. It resolves a basic issue and repository name, excludes old backlog/generated output, deduplicates retries and holds changed sources. A login task supervises the local services and temporary HTTPS tunnel. See [monitor operation](docs/linear-monitor.md), [issue-driven intake](docs/issue-driven-operation.md) and [exact limitations](docs/implementation-status.md).

The existing local pilot uses explicit operator identity, encrypted PostgreSQL, Temporal, bounded Anthropic calls and a durable aggregate spending allowance. Its earlier six-call `claude-opus-5-5` smoke reached a reviewed proposal after two preserved failures, and read-only Linear API-key identity discovery succeeded. That earlier smoke had no human approval, live Linear write or actual Delivery OS intake; the later PER-7 evidence above exercises those boundaries. See [pilot setup](docs/local-pilot.md) and [v0.5 evidence](docs/v05-validation-record.md).

Product Ops defines and governs approved work. Delivery OS executes approved work. They share a versioned public artifact contract, never a database or internal persistence models.

## Quick start

Install Python 3.12 or 3.13 and uv, then run from this repository:

```sh
python -m pip install uv==0.12.18
python -m uv sync --locked --python 3.12
python -m uv run product-ops draft --input examples/feature-request.md
python -m uv run product-ops draft --input examples/ambiguous-request.md
python -m uv run product-ops demo --output out/demo-1
python -m uv run product-ops roles-demo --input examples/feature-request.md
python -m uv run product-ops evaluate-semantic --corpus examples/semantic/corpus.json --attempts examples/semantic/attempts.json --adjudications examples/semantic/adjudications.json
python -m uv run product-ops inspect-repository --root . --repository-id product-ops
python -m uv run product-ops roles-demo --input examples/feature-request.md --repository-root . --repository-id product-ops
```

The ambiguous offline draft emits `AWAITING_CLARIFICATION` and exits 2. An unrecognized offline input also stops for clarification. The offline demo uses the low-risk documentation fixture, validates simulated approval, suppresses duplicate fake writes, and exports a digested handoff. These commands make no live external write. `product-ops-pilot` is a separate explicitly configured command path; its paid-execution and publication flags default off.

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

Default tests need no services or credentials; five service-dependent tests skip unless explicitly configured. See [current validation and runtime commands](docs/v05-validation-record.md) for real PostgreSQL/Temporal checks. Dependency installation and vulnerability auditing use public registries, not paid model APIs. The default API denies all identities and reports unready; the local pilot explicitly supplies its operator and guarded publication handler. There is no UI.

## Read the design

- [Product specification](docs/product-spec.md), [initialization plan](docs/plan.md)
- [Architecture](docs/architecture.md), [state machine](docs/state-machine.md)
- [Security model](docs/security-model.md), [ADRs](docs/adr/README.md)
- [Linear integration](docs/linear-integration.md), [Delivery OS handoff](docs/delivery-os-handoff.md)
- [Evaluation methodology](docs/evaluation-methodology.md)
- [Implementation status and limits](docs/implementation-status.md), [ordered backlog](docs/backlog.md)
- [Remaining implementation steps](docs/remaining-work.md), [local runtime commands and results](docs/offline-expansion.md)
- [Current verification and exact commands](docs/v04-validation-record.md), [offline case study](docs/offline-case-study.md)
- [Completed engineering checklist](docs/offline-completion-plan.md)
- [Local pilot runbook](docs/local-pilot.md), [independent evaluation kit](docs/independent-evaluation-kit.md)
- [Contributing](CONTRIBUTING.md)

The foundation validates structure and objective invariants, not semantic correctness. Lexical risk rules are a conservative floor, not a complete classifier. Hashes prove byte integrity; signed v2 handoffs additionally require pinned issuer keys and an expected digest. Unknown outcomes stop publication; they never trigger blind retries. The model smoke is engineering evidence. Hosted CI, live publication, actual Delivery OS consumption, independent semantic quality and human value remain unverified.
