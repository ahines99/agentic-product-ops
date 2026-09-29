"""Activities revalidate PostgreSQL artifacts and approval receipts against current policy/time."""

import json
from datetime import UTC, datetime

from temporalio import activity
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError

from agentic_product_ops.adapters.linear.offline import build_plan
from agentic_product_ops.adapters.persistence.store import Missing, Store
from agentic_product_ops.domain.contracts import SpecificationApproval, WorkSpecification
from agentic_product_ops.policies.validation import (
    PolicyError,
    ServerPolicy,
    proposal_ready,
    validate_approval,
)
from agentic_product_ops.services.durable_analysis import analyze_specification, recorded_review
from agentic_product_ops.workflows.governance import GovernanceInput, GovernanceWorkflow


class GovernanceActivities:
    def __init__(self, store: Store, policy: ServerPolicy):
        self.store, self.policy = store, policy

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
            if self.store.cancelled(request.workspace, request.specification_id):
                return "CANCELLED"
            if result.state != "PROPOSED":
                return result.state
            proposal_ready(spec, self.policy)
        except PolicyError:
            return "AWAITING_CLARIFICATION"
        return "PROPOSED"

    @activity.defn
    async def validate_governance_receipt(self, request: GovernanceInput, approval_id: str) -> str:
        if self.store.cancelled(request.workspace, request.specification_id):
            return "CANCELLED"
        try:
            spec = self.specification(request)
            recorded_review(self.store, request.workspace, spec, self.policy)
        except PolicyError:
            return "REVISION_REQUIRED"
        try:
            approval = SpecificationApproval.model_validate_json(
                json.dumps(self.store.get(request.workspace, "approval", approval_id))
            )
            plan = build_plan(spec, self.policy)
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
            )
        except (Missing, ValueError):
            return "INVALID"
        return "APPROVED" if approval.decision == "approve" else "REJECTED"


async def dispatch_outbox(store: Store, client: Client, task_queue: str) -> int:
    count = 0
    pending = sorted(
        store.pending_workflows(),
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
