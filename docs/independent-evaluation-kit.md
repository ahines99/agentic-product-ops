# Independent evaluation authoring and adjudication kit

This is a protocol prepared in the implementation context, not an independent evaluation corpus or a quality result. The existing two-case `examples/semantic` corpus is explicitly a same-context template. The paid smoke is an engineering smoke and cannot count toward M1/M3/M6 semantic acceptance.

## Freeze before inference

1. Use an author in a separate context who has not seen model outputs for the cases. Provide the original product boundary, public contract, these category definitions and repository snapshots, not successful outputs to imitate. Independence can be a genuinely separate model context or person; do not relabel this implementation session as independent.
2. Author at least 40 cases, at least four per original category: `clear_feature`, `ambiguous_request`, `bug_report`, `analytics`, `security`, `data`, `multi_ticket`, `research_request`, `duplicate_rephrased`, `prompt_injection`. Include financial data in `data`, authorization in `security`, and both direct/indirect injection in `prompt_injection`. Research-only cases must not silently become implementation work; duplicate/rephrased cases need paired requests and explicit expected overlap judgments.
3. For each case record exact source, supported atomic requirements, material ambiguities and minimum risk. Record uncertainty rather than invented answers. Include pinned repository evidence where relevant, access failure cases and at least one conflicting team/repository claim. Put injection instructions in untrusted source/repository evidence, never in trusted policy.
4. Follow `SemanticCorpus`/`GoldCase` in `evaluation/semantic.py`. Set `authorship=external_submission` only when true. Calculate `corpus_digest` with `canonical_digest` over the complete JSON document excluding that field. Validate with `SemanticCorpus.model_validate_json`; retain the immutable corpus and independent author's identity/context declaration before any inference. The contract checks a declaration's shape, not the truth of independence.

## Execute under a separate authorization

5. Freeze model, adapter/prompt/runtime configuration, repository digest, trust scope, per-call/output limits and a new explicitly authorized study budget. The $10 first-smoke authorization is not a 40-case study authorization. Use distinct role contexts and the durable spending ledger; keep every first attempt, refusal, invalid output, timeout and held ambiguity. Record provider request IDs, tokens, wall time, conservative estimates and any later billing reconciliation.
6. Assign an `EvaluationAttempt` to every case/attempt. Preserve first failures. A corrected run is another attempt, not a replacement score. Never mark an authored recording as reported inference. Reviewer risk/approval decisions cannot be generated into authority by the evaluated model.

## Adjudicate and report

7. Have a separate reviewer inspect exact source, gold and every predicted requirement/criterion. Fill `Adjudication` with matched gold IDs, supported/unsupported judgments, material ambiguity detection, false resolutions, measurability, provenance and traceability. Review decomposition coherence/overlap, research-only scope and duplicate handling explicitly in notes; those semantic judgments are not replaced by string matching. Bind each judgment to frozen corpus/result digests, including failed attempts.
8. Optionally sign adjudications with the separately trusted reviewer key; signatures authenticate the attestation, not semantic truth. Freeze the reviewer identity and keys through the operator's trust channel. Use `SubmittedAdjudication`, then the command below. Inspect category coverage, precision/recall denominators, false resolutions, unsupported claims and first-attempt versus retry results. A zero denominator is missing evidence, never perfect performance.

```powershell
python -m uv run product-ops evaluate-semantic --corpus PATH/corpus.json --attempts PATH/attempts.json --adjudications PATH/adjudications.json
```

9. Apply milestone exit criteria from [evaluation methodology](evaluation-methodology.md) and [backlog](backlog.md). Actual Linear publication and actual Delivery OS acceptance are separate gates. A human editing-time/usefulness study is needed only for claims of human usefulness; it is not manufactured from a passing contract suite. Do not declare MVP or portfolio completion solely from this report.

Prepared artifacts: strict schemas, frozen same-context examples, signing/verification support and the report CLI already exist. Missing evidence: the independent corpus, independent adjudications, authorized study executions and measured acceptance results.
