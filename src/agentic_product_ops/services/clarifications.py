"""Load answer authority from immutable records and verify its original question lineage."""

import json

from agentic_product_ops.adapters.persistence.store import Store
from agentic_product_ops.domain.clarifications import ClarificationReceipt
from agentic_product_ops.domain.contracts import WorkSpecification
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy


def load_clarifications(
    store: Store, spec: WorkSpecification, policy: ServerPolicy
) -> tuple[ClarificationReceipt, ...]:
    receipts: list[ClarificationReceipt] = []
    for reference in spec.provenance.clarification_refs:
        receipt = ClarificationReceipt.model_validate_json(
            json.dumps(store.get(policy.workspace_id, "clarification", reference))
        )
        if (
            receipt.id != reference
            or receipt.workspace_id != policy.workspace_id
            or receipt.specification_id != spec.specification_id
            or receipt.base_revision >= spec.revision
            or receipt.actor_id not in policy.approvers
        ):
            raise PolicyError("clarification authority mismatch")
        original = WorkSpecification.model_validate_json(
            json.dumps(
                store.get(
                    policy.workspace_id,
                    "specification",
                    str(spec.specification_id),
                    receipt.base_revision,
                )
            )
        )
        question = next(
            (q for q in original.unresolved_questions if q.id == receipt.question_id), None
        )
        if (
            original.content_digest != receipt.base_digest
            or question is None
            or question.question != receipt.question_text
            or question.resolution is not None
            or receipt.resolved_at < original.provenance.created_at
        ):
            raise PolicyError("clarification question lineage mismatch")
        receipts.append(receipt)
    return tuple(receipts)
