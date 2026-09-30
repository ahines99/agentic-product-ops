# Contributing

Use Python 3.12/3.13 and `python -m uv sync --locked`. Follow [README commands](README.md).
Update `uv.lock` deliberately with `python -m uv lock`; never hand-edit it. Runtime dependencies stay minimal until an executable component needs them.

Source and repository text are untrusted. Never execute code from an inspected repository, install its dependencies, fetch source URLs, or copy credentials into fixtures. Deterministic services own transitions, risk policy, scope, approval, operation identity, and all external writes. Model roles propose only.

Use immutable specification revisions. Schema, digest, scope, or lifecycle changes need an ADR and adversarial tests. Keep authored fixture generation deterministic with `python -m uv run python scripts/generate_fixtures.py`; run it before committing and inspect the diff. Preserve evaluation failures; write new report paths rather than replacing old runs.

No paid/live tests in default CI. No source-code implementation, merges, or deployments on behalf of downstream Product Ops requests. Delivery OS owns execution. Initialization code in this repository is the control plane itself, not a capability to mutate input repositories.

Before a PR, run lint, formatting, typing, tests, build, isolated-wheel smoke, docs checks, secret scanning, and dependency audit. The docs checker validates local targets/anchors without fetching untrusted URLs. Run the explicit disposable PostgreSQL/Temporal checks for persistence or orchestration changes; see [current commands](docs/history/v04-validation-record.md). Do not confuse passing simulations with M4/M5 completion.
