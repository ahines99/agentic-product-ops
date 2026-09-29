# Evaluation methodology

Evaluation begins with objective safety regressions. [The frozen M0 corpus](../evals/fixtures/m0-corpus.json) contains 15 authored cases covering clear features, ambiguous features, documentation, bugs, analytics, authorization, financial logic, multi-ticket work, research, rephrasing, and five prompt-injection intents. Each case records exact source, expected routing state, category, and same-context authorship. The corpus digest binds all cases in order.

These cases were authored in the same initialization context as the implementation. They are neither independent evaluation nor human validation. They establish only deterministic fixture-routing behavior: recognized fixtures propose; all other inputs hold. They do not measure semantic extraction or general ambiguity detection. The first report is preserved at [m0-first-run.json](../evals/reports/m0-first-run.json). Later reports use new paths; the runner refuses overwrites. Separate contexts for independent authoring and system evaluation are required in M1/M6, with no claim that separately authored agent cases constitute human validation.

```sh
python -m uv run python scripts/evaluate.py --output out/evaluation-1.json
```

## Measures and definitions

| Dimension | Planned scoring | M0 evidence |
| --- | --- | --- |
| Requirement precision / recall | Matched supported requirements / generated or gold requirements | Unmeasured |
| Ambiguity detection | Recall of authored material unknowns, stratified by category | Known ambiguous fixture keeps five blockers; unknown input holds |
| False resolution | Material unknowns asserted resolved without authorized answer / material unknowns | Forged-resolution rejection test only |
| Acceptance quality | Traceability + human rubric for observable behavior and evidence | Structural coverage, references, evidence text required |
| Decomposition quality | Human rubric for coherent boundaries, sequencing, overlap | DAG checks and normalized duplicate-title detection |
| Traceability | Valid source/requirement/criterion links / total links | Executable reference validation |
| Repository grounding | Claims supported by pinned evidence / repository claims | Advisory schema; synthetic injection test only |
| Risk classification | Confusion matrix against adjudicated policy tiers | Lexical floor regression, not semantic accuracy |
| Publication safety | Unauthorized writes per attempted adversarial command | Zero fake writes in denied-command tests |
| Write reliability | Duplicates, UNKNOWN handling, recovery after faults | In-memory fake duplicate/lost-response tests |
| Cost / latency | Model usage, estimated decimal cost, end-to-end and wait latency separately | Zero model calls; live latency/cost unmeasured |
| Human value | Time, edit count/distance, missed requirements, confidence/usefulness | No participants or measured savings |

M6 requires at least 40 separately authored frozen cases with matched model/provider/config/prompt versions, pinned repository snapshots, first-run failures, per-case results, aggregate metrics with denominators, risk/category breakdown, and measured cost/latency. Abstention and research-only outputs need explicit gold labels; holding all inputs is not successful extraction. Retrieval/vector storage is deferred until an ablation establishes need.

## Acceptance scenario mapping

| ID | Scenario | M0 coverage / remaining gap |
| --- | --- | --- |
| A-01 | Clear request | Authored fixture CLI + strict traceability tests |
| A-02 | Material ambiguity | Five blockers, proposal/publication denied |
| A-03 | Safe nonmaterial choice | Visible nonbehavioral ID-format assumption |
| A-04 | Unsupported inference | Objective check blocks inferred behavior; semantic reviewer planned |
| A-05 | High risk | Deterministic lexical floor and handoff restriction |
| A-06 | Request injection | Adversarial unknown sources remain held |
| A-07 | Repository injection | Synthetic advisory evidence cannot change policy; adapter planned |
| A-08 | Revision mismatch | Fake publication denied |
| A-09 | Expired approval | Boundary-time and future-date denial |
| A-10 | Duplicate publish | One fake issue set in a single process |
| A-11 | Lost response | Reconcile or UNKNOWN, no blind create |
| A-12 | Unauthorized team | Allowlist and approval scope denial |
| A-13 | Repository uncertainty | Null context and explicit synthetic unknowns; grounding planned |
| A-14 | Duplicate work | Normalized title detector; semantic overlap review planned |
| A-15 | Exact handoff | Digested simulation export/consumer parsing; real consumer planned |
| A-16 | Post-publish revision | Old immutable object unchanged; old approval invalid; durable history planned |
| A-17 | Model outage/budget | Not implemented; no model calls exist |
| A-18 | Cancellation | Future fake writes denied; durable race handling planned |

Test coverage percentages measure exercised code, not product capability or task quality. Hosted, live provider, cross-repository, externally used, human-validated, and production-accepted evidence remain separate categories.
