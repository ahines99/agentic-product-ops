"""Explain why each evaluated case stopped, from the durable evaluation database.

For every case this replays the deterministic checks against the last stored attempt, so the
reported stop reason is the rule that fired, not a guess. Final states come from the run reports;
a held first call leaves no attempt to diagnose. It also scans every generated candidate
(including rejected ones) for injected phrases and prints the surrounding text, because a phrase
can appear in a refusal as easily as in a leak. No model calls are made.
"""

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_product_ops.adapters.model.contracts import Analysis
from agentic_product_ops.adapters.persistence.store import Store, artifacts, engine
from agentic_product_ops.domain.contracts import WorkSpecification
from agentic_product_ops.evaluation.model_eval import intake
from agentic_product_ops.policies.revisions import validate_revision
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy, proposal_ready
from agentic_product_ops.services.clarifications import load_clarifications

POLICY = ServerPolicy(
    version="pilot-v1",
    workspace_id="model-eval",
    teams=("product",),
    repositories=(),
    allow_any_repository=True,
    approvers=("evaluator",),
    security_approvers=("evaluator",),
)


def diagnose(store: Store, base: WorkSpecification, attempt: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    answers = load_clarifications(store, base, POLICY)
    if attempt.get("analysis") and base.provenance.clarification_refs:
        analysis = Analysis.model_validate_json(json.dumps(attempt["analysis"]))
        if analysis.unresolved_questions != base.unresolved_questions:
            notes.append("revision gate: analyst changed the answered questions")
        if analysis.objective != base.objective:
            notes.append("revision gate: analyst changed the objective")
    if attempt.get("specification"):
        candidate = WorkSpecification.model_validate_json(json.dumps(attempt["specification"]))
        if base.provenance.clarification_refs:
            try:
                validate_revision(base, candidate, answers, POLICY)
            except PolicyError as error:
                notes.append(f"revision gate: {error}")
        try:
            proposal_ready(candidate, POLICY, clarifications=answers)
        except PolicyError as error:
            notes.append(f"readiness gate: {error}")
    review = attempt.get("review") or {}
    blocking = [f["summary"] for f in review.get("findings", []) if f["blocking"]]
    if blocking:
        notes.append(f"reviewer: {len(blocking)} blocking finding(s)")
    failed = [
        f"{r['role']} {r['status']}" for r in attempt["receipts"] if r["status"] != "SUCCEEDED"
    ]
    if failed:
        notes.append("model call held: " + ", ".join(failed))
    return notes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
    database = engine(f"sqlite:///{args.database}", testing=True)
    store = Store(database)
    with database.connect() as conn:
        rows = conn.execute(
            artifacts.select()
            .where(artifacts.c.kind.in_(["revision_attempt", "revision_result"]))
            .order_by(artifacts.c.created_at)
        ).mappings()
        stored = [(row["kind"], json.loads(row["payload"])) for row in rows]
    report: list[dict[str, Any]] = []
    for case in cases:
        identity = str(
            intake(case["id"], case["request"], POLICY, datetime.now(UTC)).specification_id
        )
        base = WorkSpecification.model_validate_json(
            json.dumps(store.get(POLICY.workspace_id, "specification", identity))
        )
        request = case["request"].strip()

        def mine(value: dict[str, Any], request: str = request) -> bool:
            source = (value.get("analysis") or value.get("specification") or {}).get(
                "source_statements", [{}]
            )
            return bool(source) and source[0].get("text", "").strip() == request

        attempts = [v for kind, v in stored if kind == "revision_attempt" and mine(v)]
        candidates = [a["specification"] for a in attempts if a.get("specification")]
        contexts = []
        for spec in candidates:
            texts = [r["text"] for r in spec["requirements"]]
            for work in spec["work_items"]:
                texts.append(work["title"] + " | " + work["description"])
                texts.extend(a["text"] for a in work["acceptance_criteria"])
            for text in texts:
                for phrase in case["must_not_contain"]:
                    index = text.casefold().find(phrase.casefold())
                    if index >= 0:
                        contexts.append(
                            {"phrase": phrase, "context": text[max(0, index - 200) : index + 120]}
                        )
        report.append(
            {
                "id": case["id"],
                "answered": bool(base.provenance.clarification_refs),
                "stop_diagnosis": diagnose(store, base, attempts[-1]) if attempts else [],
                "candidates_with_tickets": sum(bool(c["work_items"]) for c in candidates),
                "tickets_generated": sum(len(c["work_items"]) for c in candidates),
                "reviews": sum(bool(a.get("review")) for a in attempts),
                "reviews_with_blocking_findings": sum(
                    any(f["blocking"] for f in (a.get("review") or {}).get("findings", []))
                    for a in attempts
                ),
                "phrase_contexts": contexts,
            }
        )
    tally = Counter(note.split(":")[0] for entry in report for note in entry["stop_diagnosis"])
    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "stop_rule_counts": tally,
        "cases": report,
    }
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8", newline="\n")
    for entry in report:
        print(entry["id"], "|", "; ".join(entry["stop_diagnosis"]) or "no stored attempt")
    database.dispose()


if __name__ == "__main__":
    main()
