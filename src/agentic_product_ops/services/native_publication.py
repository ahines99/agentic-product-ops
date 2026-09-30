"""Governed native issue/relation publication through durable reservation and reconciliation."""

import json
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import Connection, func, insert, select, update

from agentic_product_ops.adapters.linear.native_graphql import NativeGraphQLAdapter
from agentic_product_ops.adapters.linear.native_plan import (
    NativeOperation,
    NativePlan,
    build_native_plan,
)
from agentic_product_ops.adapters.linear.offline import OperationEvidence
from agentic_product_ops.adapters.persistence.store import (
    Conflict,
    Missing,
    Store,
    artifacts,
    operations,
)
from agentic_product_ops.domain.contracts import SpecificationApproval, WorkSpecification
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy, validate_approval
from agentic_product_ops.services.authority import Authority
from agentic_product_ops.services.clarifications import load_clarifications
from agentic_product_ops.services.durable_analysis import recorded_review


def publication_writes(
    store: Store, conn: Connection, workspace: str, identifier: str, revisions: range
) -> bool:
    """Whether any planned operation of these revisions has a recorded write intent."""
    for revision in revisions:
        try:
            stored = store.get(workspace, "publication_plan", identifier, revision, connection=conn)
        except Missing:
            continue
        keys = [operation["operation_key"] for operation in stored["operations"]]
        if conn.execute(
            select(operations.c.operation_key)
            .where(operations.c.workspace == workspace, operations.c.operation_key.in_(keys))
            .limit(1)
        ).first():
            return True
    return False


class NativePublisher:
    def __init__(
        self,
        store: Store,
        provider: NativeGraphQLAdapter,
        authority: Authority,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        source_guard: Callable[[str], None] | None = None,
        allow_revision_republication: bool = False,
    ) -> None:
        if authority.store is not store:
            raise ValueError("publication authority must share Product Ops transaction store")
        self.store, self.provider, self.authority, self.clock = store, provider, authority, clock
        self.source_guard = source_guard
        # Operator assembly choice, never source text: publish a new revision's tickets although
        # an earlier revision already wrote some. Downstream supersedes; Linear keeps both sets.
        self.allow_revision_republication = allow_revision_republication

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
            if self.source_guard is not None:
                self.source_guard(identifier)
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

        with self.store.database.begin() as conn:
            if not self.allow_revision_republication and publication_writes(
                self.store, conn, workspace, identifier, range(1, spec.revision)
            ):
                # New revisions derive new provider identities. Without a supersession policy,
                # writing them beside an earlier revision's tickets would duplicate work.
                raise PolicyError("earlier revision already has publication writes")
            validate(conn)

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
                elif not self._dispatched(conn, workspace, operation.operation_key):
                    # Dispatch authority is committed immediately before the mutation is sent.
                    # Its absence proves no write left this process, so the intent may be
                    # dispatched under the authority just validated.
                    dispatch = True
            provider_id = None
            try:
                provider_id = (
                    self.provider.create(operation, guard)
                    if dispatch
                    else self.provider.reconcile(operation)
                )
            except Exception:
                provider_id = None  # Intent remains UNKNOWN; never persist provider errors.
            # Preserve late success even if authority changed during the already-reserved write.
            # The next operation must pass validate again and cannot inherit that authority.
            receipt = self._observe(workspace, identifier, operation, provider_id)
            receipts.append(receipt)
            if receipt.status == "UNKNOWN":
                break
        return tuple(receipts)

    def reconcile(
        self, spec: WorkSpecification, plan: NativePlan, policy: ServerPolicy
    ) -> tuple[OperationEvidence, ...]:
        """Read-only recovery of recorded intents. It can observe a write, never send one.

        Observation needs no unexpired approval: an expired or revoked approval must not hide
        a ticket that its earlier, authorized dispatch already created.
        """
        if self.authority.workspace != policy.workspace_id or self.provider.scope != plan.scope:
            raise PolicyError("publication tenant configuration mismatch")
        workspace, identifier = policy.workspace_id, str(spec.specification_id)
        with self.store.database.begin() as conn:
            recorded = self.store.get(
                workspace, "specification", identifier, spec.revision, connection=conn
            )
            stored_plan = self.store.get(
                workspace, "publication_plan", identifier, spec.revision, connection=conn
            )
            if (
                recorded["content_digest"] != spec.content_digest
                or plan.specification_digest != spec.content_digest
                or stored_plan != plan.model_dump(mode="json")
            ):
                raise PolicyError("unrecorded publication plan")
        receipts: list[OperationEvidence] = []
        for operation in plan.operations:
            with self.store.database.begin() as conn:
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
                if row is None:
                    break  # No intent exists; only governed publication may create one.
                if row["request_digest"] != operation.request_digest:
                    raise Conflict("native operation identity reused with different content")
                if row["status"] == "SUCCEEDED":
                    receipts.append(
                        OperationEvidence.model_validate_json(
                            json.dumps({name: row[name] for name in OperationEvidence.model_fields})
                        )
                    )
                    continue
                dispatched = self._dispatched(conn, workspace, operation.operation_key)
            # An undispatched intent has nothing to observe and is left for governed publication.
            provider_id = self.provider.reconcile(operation) if dispatched else None
            receipt = self._observe(workspace, identifier, operation, provider_id)
            receipts.append(receipt)
            if receipt.status == "UNKNOWN":
                break
        return tuple(receipts)

    def _observe(
        self, workspace: str, identifier: str, operation: NativeOperation, provider_id: str | None
    ) -> OperationEvidence:
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
        return receipt

    def _dispatched(self, conn: Connection, workspace: str, key: str) -> bool:
        try:
            self.store.get(workspace, "native_dispatch_authority", key, connection=conn)
            return True
        except Missing:
            return False

    def _observation_revision(self, key: str, conn: Connection) -> int:
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
