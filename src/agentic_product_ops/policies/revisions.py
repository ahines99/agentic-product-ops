"""Revision invariants independent of any model's interpretation or confidence."""

from agentic_product_ops.domain.clarifications import ClarificationReceipt
from agentic_product_ops.domain.contracts import WorkSpecification
from agentic_product_ops.policies.validation import (
    PolicyError,
    ServerPolicy,
    blocking_findings,
    validate_scope,
)


def validate_revision(
    base: WorkSpecification,
    candidate: WorkSpecification,
    receipts: tuple[ClarificationReceipt, ...],
    policy: ServerPolicy,
) -> None:
    if (
        candidate.specification_id != base.specification_id
        or candidate.revision != base.revision + 1
        or candidate.source_digest != base.source_digest
        or candidate.source_statements != base.source_statements
        or candidate.repository_context != base.repository_context
        or candidate.approval_policy != base.approval_policy
        or candidate.provenance.clarification_refs != base.provenance.clarification_refs
        or candidate.risk.tier < base.risk.tier
    ):
        raise PolicyError("revision changed immutable scope, source, lineage, or risk")
    if candidate.unresolved_questions != base.unresolved_questions:
        raise PolicyError("revision cannot remove or rewrite questions or authenticated answers")
    original = {r.id: r for r in base.requirements}
    revised = {r.id: r for r in candidate.requirements}
    if not original.keys() <= revised.keys():
        raise PolicyError("revision cannot silently remove requirements")
    for identity, requirement in original.items():
        new = revised[identity]
        if requirement.model_dump(exclude={"needs_human_decision"}) != new.model_dump(
            exclude={"needs_human_decision"}
        ):
            raise PolicyError("revision cannot silently rewrite existing requirements")
        if requirement.needs_human_decision and not new.needs_human_decision:
            questions = [
                q for q in base.unresolved_questions if identity in q.affected_requirement_ids
            ]
            if not questions or any(q.resolution is None for q in questions):
                raise PolicyError("human decision was not answered")
    for identity in revised.keys() - original.keys():
        if revised[identity].provenance != "human_clarification":
            raise PolicyError("added revision requirements require human clarification provenance")
    if any(
        "clarification" in finding
        for finding in blocking_findings(candidate, clarifications=receipts)
    ):
        raise PolicyError("revision answers are not authenticated")
    validate_scope(candidate, policy)
