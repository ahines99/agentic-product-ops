"""Crash-safe *simulation* intent ledger. No real provider is wired into the application."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from agentic_product_ops.adapters.linear.offline import (
    FakeLinear,
    LinearPublicationPlan,
    OperationEvidence,
    build_plan,
)
from agentic_product_ops.adapters.persistence.store import (
    Conflict,
    Missing,
    Store,
    controls,
    operations,
)
from agentic_product_ops.domain.contracts import SpecificationApproval, WorkSpecification
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy, validate_approval


class DurableSimulationPublisher:
    def __init__(
        self,
        store: Store,
        provider: FakeLinear,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.store, self.provider, self.clock = store, provider, clock

    def lock_control(self, conn: Connection, workspace: str, specification_id: str) -> bool:
        factory = pg_insert if conn.dialect.name == "postgresql" else sqlite_insert
        conn.execute(
            factory(controls)
            .values(workspace=workspace, specification_id=specification_id, cancelled=0)
            .on_conflict_do_nothing()
        )
        return bool(
            conn.execute(
                select(controls.c.cancelled)
                .where(
                    controls.c.workspace == workspace,
                    controls.c.specification_id == specification_id,
                )
                .with_for_update()
            ).scalar_one()
        )

    def cancel(self, workspace: str, specification_id: str) -> None:
        with self.store.database.begin() as conn:
            self.lock_control(conn, workspace, specification_id)
            conn.execute(
                update(controls)
                .where(
                    controls.c.workspace == workspace,
                    controls.c.specification_id == specification_id,
                )
                .values(cancelled=1)
            )

    def publish(
        self,
        spec: WorkSpecification,
        plan: LinearPublicationPlan,
        approval: SpecificationApproval,
        policy: ServerPolicy,
        actor: str,
    ) -> tuple[OperationEvidence, ...]:
        if plan != build_plan(spec, policy):
            raise PolicyError("publication plan changed")
        receipts: list[OperationEvidence] = []
        for operation in plan.operations:
            dispatch = False
            with self.store.database.begin() as conn:
                if self.lock_control(conn, policy.workspace_id, str(spec.specification_id)):
                    raise PolicyError("cancelled")
                # An older approved revision cannot dispatch after a newer revision is recorded.
                try:
                    latest = self.store.get(
                        policy.workspace_id,
                        "specification",
                        str(spec.specification_id),
                        connection=conn,
                    )
                except Missing:
                    latest = spec.model_dump(mode="json")
                if latest["content_digest"] != spec.content_digest:
                    raise PolicyError("superseded specification")
                now = self.clock()
                validate_approval(
                    spec,
                    approval,
                    policy,
                    authenticated_actor=actor,
                    plan_digest=plan.content_digest,
                    operation_keys=tuple(o.operation_key for o in plan.operations),
                    now=now,
                )
                query = select(operations).where(
                    operations.c.workspace == policy.workspace_id,
                    operations.c.operation_key == operation.operation_key,
                )
                row = conn.execute(query).mappings().first()
                if row is not None and row["request_digest"] != operation.request_digest:
                    raise Conflict("operation key content conflict")
                if row is None:
                    conn.execute(
                        insert(operations).values(
                            workspace=policy.workspace_id,
                            operation_key=operation.operation_key,
                            request_digest=operation.request_digest,
                            request=operation.model_dump_json(),
                            status="UNKNOWN",
                            attempt=1,
                            provider_id=None,
                            provider_request_id=None,
                            observed_at=now.isoformat(),
                        )
                    )
                    dispatch = True
                elif row["status"] == "SUCCEEDED":
                    receipts.append(
                        OperationEvidence.model_validate_json(
                            json.dumps({key: row[key] for key in OperationEvidence.model_fields})
                        )
                    )
                    continue
            # Committed intent is the dispatch boundary. Cancellation cannot undo an in-flight call.
            provider_id = None
            if dispatch:
                try:
                    provider_id = self.provider.create(operation)
                except Exception:
                    provider_id = None  # Preserve UNKNOWN without logging provider content.
            else:
                provider_id = self.provider.reconcile(operation)
            evidence = OperationEvidence(
                operation_key=operation.operation_key,
                request_digest=operation.request_digest,
                attempt=1,
                status="SUCCEEDED" if provider_id else "UNKNOWN",
                provider_id=provider_id,
                provider_request_id=f"fake-request-{provider_id}" if provider_id else None,
                observed_at=self.clock(),
            )
            if provider_id:
                with self.store.database.begin() as conn:
                    conn.execute(
                        update(operations)
                        .where(
                            operations.c.workspace == policy.workspace_id,
                            operations.c.operation_key == operation.operation_key,
                            operations.c.request_digest == operation.request_digest,
                        )
                        .values(
                            status="SUCCEEDED",
                            provider_id=provider_id,
                            provider_request_id=evidence.provider_request_id,
                            observed_at=evidence.observed_at.isoformat(),
                        )
                    )
            receipts.append(evidence)
            if evidence.status == "UNKNOWN":
                break
        return tuple(receipts)
