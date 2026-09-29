"""Temporal owns lifecycle; PostgreSQL owns immutable artifacts and authenticated receipts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError


@dataclass
class GovernanceInput:
    workspace: str
    specification_id: str
    content_digest: str
    wait_seconds: int = 3600


@workflow.defn
class GovernanceWorkflow:
    def __init__(self) -> None:
        self.state = "RECEIVED"
        self.receipt = ""
        self.accepted_receipt = ""
        self.cancel_requested = False

    @workflow.query
    def status(self) -> str:
        return self.state

    @workflow.query
    def decision_receipt(self) -> str:
        return self.accepted_receipt

    @workflow.signal
    def decision_recorded(self, approval_id: str) -> None:
        # Signals are references; only validation of a stored receipt grants authority.
        if len(approval_id) <= 128 and self.state in {
            "RECEIVED",
            "NORMALIZED",
            "AWAITING_APPROVAL",
        }:
            self.receipt = approval_id

    @workflow.signal
    def cancel(self) -> None:
        self.cancel_requested = True

    @workflow.run
    async def run(self, request: GovernanceInput) -> str:
        if not 0 < request.wait_seconds <= 86400:
            self.state = "PAUSED"
            return self.state
        try:
            self.state = "NORMALIZED"
            readiness = await workflow.execute_activity(
                "prepare_governance",
                request,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=2),
                result_type=str,
            )
            if self.cancel_requested:
                self.state = "CANCELLED"
            elif readiness != "PROPOSED":
                self.state = readiness
            else:
                self.state = "AWAITING_APPROVAL"
                deadline = workflow.now() + timedelta(seconds=request.wait_seconds)
                while self.state == "AWAITING_APPROVAL":
                    try:
                        await workflow.wait_condition(
                            lambda: bool(self.receipt) or self.cancel_requested,
                            timeout=deadline - workflow.now(),
                        )
                    except TimeoutError:
                        self.state = "EXPIRED"
                        break
                    if self.cancel_requested:
                        self.state = "CANCELLED"
                        break
                    approval_id, self.receipt = self.receipt, ""
                    verdict = await workflow.execute_activity(
                        "validate_governance_receipt",
                        args=[request, approval_id],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=2),
                        result_type=str,
                    )
                    if self.cancel_requested:
                        self.state = "CANCELLED"
                    elif verdict in {
                        "APPROVED",
                        "REJECTED",
                        "EXPIRED",
                        "REVISION_REQUIRED",
                        "CANCELLED",
                    }:
                        self.accepted_receipt = approval_id
                        self.state = verdict
                    # Invalid references cannot transition state or extend expiry.
        except ActivityError:
            self.state = "PAUSED"
        return self.state  # No publication activity is registered; live writes remain disabled.
