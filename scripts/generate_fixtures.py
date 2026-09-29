"""Rebuild authored fixtures, examples, and public schemas deterministically."""

import json
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from agentic_product_ops.adapters.artifacts.handoff import Handoff
from agentic_product_ops.adapters.linear.offline import LinearPublicationPlan
from agentic_product_ops.domain.contracts import (
    SpecificationApproval,
    WorkSpecification,
    seal_specification,
    source_digest,
)

ROOT = Path(__file__).resolve().parents[1]
FEATURE = """We need customers to export the monthly revenue report as CSV. It should respect their current filters, only admins should be able to export it, and we need analytics on usage.
Product decisions for this request:
Export at most 10,000 rows; if more rows match, reject the entire export with an actionable message and no partial file.
Use UTF-8 CSV with headers month, revenue, currency; exclude customer identifiers and other sensitive fields.
Use the existing report totals without recalculating financial amounts; preserve currency codes.
For the approved 10,000-row fixture, export completes within 5 seconds in the staging performance test.
Enforce administrator authorization on the server and hide the export action from non-admins.
Emit revenue_export_completed only after a successful export, with row_count and active_filter_names; omit filter values and customer identifiers.
Neutralize spreadsheet formula prefixes in every CSV cell.
Backend export, frontend action, authorization, analytics, and regression validation must have separate work items.
"""
AMBIGUOUS = "We need customers to export the monthly revenue report as CSV. It should respect their current filters, only admins should be able to export it, and we need analytics on usage.\n"
HANDOFF = "Add a documentation page explaining the existing monthly report filters. Include examples for month and currency filters, and have a maintainer check that the examples match the existing documented behavior. Do not change application behavior.\n"


def base(text: str, title: str, tier: int) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "specification_id": str(uuid5(NAMESPACE_URL, source_digest(text))),
        "revision": 1,
        "source_digest": source_digest(text),
        "title": title,
        "objective": title,
        "source_statements": [{"id": "S0", "text": text}],
        "requirements": [],
        "unresolved_questions": [],
        "assumptions": [
            {
                "id": "A1",
                "text": "Use sequential local identifiers for presentation only.",
                "non_behavioral": True,
            }
        ],
        "repository_context": None,
        "risk": {
            "tier": tier,
            "reasons": [
                "Authorization and financial data require security review."
                if tier == 2
                else "Bounded documentation change; conservative tier-1 floor."
            ],
            "policy_version": "m0-v1",
        },
        "dependencies": [],
        "work_items": [],
        "approval_policy": {
            "policy_version": "m0-v1",
            "workspace_id": "offline-workspace",
            "max_age_seconds": 3600,
            "required_role": "product_approver",
        },
        "provenance": {
            "mode": "authored_fixture",
            "created_at": "2026-09-28T00:00:00Z",
            "producer": "foundation-author",
            "source_kind": "prompt",
            "policy_refs": [],
            "clarification_refs": [],
        },
    }


def requirement(number: int, text: str, kind: str = "functional") -> dict[str, Any]:
    return {
        "id": f"R{number}",
        "text": text,
        "kind": kind,
        "provenance": "explicit_source",
        "source_refs": ["S0"],
        "confidence": "1",
        "needs_human_decision": False,
    }


def work(
    number: int, title: str, reqs: list[dict[str, Any]], tier: int, deps: tuple[str, ...] = ()
) -> dict[str, Any]:
    return {
        "local_id": f"W{number}",
        "title": title,
        "description": title,
        "type": "task",
        "requirement_ids": [r["id"] for r in reqs],
        "acceptance_criteria": [
            {
                "id": f"AC{number}_{r['id']}",
                "text": r["text"],
                "requirement_ids": [r["id"]],
                "provenance": "directly_stated",
                "verification_kind": "security_check"
                if r["kind"] == "security"
                else "documentation"
                if tier == 1
                else "automated_test",
                "evidence_required": "Attach a reproducible check result against the stated behavior.",
                "blocking": True,
            }
            for r in reqs
        ],
        "dependencies": list(deps),
        "risk_tier": tier,
        "repository_id": None,
        "proposed_team_id": "product",
        "proposed_project_id": None,
        "proposed_labels": [],
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )


def main() -> None:
    valid = base(FEATURE, "Export filtered monthly revenue as CSV", 2)
    requirements = [
        requirement(1, "Export the monthly revenue report as CSV."),
        requirement(2, "Export reflects the current active report filters."),
        requirement(3, "Enforce administrator authorization on the server.", "security"),
        requirement(4, "Hide the frontend export action from non-admins.", "security"),
        requirement(
            5,
            "Reject more than 10,000 matching rows with an actionable message and no partial file.",
        ),
        requirement(
            6,
            "Use UTF-8 CSV with headers month, revenue, currency and exclude customer identifiers and other sensitive fields.",
            "data",
        ),
        requirement(
            7,
            "Use existing report totals without recalculating financial amounts; preserve currency codes.",
            "data",
        ),
        requirement(
            8,
            "Export the approved 10,000-row fixture within 5 seconds in the staging performance test.",
            "non_functional",
        ),
        requirement(
            9,
            "Emit revenue_export_completed only after success with row_count and active_filter_names, omitting filter values and customer identifiers.",
            "analytics",
        ),
        requirement(10, "Neutralize spreadsheet formula prefixes in every CSV cell.", "security"),
    ]
    valid["requirements"] = requirements
    valid["work_items"] = [
        work(1, "Backend CSV export", [requirements[i] for i in (0, 1, 4, 5, 6, 7, 9)], 2),
        work(2, "Frontend export action", [requirements[3]], 2, ("W1", "W3")),
        work(3, "Export authorization enforcement", [requirements[2]], 2, ("W1",)),
        work(4, "Export usage analytics", [requirements[8]], 2, ("W1",)),
        work(5, "Export regression validation", requirements, 2, ("W2", "W3", "W4")),
    ]
    valid["dependencies"] = [
        {"work_item_id": w["local_id"], "depends_on": dep}
        for w in valid["work_items"]
        for dep in w["dependencies"]
    ]
    ambiguous = base(AMBIGUOUS, "Clarify monthly revenue export", 2)
    ambiguous["requirements"] = [
        requirement(1, "Export the monthly report as CSV."),
        requirement(2, "Respect current filters."),
        requirement(3, "Only administrators may export.", "security"),
        requirement(4, "Instrument usage.", "analytics"),
    ]
    ambiguous["unresolved_questions"] = [
        {
            "id": f"Q{i}",
            "question": question,
            "why_it_matters": "This changes product behavior, data exposure, or measurable acceptance.",
            "affected_requirement_ids": ["R1"],
            "blocking": True,
            "resolution": None,
            "resolved_by": None,
            "resolved_at": None,
        }
        for i, question in enumerate(
            (
                "What is the maximum supported row count?",
                "What happens for oversized exports?",
                "What is the analytics event schema?",
                "Which sensitive fields must be excluded?",
                "What is the performance target?",
            ),
            1,
        )
    ]
    handoff = base(HANDOFF, "Document existing monthly report filters", 1)
    handoff["requirements"] = [
        requirement(1, "Document existing monthly report filters without changing behavior."),
        requirement(2, "Include examples for month and currency filters."),
        requirement(3, "A maintainer checks examples against existing documented behavior."),
    ]
    handoff["work_items"] = [work(1, "Document monthly report filters", handoff["requirements"], 1)]
    for name, payload, source, example in (
        ("feature", valid, FEATURE, "feature-request.md"),
        ("ambiguous", ambiguous, AMBIGUOUS, "ambiguous-request.md"),
        ("handoff", handoff, HANDOFF, "handoff-request.md"),
    ):
        spec = seal_specification(payload)
        write_json(
            ROOT / "src/agentic_product_ops/fixtures" / f"{name}.json", spec.model_dump(mode="json")
        )
        path = ROOT / "examples" / example
        path.parent.mkdir(exist_ok=True)
        path.write_text(source, encoding="utf-8", newline="\n")
    for model in (WorkSpecification, SpecificationApproval, LinearPublicationPlan, Handoff):
        write_json(
            ROOT / "evals/schemas" / f"{model.__name__}.schema.json", model.model_json_schema()
        )


if __name__ == "__main__":
    main()
