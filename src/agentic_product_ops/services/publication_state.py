"""Post-decision lifecycle state, derived from durable records instead of stored as a claim.

The Temporal workflow owns states up to the human decision. After it, authority is re-derived
from immutable records at every dispatch, so the state is computed from those same records and
cannot drift from them or be set by a caller.
"""

import json
from datetime import datetime

from sqlalchemy import select

from agentic_product_ops.adapters.persistence.store import Missing, Store, operations
from agentic_product_ops.domain.contracts import SpecificationApproval
from agentic_product_ops.services.decisions import current_decision
from agentic_product_ops.workflows.lifecycle import State


def publication_state(store: Store, workspace: str, identifier: str, now: datetime) -> State | None:
    """Return None while the pre-decision workflow still owns the specification."""
    if store.cancelled(workspace, identifier):
        return State.CANCELLED
    revision = int(store.get(workspace, "specification", identifier)["revision"])
    try:
        decision = current_decision(store, workspace, identifier, revision)
    except Missing:
        return None
    if decision["decision"] != "approve":
        return State.REJECTED
    approval = SpecificationApproval.model_validate_json(
        json.dumps(store.get(workspace, "approval", decision["approval_id"]))
    )
    plan = store.get(workspace, "publication_plan", identifier, revision)
    keys = [operation["operation_key"] for operation in plan["operations"]]
    with store.database.connect() as conn:
        statuses = {
            row.operation_key: row.status
            for row in conn.execute(
                select(operations.c.operation_key, operations.c.status).where(
                    operations.c.workspace == workspace, operations.c.operation_key.in_(keys)
                )
            )
        }
    if not statuses:
        return State.EXPIRED if now >= approval.expires_at else State.APPROVED
    if len(statuses) == len(keys) and set(statuses.values()) == {"SUCCEEDED"}:
        try:
            store.get(workspace, "handoff_export", identifier, revision)
            return State.HANDOFF_READY
        except Missing:
            return State.PUBLISHED
    for key, status in statuses.items():
        if status != "SUCCEEDED":
            try:
                # A dispatched write with no observed result must be reconciled, not resent.
                store.get(workspace, "native_dispatch_authority", key)
                return State.RECONCILIATION_REQUIRED
            except Missing:
                pass
    return State.LINEAR_PUBLISHING
