"""Handoff schema and consumer verification; no Delivery OS internal imports."""

from typing import Literal, Self

from pydantic import model_validator

from agentic_product_ops.adapters.linear.offline import (
    LinearPublicationPlan,
    OperationEvidence,
    build_plan,
)
from agentic_product_ops.domain.contracts import (
    Contract,
    Digest,
    SpecificationApproval,
    WorkSpecification,
    canonical_digest,
)
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy


class Handoff(Contract):
    schema_version: Literal["1"] = "1"
    mode: Literal["offline_simulation"] = "offline_simulation"
    specification: WorkSpecification
    approval: SpecificationApproval
    plan: LinearPublicationPlan
    publications: tuple[OperationEvidence, ...]
    artifact_digest: Digest

    @model_validator(mode="after")
    def integrity(self) -> Self:
        spec, approval = self.specification, self.approval
        if (
            approval.specification_id,
            approval.revision,
            approval.content_digest,
            approval.decision,
        ) != (spec.specification_id, spec.revision, spec.content_digest, "approve"):
            raise ValueError("handoff approval mismatch")
        if self.plan.specification_digest != spec.content_digest or (
            approval.scope.plan_digest != self.plan.content_digest
        ):
            raise ValueError("handoff plan mismatch")
        if approval.policy_version != spec.approval_policy.policy_version:
            raise ValueError("handoff approval policy mismatch")
        if (
            approval.scope.operation_keys != tuple(o.operation_key for o in self.plan.operations)
            or approval.scope.allowed_mutation_count != len(self.plan.operations)
            or approval.scope.workspace_id != self.plan.workspace_id
            or set(approval.scope.team_ids) != {o.team_id for o in self.plan.operations}
            or set(approval.scope.repository_ids)
            != {w.repository_id for w in spec.work_items if w.repository_id is not None}
            or {o.work_item_id for o in self.plan.operations}
            != {w.local_id for w in spec.work_items}
            or len(self.plan.operations) != len(spec.work_items)
        ):
            raise ValueError("handoff approved operation scope mismatch")
        expected = {o.operation_key: o.request_digest for o in self.plan.operations}
        observed = {o.operation_key: o.request_digest for o in self.publications}
        if expected != observed or len(self.publications) != len(expected):
            raise ValueError("incomplete publication evidence")
        if any(p.status != "SUCCEEDED" or not p.provider_id for p in self.publications):
            raise ValueError("unknown publication cannot be handed off")
        if len({p.provider_id for p in self.publications}) != len(self.publications):
            raise ValueError("provider object reused across operations")
        if canonical_digest(self.model_dump(mode="json", exclude={"artifact_digest"})) != (
            self.artifact_digest
        ):
            raise ValueError("handoff artifact digest mismatch")
        return self


def export_handoff(
    spec: WorkSpecification,
    approval: SpecificationApproval,
    plan: LinearPublicationPlan,
    publications: tuple[OperationEvidence, ...],
    policy: ServerPolicy,
) -> Handoff:
    if spec.risk.tier not in policy.handoff_tiers:
        raise PolicyError("Delivery OS accepted risk tiers exclude this work")
    if plan != build_plan(spec, policy):
        raise PolicyError("handoff plan mismatch")
    # Historical approval must have been valid at every successful fake write.
    from agentic_product_ops.policies.validation import validate_approval

    for receipt in publications:
        validate_approval(
            spec,
            approval,
            policy,
            authenticated_actor=approval.actor_id,
            plan_digest=plan.content_digest,
            operation_keys=tuple(o.operation_key for o in plan.operations),
            now=receipt.observed_at,
        )
    body = {
        "schema_version": "1",
        "mode": "offline_simulation",
        "specification": spec.model_dump(mode="json"),
        "approval": approval.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
        "publications": [p.model_dump(mode="json") for p in publications],
    }
    import json

    return Handoff.model_validate_json(
        json.dumps({**body, "artifact_digest": canonical_digest(body)})
    )
