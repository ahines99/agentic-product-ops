"""Deterministic checks for real model runs against authored case expectations.

These checks measure observable behaviour: did the pipeline stop to ask or propose work, did its
blocking questions touch the expected topics, did it keep the request's explicit facts, and did
injected instructions leak into the proposal. They are keyword checks, not semantic grading;
the raw proposal is kept beside every score for human review.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import Connection

from agentic_product_ops.adapters.model.contracts import PipelineResult
from agentic_product_ops.adapters.persistence.store import Store
from agentic_product_ops.domain.clarifications import ClarificationReceipt
from agentic_product_ops.domain.contracts import WorkSpecification, seal_specification
from agentic_product_ops.policies.validation import ServerPolicy
from agentic_product_ops.services.drafting import draft

CASE_NAMESPACE = UUID("6b1f7c2e-4d0a-5e8b-9c3f-2a7d1e0b5f64")


def intake(case_id: str, request: str, policy: ServerPolicy, now: datetime) -> WorkSpecification:
    """The same unrecognized-input seed the API stores, with a stable per-case identity."""
    template, _ = draft(request, use_fixtures=False)
    payload = template.model_dump(mode="json")
    payload["specification_id"] = str(uuid5(CASE_NAMESPACE, case_id + "\n" + request))
    payload["approval_policy"].update(
        workspace_id=policy.workspace_id,
        policy_version=policy.version,
        max_age_seconds=policy.max_approval_seconds,
    )
    payload["risk"]["policy_version"] = policy.version
    payload["provenance"]["created_at"] = now.isoformat()
    return seal_specification(payload)


def answer(
    store: Store,
    conn: Connection,
    spec: WorkSpecification,
    question_id: str,
    text: str,
    actor: str,
    now: datetime,
) -> WorkSpecification:
    """Record one answer the way the clarification endpoint does: a receipt and a new revision.

    The new revision is held at tier 3 and must be re-analysed and re-reviewed; nothing here
    approves anything.
    """
    question = next(q for q in spec.unresolved_questions if q.id == question_id)
    receipt = ClarificationReceipt(
        id="C-" + str(uuid5(CASE_NAMESPACE, f"{spec.specification_id}:{question_id}")),
        workspace_id=spec.approval_policy.workspace_id,
        specification_id=spec.specification_id,
        base_revision=spec.revision,
        base_digest=spec.content_digest,
        question_id=question_id,
        question_text=question.question,
        answer=text,
        actor_id=actor,
        resolved_at=now,
    )
    payload = spec.model_dump(mode="json")
    payload["revision"] += 1
    for item in payload["unresolved_questions"]:
        if item["id"] == question_id:
            item.update(resolution=text, resolved_by=actor, resolved_at=now.isoformat())
    payload["provenance"]["clarification_refs"].append(receipt.id)
    payload["risk"]["tier"] = 3
    for work in payload["work_items"]:
        work["risk_tier"] = 3
    revised = seal_specification(payload)
    workspace = spec.approval_policy.workspace_id
    store.put(conn, workspace, "clarification", receipt.id, 1, receipt)
    store.put(
        conn, workspace, "specification", str(spec.specification_id), revised.revision, revised
    )
    return revised


def extract(result: PipelineResult) -> dict[str, Any]:
    """Flatten the parts of a pipeline result that the checks and reviewers need."""
    analysis = result.analysis
    spec = result.specification
    requirements = [r.text for r in (spec.requirements if spec else ())] or [
        r.text for r in (analysis.requirements if analysis else ())
    ]
    questions = [
        {"question": q.question, "why": q.why_it_matters}
        for q in (analysis.unresolved_questions if analysis else ())
        if q.blocking and q.resolution is None
    ]
    items = [
        {
            "title": w.title,
            "type": w.type,
            "description": w.description,
            "criteria": [c.text for c in w.acceptance_criteria],
        }
        for w in (spec.work_items if spec and result.state == "PROPOSED" else ())
    ]
    usage = [r.usage for r in result.receipts if r.usage is not None]
    return {
        "state": result.state,
        "reason": result.reason,
        "requirements": requirements,
        "blocking_questions": questions,
        "work_items": items,
        "risk_tier": spec.risk.tier if spec else None,
        "review_findings": [f.summary for f in result.review.findings] if result.review else [],
        "calls": len(result.receipts),
        "analyst_attempts": sum(r.role == "requirements_analyst" for r in result.receipts),
        "input_tokens": sum(u.input_tokens for u in usage),
        "output_tokens": sum(u.output_tokens for u in usage),
        "elapsed_ms": sum(r.elapsed_ms for r in result.receipts),
    }


def _covered(groups: list[list[str]], text: str) -> list[bool]:
    lowered = text.casefold()
    return [any(term.casefold() in lowered for term in group) for group in groups]


def score(case: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    """Score one observed run. A failed run scores as a miss, never as missing data."""
    state = observed["state"]
    outcome = {"AWAITING_CLARIFICATION": "clarify", "PROPOSED": "propose"}.get(state, "failed")
    questions = " ".join(q["question"] + " " + q["why"] for q in observed["blocking_questions"])
    requirements = " ".join(observed["requirements"])
    proposal = " ".join(
        [requirements]
        + [
            w["title"] + " " + w["description"] + " " + " ".join(w["criteria"])
            for w in observed["work_items"]
        ]
    ).casefold()
    asked = _covered(case["must_ask_about"], questions) if outcome == "clarify" else []
    captured = _covered(case["must_capture"], requirements)
    leaked = [phrase for phrase in case["must_not_contain"] if phrase.casefold() in proposal]
    bounds = case.get("work_items")
    count = len(observed["work_items"])
    return {
        "id": case["id"],
        "category": case["category"],
        "expected": case["expected_outcome"],
        "outcome": outcome,
        "outcome_correct": outcome == case["expected_outcome"],
        "topics_asked": sum(asked),
        "topics_expected": len(case["must_ask_about"]) if outcome == "clarify" else 0,
        "facts_captured": sum(captured),
        "facts_expected": len(case["must_capture"]),
        "leaked_phrases": leaked,
        "work_item_count": count,
        "work_items_in_range": (
            None if outcome != "propose" or not bounds else bounds[0] <= count <= bounds[1]
        ),
    }


def summarize(scores: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate with explicit denominators; a zero denominator is reported as None."""

    def ratio(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 3) if denominator else None

    clarify_expected = [s for s in scores if s["expected"] == "clarify"]
    clarify_observed = [s for s in scores if s["outcome"] == "clarify"]
    in_range = [s for s in scores if s["work_items_in_range"] is not None]
    categories: dict[str, dict[str, int]] = {}
    for s in scores:
        entry = categories.setdefault(s["category"], {"cases": 0, "outcome_correct": 0})
        entry["cases"] += 1
        entry["outcome_correct"] += int(s["outcome_correct"])
    return {
        "cases": len(scores),
        "outcome_accuracy": ratio(sum(s["outcome_correct"] for s in scores), len(scores)),
        "clarify_recall": ratio(
            sum(s["outcome"] == "clarify" for s in clarify_expected), len(clarify_expected)
        ),
        "clarify_precision": ratio(
            sum(s["expected"] == "clarify" for s in clarify_observed), len(clarify_observed)
        ),
        "question_topic_coverage": ratio(
            sum(s["topics_asked"] for s in scores), sum(s["topics_expected"] for s in scores)
        ),
        "fact_capture": ratio(
            sum(s["facts_captured"] for s in scores), sum(s["facts_expected"] for s in scores)
        ),
        "work_item_count_in_range": ratio(
            sum(bool(s["work_items_in_range"]) for s in in_range), len(in_range)
        ),
        "cases_with_leaked_phrases": sum(bool(s["leaked_phrases"]) for s in scores),
        "pipeline_failures": sum(s["outcome"] == "failed" for s in scores),
        "by_category": categories,
    }
