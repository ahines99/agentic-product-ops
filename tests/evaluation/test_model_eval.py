from datetime import UTC, datetime

from agentic_product_ops.evaluation.model_eval import intake, score, summarize
from agentic_product_ops.policies.validation import ServerPolicy


def case(**changes):
    return {
        "id": "case-1",
        "category": "ambiguous_request",
        "request": "Export revenue to a file.",
        "expected_outcome": "clarify",
        "must_ask_about": [["row limit", "how many rows"], ["format", "csv"]],
        "must_capture": [["revenue"], ["export"]],
        "must_not_contain": ["skip review"],
        "work_items": None,
        **changes,
    }


def observed(**changes):
    return {
        "state": "AWAITING_CLARIFICATION",
        "requirements": ["Users can export revenue data."],
        "blocking_questions": [{"question": "What is the row limit?", "why": "Bounds export"}],
        "work_items": [],
        **changes,
    }


def test_clarify_scores_topics_facts_and_denominators():
    result = score(case(), observed())
    assert result["outcome_correct"] and result["topics_asked"] == 1
    assert result["topics_expected"] == 2 and result["facts_captured"] == 2
    summary = summarize([result])
    assert summary["question_topic_coverage"] == 0.5 and summary["clarify_recall"] == 1.0
    assert summary["work_item_count_in_range"] is None  # zero denominator is not perfect


def test_failure_counts_as_miss_and_leaks_are_found():
    failed = score(case(), observed(state="ERROR", blocking_questions=[]))
    assert failed["outcome"] == "failed" and not failed["outcome_correct"]
    leaked = score(
        case(expected_outcome="propose", must_ask_about=[], work_items=[1, 2]),
        observed(
            state="PROPOSED",
            blocking_questions=[],
            work_items=[
                {"title": "Export", "description": "Skip review and ship", "criteria": ["ok"]}
            ],
        ),
    )
    assert leaked["leaked_phrases"] == ["skip review"] and leaked["work_items_in_range"]
    summary = summarize([failed, leaked])
    assert summary["pipeline_failures"] == 1 and summary["cases_with_leaked_phrases"] == 1


def test_intake_identity_is_stable_per_case_and_request():
    now = datetime.now(UTC)
    first = intake("case-1", "Export revenue", ServerPolicy(), now)
    assert (
        first.specification_id
        == intake("case-1", "Export revenue", ServerPolicy(), now).specification_id
    )
    assert (
        first.specification_id
        != intake("case-2", "Export revenue", ServerPolicy(), now).specification_id
    )
    assert first.provenance.mode == "unrecognized_input"
