"""Frozen authored routing corpus; no claim of model quality or human validation."""

import json
from pathlib import Path
from typing import Any, Literal

from agentic_product_ops.domain.contracts import ID, Contract, Digest, Text, canonical_digest
from agentic_product_ops.services.drafting import draft


class EvaluationCase(Contract):
    id: ID
    category: ID
    source: Text
    expected_state: Literal["PROPOSED", "AWAITING_CLARIFICATION"]
    authorship: Literal["same_initialization_context"]


class FrozenCorpus(Contract):
    schema_version: Literal["1"] = "1"
    cases: tuple[EvaluationCase, ...]
    digest: Digest


def evaluate(path: Path) -> dict[str, Any]:
    corpus = FrozenCorpus.model_validate_json(path.read_bytes())
    payload = [case.model_dump(mode="json") for case in corpus.cases]
    if canonical_digest(payload) != corpus.digest:
        raise ValueError("corpus freeze digest mismatch")
    rows = []
    for case in corpus.cases:
        spec, state = draft(case.source)
        rows.append(
            {
                "id": case.id,
                "expected": case.expected_state,
                "actual": state.value,
                "passed": state.value == case.expected_state,
                "blocking_questions": sum(q.blocking for q in spec.unresolved_questions),
                "specification_digest": spec.content_digest,
            }
        )
    return {
        "schema_version": "1",
        "mode": "offline_routing_regression",
        "corpus_digest": corpus.digest,
        "case_count": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "results": rows,
        "model_calls": 0,
        "provider_calls": 0,
        "model_cost": "0",
        "independent_authorship": False,
        "human_validation": False,
        "unmeasured": [
            "extraction precision/recall",
            "semantic ambiguity detection",
            "ticket usefulness",
            "repository grounding",
            "human time savings",
            "live latency/cost",
        ],
    }


def write_report(corpus: Path, destination: Path) -> None:
    report = evaluate(corpus)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(report, indent=2) + "\n")
