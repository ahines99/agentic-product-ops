"""Activities revalidate PostgreSQL artifacts and approval receipts against current policy/time."""

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime

from temporalio import activity
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError

from agentic_product_ops.adapters.linear.native_plan import LinearScope, build_native_plan
from agentic_product_ops.adapters.linear.offline import build_plan
from agentic_product_ops.adapters.model.contracts import RuntimeConfiguration
from agentic_product_ops.adapters.model.runner import ModelProvider
from agentic_product_ops.adapters.persistence.store import Missing, Store
from agentic_product_ops.domain.contracts import SpecificationApproval, WorkSpecification
from agentic_product_ops.policies.validation import (
    PolicyError,
    ServerPolicy,
    proposal_ready,
    validate_approval,
)
from agentic_product_ops.services.authority import Authority
from agentic_product_ops.services.clarifications import load_clarifications
from agentic_product_ops.services.durable_analysis import (
    analyze_specification,
    passing_review,
    recorded_review,
)
from agentic_product_ops.services.revisions import revise_specification
from agentic_product_ops.workflows.governance import GovernanceInput, GovernanceWorkflow


class GovernanceActivities:
    def __init__(
        self,
        store: Store,
        policy: ServerPolicy,
        *,
        revision_configuration: RuntimeConfiguration | None = None,
        revision_provider: Callable[[], ModelProvider] | None = None,
        authority: Authority | None = None,
        linear_scope: LinearScope | None = None,
    ):
        self.store, self.policy = store, policy
        self.authority = authority
        self.linear_scope = linear_scope
        if (revision_configuration is None) != (revision_provider is None):
            raise ValueError("revision runtime requires configuration and provider together")
        self.revision_configuration, self.revision_provider = (
            revision_configuration,
            revision_provider,
        )

    def specification(self, request: GovernanceInput) -> WorkSpecification:
        if request.workspace != self.policy.workspace_id:
            raise PolicyError("workspace denied")
        spec = WorkSpecification.model_validate_json(
            json.dumps(self.store.get(request.workspace, "specification", request.specification_id))
        )
        if spec.content_digest != request.content_digest:
            raise PolicyError("superseded specification")
        return spec

    @activity.defn
    async def prepare_governance(self, request: GovernanceInput) -> str:
        return await asyncio.to_thread(self.prepare, request)

    def prepare(self, request: GovernanceInput) -> str:
        if self.store.cancelled(request.workspace, request.specification_id):
            return "CANCELLED"
        try:
            spec = self.specification(request)
            result = analyze_specification(
                self.store,
                request.workspace,
                request.specification_id,
                request.content_digest,
                self.policy,
            )
            if (
                result.state != "PROPOSED"
                and (
                    spec.provenance.clarification_refs
                    or spec.provenance.mode == "unrecognized_input"
                )
                and self.revision_configuration is not None
                and self.revision_provider is not None
            ):
                result = revise_specification(
                    self.store,
                    request.specification_id,
                    request.content_digest,
                    self.policy,
                    self.revision_configuration,
                    self.revision_provider(),
                    initial=spec.provenance.mode == "unrecognized_input"
                    and not spec.provenance.clarification_refs,
                )
                if result.state == "PROPOSED":
                    # Promotion queued a new workflow; the old digest cannot be approved.
                    return "REVISION_REQUIRED"
            if self.store.cancelled(request.workspace, request.specification_id):
                return "CANCELLED"
            if result.state != "PROPOSED":
                return result.state
            proposal_ready(
                spec,
                self.policy,
                clarifications=load_clarifications(self.store, spec, self.policy),
                review=result.review,
            )
        except PolicyError:
            return "AWAITING_CLARIFICATION"
        return "PROPOSED"

    @activity.defn
    async def validate_governance_receipt(self, request: GovernanceInput, approval_id: str) -> str:
        return await asyncio.to_thread(self.validate_receipt, request, approval_id)

    def validate_receipt(self, request: GovernanceInput, approval_id: str) -> str:
        if self.store.cancelled(request.workspace, request.specification_id):
            return "CANCELLED"
        try:
            spec = self.specification(request)
            recorded_review(self.store, request.workspace, spec, self.policy)
            review = passing_review(self.store, request.workspace, spec, self.policy)
        except PolicyError:
            return "REVISION_REQUIRED"
        try:
            approval = SpecificationApproval.model_validate_json(
                json.dumps(self.store.get(request.workspace, "approval", approval_id))
            )
            if self.authority:
                with self.store.database.begin() as conn:
                    self.authority.validate_dispatch(conn, approval, spec)
            answers = load_clarifications(self.store, spec, self.policy)
            plan = (
                build_native_plan(
                    spec, self.policy, self.linear_scope, clarifications=answers, review=review
                )
                if self.linear_scope
                else build_plan(spec, self.policy, clarifications=answers, review=review)
            )
            # A rejection has the same actor/scope/content requirements as an approval.
            validation = approval.model_copy(update={"decision": "approve"})
            validate_approval(
                spec,
                validation,
                self.policy,
                authenticated_actor=approval.actor_id,
                plan_digest=plan.content_digest,
                operation_keys=tuple(o.operation_key for o in plan.operations),
                now=datetime.now(UTC),
                clarifications=answers,
                review=review,
            )
        except (Missing, ValueError):
            return "INVALID"
        return "APPROVED" if approval.decision == "approve" else "REJECTED"


async def dispatch_outbox(
    store: Store, client: Client, task_queue: str, workspace: str | None = None
) -> int:
    """Start or signal pending workflows; a profile worker passes its own workspace.

    Without the filter a worker would start another profile's work on its own queue and run
    it under the wrong server policy.
    """
    count = 0
    pending = sorted(
        store.pending_workflows(workspace),
        key=lambda row: {"decision": 1, "cancel": 2}.get(
            json.loads(row["payload"]).get("action"), 0
        ),
    )
    for item in pending:
        payload = json.loads(item["payload"])
        if payload.get("action") == "cancel":
            if not store.cancelled(item["workspace"], payload["specification_id"]):
                raise PolicyError("cancellation receipt missing")
            handle = client.get_workflow_handle(payload["target_workflow"])
            try:
                await handle.signal(GovernanceWorkflow.cancel)
            except RPCError:
                if await handle.query(GovernanceWorkflow.status) not in {
                    "CANCELLED",
                    "APPROVED",
                    "REJECTED",
                    "EXPIRED",
                    "PAUSED",
                    "AWAITING_CLARIFICATION",
                    "REVISION_REQUIRED",
                }:
                    raise
            store.mark_dispatched(item["workspace"], item["workflow_id"])
            count += 1
            continue
        if payload.get("action") == "decision":
            handle = client.get_workflow_handle(
                payload.get("target_workflow", f"product-ops-{payload['specification_id']}")
            )
            try:
                await handle.signal(GovernanceWorkflow.decision_recorded, payload["approval_id"])
            except RPCError:
                # Lost signal acknowledgement may be retried after workflow completion.
                observed = await handle.query(GovernanceWorkflow.decision_receipt)
                if observed != payload["approval_id"]:
                    raise
            store.mark_dispatched(item["workspace"], item["workflow_id"])
            count += 1
            continue
        request = GovernanceInput(
            workspace=item["workspace"],
            specification_id=payload["specification_id"],
            content_digest=payload["content_digest"],
        )
        try:
            await client.start_workflow(
                GovernanceWorkflow.run,
                request,
                id=item["workflow_id"],
                task_queue=task_queue,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            )
        except WorkflowAlreadyStartedError:
            pass  # Crash after start but before outbox acknowledgement is safe to replay.
        store.mark_dispatched(item["workspace"], item["workflow_id"])
        count += 1
    return count
