"""Create signed immutable exports from verified Product Ops records, never from model output."""

import base64
import json
from datetime import datetime, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select

from agentic_product_ops.adapters.linear.native_plan import NativePlan, build_native_plan
from agentic_product_ops.adapters.linear.offline import OperationEvidence
from agentic_product_ops.adapters.persistence.store import Missing, Store, operations
from agentic_product_ops.domain.contracts import (
    SpecificationApproval,
    WorkSpecification,
    canonical_digest,
)
from agentic_product_ops.domain.handoff import DispatchAuthority, HandoffPayload, SignedHandoff
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy, validate_approval
from agentic_product_ops.services.authority import Authority
from agentic_product_ops.services.clarifications import load_clarifications
from agentic_product_ops.services.durable_analysis import recorded_review

SIGNING_DOMAIN = b"AgenticProductOps/Handoff/v2\x00"


def export_signed_handoff(
    store: Store,
    authority: Authority,
    policy: ServerPolicy,
    *,
    specification_id: str,
    approval_id: str,
    issuer: str,
    key_id: str,
    signing_key: Ed25519PrivateKey,
    now: datetime,
) -> SignedHandoff:
    workspace = policy.workspace_id
    with store.database.begin() as conn:
        if store.lock_specification(conn, workspace, specification_id):
            raise PolicyError("cancelled specification cannot be handed off")
        spec = WorkSpecification.model_validate_json(
            json.dumps(store.get(workspace, "specification", specification_id, connection=conn))
        )
        approval = SpecificationApproval.model_validate_json(
            json.dumps(store.get(workspace, "approval", approval_id, connection=conn))
        )
        plan = NativePlan.model_validate_json(
            json.dumps(
                store.get(
                    workspace, "publication_plan", specification_id, spec.revision, connection=conn
                )
            )
        )
        answers = load_clarifications(store, spec, policy)
        if spec.risk.tier not in policy.handoff_tiers or plan != build_native_plan(
            spec, policy, plan.scope, clarifications=answers
        ):
            raise PolicyError("handoff scope or tier denied")
        authority.validate_dispatch(conn, approval, spec)
        recorded_review(store, workspace, spec, policy)
        receipts, dispatches = [], []
        for operation in plan.operations:
            row = (
                conn.execute(
                    select(operations).where(
                        operations.c.workspace == workspace,
                        operations.c.operation_key == operation.operation_key,
                    )
                )
                .mappings()
                .one()
            )
            receipt = OperationEvidence.model_validate_json(
                json.dumps({field: row[field] for field in OperationEvidence.model_fields})
            )
            record = store.get(
                workspace, "native_dispatch_authority", operation.operation_key, connection=conn
            )
            dispatch = DispatchAuthority.model_validate_json(
                json.dumps({**record, "operation_key": operation.operation_key})
            )
            if receipt.status != "SUCCEEDED" or str(dispatch.approval_id) != approval_id:
                # Only a fully observed publication, dispatched under this one approval, is
                # handed off. A publication completed across a renewed approval stays held.
                raise PolicyError("handoff requires complete publication under one approval")
            validate_approval(
                spec,
                approval,
                policy,
                authenticated_actor=approval.actor_id,
                plan_digest=plan.content_digest,
                operation_keys=tuple(o.operation_key for o in plan.operations),
                now=dispatch.dispatch_at,
                clarifications=answers,
            )
            receipts.append(receipt)
            dispatches.append(dispatch)
        payload = HandoffPayload(
            issuer=issuer,
            key_id=key_id,
            issued_at=now,
            expires_at=now + timedelta(minutes=15),
            mode=dispatches[0].mode,
            specification=spec,
            approval=approval,
            plan=plan,
            publications=tuple(receipts),
            dispatches=tuple(dispatches),
            clarifications=answers,
        )
        digest = canonical_digest(payload.model_dump(mode="json"))
        signature = base64.b64encode(signing_key.sign(SIGNING_DOMAIN + digest.encode())).decode()
        envelope = SignedHandoff(payload=payload, payload_digest=digest, signature=signature)
        # Export identity includes the digest, retaining every signed envelope without overwrite.
        store.put(conn, workspace, "signed_handoff", digest, 1, envelope)
        try:
            store.get(workspace, "handoff_export", specification_id, spec.revision, connection=conn)
        except Missing:
            store.put(
                conn,
                workspace,
                "handoff_export",
                specification_id,
                spec.revision,
                {"first_payload_digest": digest, "approval_id": approval_id},
            )
        return envelope
