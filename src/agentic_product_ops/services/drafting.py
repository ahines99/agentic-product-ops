"""Exact source-digest fixture lookup, not NLP or a general requirements engine."""

import json
from importlib.resources import files
from uuid import NAMESPACE_URL, uuid5

from agentic_product_ops.domain.contracts import (
    WorkSpecification,
    seal_specification,
    source_digest,
)
from agentic_product_ops.policies.validation import ServerPolicy, proposal_ready
from agentic_product_ops.workflows.lifecycle import State

FIXED_TIME = "2026-09-28T00:00:00Z"


def draft(text: str, *, use_fixtures: bool = True) -> tuple[WorkSpecification, State]:
    digest = source_digest(text)
    resource = files("agentic_product_ops.fixtures")
    for name in ("feature", "ambiguous", "handoff") if use_fixtures else ():
        spec = WorkSpecification.model_validate_json(resource.joinpath(f"{name}.json").read_bytes())
        if spec.source_digest == digest:
            if name == "ambiguous":
                return spec, State.AWAITING_CLARIFICATION
            proposal_ready(spec, ServerPolicy())
            return spec, State.PROPOSED
    payload = {
        "schema_version": "1",
        "specification_id": str(uuid5(NAMESPACE_URL, digest)),
        "revision": 1,
        "source_digest": digest,
        "title": "Unrecognized offline input",
        "objective": "Clarify this request with an authorized human before proposing work.",
        "source_statements": [{"id": "S0", "text": text}],
        "requirements": [],
        "unresolved_questions": [
            {
                "id": "Q1",
                "question": "What behavior and constraints are approved?",
                "why_it_matters": (
                    "M0 has no general requirements engine; unknown inputs fail closed."
                ),
                "affected_requirement_ids": [],
                "blocking": True,
                "resolution": None,
                "resolved_by": None,
                "resolved_at": None,
            }
        ],
        "assumptions": [],
        "repository_context": None,
        "risk": {
            "tier": 3,
            "reasons": ["Unclassified input held at maximum risk until reviewed."],
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
            "mode": "unrecognized_input",
            "created_at": FIXED_TIME,
            "producer": "offline-fixture-router",
            "source_kind": "prompt",
            "policy_refs": [],
            "clarification_refs": [],
        },
    }
    return seal_specification(payload), State.AWAITING_CLARIFICATION


def load_fixture(name: str) -> WorkSpecification:
    if name not in {"feature", "ambiguous", "handoff"}:
        raise ValueError("unknown bundled fixture")
    return WorkSpecification.model_validate_json(
        files("agentic_product_ops.fixtures").joinpath(f"{name}.json").read_bytes()
    )


def output_json(spec: WorkSpecification, state: State) -> str:
    return json.dumps(
        {
            "mode": "offline_fixture",
            "state": state.value,
            "specification": spec.model_dump(mode="json"),
        },
        indent=2,
        ensure_ascii=False,
    )
