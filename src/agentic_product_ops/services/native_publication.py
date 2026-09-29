"""Governed native issue/relation publication through durable reservation and reconciliation."""

import json
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import Connection, func, insert, select, update

from agentic_product_ops.adapters.linear.native_graphql import NativeGraphQLAdapter
from agentic_product_ops.adapters.linear.native_plan import NativePlan, build_native_plan
from agentic_product_ops.adapters.linear.offline import OperationEvidence
from agentic_product_ops.adapters.persistence.store import Conflict, Store, operations
from agentic_product_ops.domain.contracts import SpecificationApproval, WorkSpecification
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy, validate_approval
from agentic_product_ops.services.authority import Authority
from agentic_product_ops.services.clarifications import load_clarifications
from agentic_product_ops.services.durable_analysis import recorded_review


class NativePublisher:
    def __init__(
        self,
        store: Store,
        provider: NativeGraphQLAdapter,
        authority: Authority,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if authority.store is not store:
            raise ValueError("publication authority must share Product Ops transaction store")
        self.store, self.provider, self.authority, self.clock = store, provider, authority, clock

    def publish(
        self,
        spec: WorkSpecification,
        plan: NativePlan,
        approval: SpecificationApproval,
        policy: ServerPolicy,
    ) -> tuple[OperationEvidence, ...]:
        if self.authority.workspace != policy.workspace_id or self.provider.scope != plan.scope:
            raise PolicyError("publication tenant configuration mismatch")
        answers = load_clarifications(self.store, spec, policy)
        if plan != build_native_plan(spec, policy, self.provider.scope, clarifications=answers):
            raise PolicyError("native publication plan changed")
        workspace, identifier = policy.workspace_id, str(spec.specification_id)

        def validate(conn: Connection) -> None:
            if self.store.lock_specification(conn, workspace, identifier):
                raise PolicyError("publication cancelled")
            current = self.store.get(workspace, "specification", identifier, connection=conn)
            recorded = self.store.get(
                workspace, "approval", str(approval.approval_id), connection=conn
            )
            stored_plan = self.store.get(
                workspace, "publication_plan", identifier, spec.revision, connection=conn
            )
            if (
                current["content_digest"] != spec.content_digest
                or recorded != approval.model_dump(mode="json")
                or stored_plan != plan.model_dump(mode="json")
            ):
                raise PolicyError("superseded or unrecorded publication authority")
            self.authority.validate_dispatch(conn, approval, spec)
            recorded_review(self.store, workspace, spec, policy)
            validate_approval(
                spec,
                approval,
                policy,
                authenticated_actor=approval.actor_id,
                plan_digest=plan.content_digest,
                operation_keys=tuple(o.operation_key for o in plan.operations),
                now=self.clock(),
                clarifications=answers,
            )

        def guard() -> None:
            with self.store.database.begin() as conn:
                validate(conn)
                self.store.put(
                    conn,
                    workspace,
                    "native_dispatch_authority",
                    operation.operation_key,
                    1,
                    {
                        "mode": self.provider.mode,
                        "approval_id": str(approval.approval_id),
                        "specification_digest": spec.content_digest,
                        "plan_digest": plan.content_digest,
                        "request_digest": operation.request_digest,
                        "dispatch_at": self.clock().isoformat(),
                    },
                )

        receipts: list[OperationEvidence] = []
        for operation in plan.operations:
            dispatch = False
            with self.store.database.begin() as conn:
                validate(conn)
                for prerequisite in operation.prerequisite_keys:
                    prior = (
                        conn.execute(
                            select(operations).where(
                                operations.c.workspace == workspace,
                                operations.c.operation_key == prerequisite,
                            )
                        )
                        .mappings()
                        .first()
                    )
                    if prior is None or prior["status"] != "SUCCEEDED":
                        raise PolicyError("native relation prerequisite incomplete")
                row = (
                    conn.execute(
                        select(operations).where(
                            operations.c.workspace == workspace,
                            operations.c.operation_key == operation.operation_key,
                        )
                    )
                    .mappings()
                    .first()
                )
                if row and (
                    row["request_digest"] != operation.request_digest
                    or self.store.decode_record(
                        (workspace, "operation", operation.operation_key), row["request"]
                    )
                    != operation.model_dump(mode="json")
                ):
                    raise Conflict("native operation identity reused with different content")
                if row is None:
                    conn.execute(
                        insert(operations).values(
                            workspace=workspace,
                            operation_key=operation.operation_key,
                            request_digest=operation.request_digest,
                            request=self.store.encode_record(
                                (workspace, "operation", operation.operation_key),
                                operation.model_dump(mode="json"),
                            ),
                            status="UNKNOWN",
                            attempt=1,
                            provider_id=None,
                            provider_request_id=None,
                            observed_at=self.clock().isoformat(),
                        )
                    )
                    dispatch = True
                elif row["status"] == "SUCCEEDED":
                    receipts.append(
                        OperationEvidence.model_validate_json(
                            json.dumps({name: row[name] for name in OperationEvidence.model_fields})
                        )
                    )
                    continue
            provider_id = None
            try:
                if not dispatch:
                    # A failed preflight did not acquire dispatch authority. It cannot be retried.
                    self.store.get(workspace, "native_dispatch_authority", operation.operation_key)
                provider_id = (
                    self.provider.create(operation, guard)
                    if dispatch
                    else self.provider.reconcile(operation)
                )
            except Exception:
                provider_id = None  # Intent remains UNKNOWN; never persist provider errors.
            receipt = OperationEvidence(
                operation_key=operation.operation_key,
                request_digest=operation.request_digest,
                attempt=1,
                status="SUCCEEDED" if provider_id else "UNKNOWN",
                provider_id=provider_id,
                provider_request_id=self.provider.last_request_id if provider_id else None,
                observed_at=self.clock(),
            )
            with self.store.database.begin() as conn:
                self.store.lock_specification(conn, workspace, identifier)
                # Preserve late success even if authority changed during the already-reserved write.
                # The next operation must pass validate again and cannot inherit that authority.
                if provider_id:
                    conn.execute(
                        update(operations)
                        .where(
                            operations.c.workspace == workspace,
                            operations.c.operation_key == operation.operation_key,
                            operations.c.request_digest == operation.request_digest,
                        )
                        .values(
                            status="SUCCEEDED",
                            provider_id=provider_id,
                            provider_request_id=receipt.provider_request_id,
                            observed_at=receipt.observed_at.isoformat(),
                        )
                    )
                self.store.put(
                    conn,
                    workspace,
                    "native_publication_observation",
                    operation.operation_key,
                    self._observation_revision(operation.operation_key, conn) + 1,
                    {"mode": self.provider.mode, "evidence": receipt.model_dump(mode="json")},
                )
            receipts.append(receipt)
            if receipt.status == "UNKNOWN":
                break
        return tuple(receipts)

    def _observation_revision(self, key: str, conn: Connection) -> int:
        from agentic_product_ops.adapters.persistence.store import artifacts

        return int(
            conn.execute(
                select(func.max(artifacts.c.revision)).where(
                    artifacts.c.workspace == self.authority.workspace,
                    artifacts.c.kind == "native_publication_observation",
                    artifacts.c.identity == key,
                )
            ).scalar_one()
            or 0
        )
