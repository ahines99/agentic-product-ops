# Evaluation methodology

Safety and semantic quality are separate evidence classes. [M0's 15 cases](../evals/fixtures/m0-corpus.json) and the [45-case routing corpus](../evals/fixtures/m1-routing-corpus.json) are frozen, same-context authored, zero-inference routing tests. Their [original reports](../evals/reports/m0-first-run.json) and [expanded first report](../evals/reports/m1-routing-first-run.json) remain unchanged. A larger authored routing corpus cannot satisfy M1/M6 semantic acceptance.

## Frozen semantic evaluation

`evaluation/semantic.py` supplies strict gold-case, run and adjudication contracts. Ten categories cover clear feature, ambiguous request, nonfunctional, security, data, analytics, operational, compliance, repository grounding and prompt injection. Corpus hashes bind exact sources/requirements/material unknowns/risk floor. Each attempt binds corpus and result; every prediction and criterion requires explicit adjudication. Every case must retain attempt 1, including failure/abstention. Retry successes appear separately and cannot replace the original score.

| Measure | Numerator / denominator |
| --- | --- |
| Requirement precision | Unique supported matched gold requirements / all predicted requirements |
| Requirement recall | Unique supported matched gold requirements / gold requirements |
| Material ambiguity recall | Adjudicated detected material unknowns / gold material unknowns |
| False resolution rate | Adjudicated falsely resolved material unknowns / gold material unknowns |
| Criterion quality | Criteria judged measurable with correct traceability and provenance / predicted criteria |
| Risk | Count of proposed specifications below gold minimum tier |

Duplicate predictions cannot inflate matches; unsupported or missing annotations fail rather than silently disappear. Zero denominators are null. Aggregates include original attempts, all attempt rows, retry count and category breakdown. These metrics require human or independently reviewed semantic annotations; the software does not infer correctness from matching prose. Decomposition coherence, overlap, usefulness, full risk confusion matrices and semantic repository evidence require an extended adjudication study rather than invented automated scores.

Optional Ed25519 reviewer signatures bind exact judgment/corpus/result. A pinned reviewer key, external corpus authorship and a distinct reviewer identity are necessary for an independence attestation to count; even then it is an authenticated claim, not proof of semantic truth. `reported_inference` is a label, not independent evidence that a provider ran. The report always leaves `mvp_completion` false and lists unmeasured human usefulness, billing and live integration.

## Executable example

[Example corpus](../examples/semantic/corpus.json), [attempts](../examples/semantic/attempts.json) and [adjudications](../examples/semantic/adjudications.json) demonstrate scoring. There are two same-author cases and three attempts. The first clear attempt is deliberately incomplete; its recorded retry cannot erase the failed recall. The example is neither a benchmark nor independent review.

```sh
python -m uv run product-ops evaluate-semantic --corpus examples/semantic/corpus.json --attempts examples/semantic/attempts.json --adjudications examples/semantic/adjudications.json
python -m uv run python scripts/evaluate.py --output out/routing-evaluation-1.json
```

The scorer prints JSON; redirect to a fresh evidence path when preserving a study. `--reviewer-keys` accepts an operator-maintained JSON mapping reviewer IDs to base64 public keys. Never trust a key supplied inside an evaluated request. The example generator creates new authored recordings and must not be used to overwrite an actual first-run study.

## Acceptance coverage and remaining evidence

The suite exercises all foundation safety scenarios: clear/ambiguous routing, supported assumptions, unsupported requirement/forged clarification denial, risk floors, request/repository injection, stale/expired/unauthorized approval, duplicate commands, UNKNOWN reconciliation, scope enforcement, repository changes, duplicate titles, exact handoff, superseding revisions, model outage/budget and cancellation. Revision/service tests use real PostgreSQL/Temporal; Linear and model tests use mock transport. See [validation](v04-validation-record.md).

M6 still requires at least 40 separately authored frozen semantic cases across all categories, actual provider/config/prompt versions, pinned repository evidence, original failures, per-case adjudication and denominators, paid usage/cost/latency plus separate human waiting time, controlled live publication reliability and actual Delivery OS intake. Real participants must assess usefulness/time/editing effort; no participants or savings have been measured. Retrieval/vector storage remains deferred until an ablation establishes need. Coverage percentages are code evidence, never product quality or MVP completion.
