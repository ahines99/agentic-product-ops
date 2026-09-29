"""Signed public v2 handoff contract; execution state belongs exclusively to the consumer."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from agentic_product_ops.adapters.linear.native_plan import NativePlan
from agentic_product_ops.adapters.linear.offline import OperationEvidence
from agentic_product_ops.domain.clarifications import ClarificationReceipt
from agentic_product_ops.domain.contracts import (
    ID,
    Contract,
    Digest,
    SpecificationApproval,
    Timestamp,
    WorkSpecification,
)


class DispatchAuthority(Contract):
    operation_key: Digest
    mode: Literal["mock_transport", "live_provider"]
    approval_id: ID
    specification_digest: Digest
    plan_digest: Digest
    request_digest: Digest
    dispatch_at: Timestamp


class HandoffPayload(Contract):
    schema_version: Literal["2"] = "2"
    issuer: ID
    audience: Literal["agentic-delivery-os"] = "agentic-delivery-os"
    key_id: ID
    issued_at: Timestamp
    expires_at: Timestamp
    mode: Literal["mock_transport", "live_provider"]
    specification: WorkSpecification
    approval: SpecificationApproval
    plan: NativePlan
    publications: tuple[OperationEvidence, ...]
    dispatches: tuple[DispatchAuthority, ...]
    clarifications: tuple[ClarificationReceipt, ...]

    @model_validator(mode="after")
    def integrity(self) -> Self:
        spec, approval, plan = self.specification, self.approval, self.plan
        if not 0 < (self.expires_at - self.issued_at).total_seconds() <= 3600:
            raise ValueError("handoff lifetime outside bound")
        if spec.risk.tier not in {0, 1} or any(w.risk_tier not in {0, 1} for w in spec.work_items):
            raise ValueError("Delivery OS risk boundary exceeded")
        if (
            (
                approval.specification_id,
                approval.revision,
                approval.content_digest,
                approval.decision,
            )
            != (
                spec.specification_id,
                spec.revision,
                spec.content_digest,
                "approve",
            )
            or plan.specification_digest != spec.content_digest
            or approval.scope.plan_digest != plan.content_digest
        ):
            raise ValueError("handoff approval binding mismatch")
        keys = tuple(o.operation_key for o in plan.operations)
        if approval.scope.operation_keys != keys or approval.scope.allowed_mutation_count != len(
            keys
        ):
            raise ValueError("handoff mutation scope mismatch")
        if (
            tuple(p.operation_key for p in self.publications) != keys
            or tuple(d.operation_key for d in self.dispatches) != keys
        ):
            raise ValueError("publication evidence incomplete or reordered")
        for operation, receipt, dispatch in zip(
            plan.operations, self.publications, self.dispatches, strict=True
        ):
            if (
                receipt.status != "SUCCEEDED"
                or receipt.provider_id != str(operation.target_id)
                or receipt.request_digest != operation.request_digest
                or dispatch.request_digest != operation.request_digest
                or dispatch.mode != self.mode
                or dispatch.approval_id != str(approval.approval_id)
                or dispatch.specification_digest != spec.content_digest
                or dispatch.plan_digest != plan.content_digest
                or not approval.issued_at <= dispatch.dispatch_at < approval.expires_at
                or not dispatch.dispatch_at <= receipt.observed_at <= self.issued_at
            ):
                raise ValueError("publication/dispatch evidence does not match approval")
        return self


class SignedHandoff(Contract):
    payload: HandoffPayload
    payload_digest: Digest
    algorithm: Literal["Ed25519"] = "Ed25519"
    signature: Annotated[str, Field(min_length=88, max_length=88)]
