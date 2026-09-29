"""Generate same-author scoring examples, including an intentionally incomplete first attempt."""

import json
from pathlib import Path
from typing import Any

from agentic_product_ops.domain.contracts import canonical_digest
from agentic_product_ops.evaluation.semantic import SemanticCorpus
from agentic_product_ops.services.recorded_pipeline import recorded_pipeline

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    runs: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    for case_id, filename, category in (
        ("clear", "feature-request.md", "clear_feature"),
        ("ambiguous", "ambiguous-request.md", "ambiguous_request"),
    ):
        source = (ROOT / "examples" / filename).read_text(encoding="utf-8")
        result = recorded_pipeline(source).model_dump(mode="json")
        # Recording timestamps/IDs are evidence for a demonstration only, never model quality.
        analysis = result["analysis"]
        assert analysis is not None  # noqa: S101
        cases.append(
            {
                "id": case_id,
                "category": category,
                "source": analysis["source_statements"][0]["text"],
                "requirements": [
                    {"id": r["id"], "text": r["text"]} for r in analysis["requirements"]
                ],
                "ambiguities": [
                    {"id": q["id"], "text": q["question"], "material": q["blocking"]}
                    for q in analysis["unresolved_questions"]
                ],
                "minimum_risk": 0,
            }
        )
        if case_id == "clear":
            incomplete = json.loads(json.dumps(result))
            incomplete.update(
                state="PAUSED",
                specification=None,
                review=None,
                receipts=[],
                reason="example_failure",
            )
            incomplete["analysis"]["requirements"] = analysis["requirements"][:1]
            runs.append(
                {"run_id": "clear-1", "case_id": case_id, "attempt": 1, "result": incomplete}
            )
        runs.append(
            {
                "run_id": f"{case_id}-{'2' if case_id == 'clear' else '1'}",
                "case_id": case_id,
                "attempt": 2 if case_id == "clear" else 1,
                "result": result,
            }
        )
    raw = {
        "schema_version": "1",
        "authorship": "same_context_template",
        "author_id": "initialization-author",
        "cases": cases,
    }
    corpus = SemanticCorpus.model_validate_json(
        json.dumps({**raw, "corpus_digest": canonical_digest(raw)})
    )
    judgments = []
    for run in runs:
        run.update(
            corpus_digest=corpus.corpus_digest,
            execution_mode="authored_recording",
            producer_id="initialization-author",
        )
        result = run["result"]
        output = result["specification"] or result["analysis"]
        judgments.append(
            {
                "judgment": {
                    "run_id": run["run_id"],
                    "reviewer_id": "initialization-author",
                    "corpus_digest": corpus.corpus_digest,
                    "result_digest": canonical_digest(result),
                    "requirements": [
                        {"predicted_id": r["id"], "matched_gold_id": r["id"], "supported": True}
                        for r in output["requirements"]
                    ],
                    "detected_gold_ambiguities": [
                        q["id"] for q in output["unresolved_questions"] if q["blocking"]
                    ],
                    "falsely_resolved_gold_ambiguities": [],
                    "criteria": [
                        {
                            "criterion_id": c["id"],
                            "measurable": True,
                            "correct_traceability": True,
                            "correct_provenance": True,
                        }
                        for w in (result["specification"] or {}).get("work_items", [])
                        for c in w["acceptance_criteria"]
                    ],
                    "notes": "Authored example; incomplete first result; no independent review.",
                    "independence_attested": False,
                },
                "signature": None,
            }
        )
    target = ROOT / "examples" / "semantic"
    target.mkdir(exist_ok=True)
    for name, data in (
        ("corpus", corpus.model_dump(mode="json")),
        ("attempts", runs),
        ("adjudications", judgments),
    ):
        (target / f"{name}.json").write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n"
        )


if __name__ == "__main__":
    main()
