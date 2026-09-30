"""The current human decision for one exact revision, including renewal after expiry."""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Connection

from agentic_product_ops.adapters.persistence.store import Conflict, Missing, Store
from agentic_product_ops.domain.contracts import SpecificationApproval


def current_decision(
    store: Store,
    workspace: str,
    identifier: str,
    revision: int,
    connection: Connection | None = None,
) -> dict[str, Any]:
    try:
        return store.get(
            workspace, "decision_renewal", f"{identifier}:r{revision}", connection=connection
        )
    except Missing:
        return store.get(workspace, "decision", identifier, revision, connection=connection)


def record_decision(
    store: Store,
    conn: Connection,
    workspace: str,
    identifier: str,
    approval: SpecificationApproval,
    now: datetime,
) -> int:
    """Record the first decision, or renew an expired approval of the same exact revision.

    A rejection, or an approval that is still inside its window, stays final for its revision.
    Renewal is a new authenticated human approval; it never extends the earlier one.
    """
    record = {"approval_id": str(approval.approval_id), "decision": approval.decision}
    try:
        previous = current_decision(store, workspace, identifier, approval.revision, conn)
    except Missing:
        store.put(conn, workspace, "decision", identifier, approval.revision, record)
        return 0
    earlier = SpecificationApproval.model_validate_json(
        json.dumps(store.get(workspace, "approval", previous["approval_id"], connection=conn))
    )
    if (
        approval.decision != "approve"
        or earlier.decision != "approve"
        or earlier.content_digest != approval.content_digest
        or now < earlier.expires_at
    ):
        raise Conflict("decision already recorded for this revision")
    sequence = int(previous.get("sequence", 0)) + 1
    store.put(
        conn,
        workspace,
        "decision_renewal",
        f"{identifier}:r{approval.revision}",
        sequence,
        {**record, "sequence": sequence, "renews": previous["approval_id"]},
    )
    return sequence
