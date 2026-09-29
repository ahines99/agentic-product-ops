"""Durable identity grants and monotonic revocation, separate from model-visible artifacts."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator
from sqlalchemy import Connection, insert

from agentic_product_ops.adapters.identity.contracts import Principal
from agentic_product_ops.adapters.persistence.store import Conflict, Missing, Store, audits
from agentic_product_ops.domain.clarifications import ClarificationReceipt
from agentic_product_ops.domain.contracts import (
    ID,
    Contract,
    SpecificationApproval,
    Text,
    Timestamp,
    WorkSpecification,
    canonical_digest,
    unique,
)
from agentic_product_ops.policies.validation import PolicyError


class ActorGrant(Contract):
    schema_version: Literal["1"] = "1"
    workspace_id: ID
    actor_id: ID
    issuer: Text
    subject: Annotated[str, Field(min_length=1, max_length=256)]
    revision: Annotated[int, Field(ge=1)]
    roles: tuple[ID, ...]
    team_ids: tuple[ID, ...]
    repository_ids: tuple[ID, ...]
    allow_any_repository: bool = False
    issued_at: Timestamp
    expires_at: Timestamp
    enabled: bool

    @model_validator(mode="after")
    def valid(self) -> Self:
        if not self.issuer.startswith("https://") or self.expires_at <= self.issued_at:
            raise ValueError("invalid issuer or grant interval")
        for values in (self.roles, self.team_ids, self.repository_ids):
            unique(values, "grant scope")
        if not set(self.roles) <= {"product_approver", "security_approver", "intake_reader"}:
            raise ValueError("unsupported authority role")
        return self


class Authority:
    def __init__(
        self,
        store: Store,
        *,
        workspace: str,
        issuer: str,
        administrators: tuple[str, ...],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not administrators or not issuer.startswith("https://"):
            raise ValueError("explicit authority administration and issuer required")
        self.store, self.workspace, self.issuer = store, workspace, issuer
        self.administrators, self.clock = administrators, clock

    def _subject_key(self, subject: str) -> str:
        return canonical_digest({"issuer": self.issuer, "subject": subject})

    def _admin(self, actor: str) -> None:
        if actor not in self.administrators:
            raise PolicyError("identity administrator required")

    def register(self, grant: ActorGrant, *, administrator: str) -> None:
        """Operator control-plane method; not exposed to source text, roles, or HTTP users."""
        self._admin(administrator)
        ActorGrant.model_validate_json(grant.model_dump_json())
        if grant.workspace_id != self.workspace or grant.issuer != self.issuer:
            raise PolicyError("grant outside configured identity scope")
        with self.store.database.begin() as conn:
            self.store.lock_specification(conn, self.workspace, "authority-dispatch")
            self.store.lock_specification(conn, self.workspace, "identity:" + grant.actor_id)
            try:
                previous = self.store.get(
                    self.workspace, "actor_grant", grant.actor_id, connection=conn
                )
            except Missing:
                previous = None
            if grant.revision != (previous["revision"] + 1 if previous else 1):
                raise Conflict("grant revision must be sequential")
            if previous and (previous["issuer"], previous["subject"]) != (
                grant.issuer,
                grant.subject,
            ):
                raise PolicyError("actor subject binding is immutable")
            binding = self._subject_key(grant.subject)
            self.store.put(
                conn, self.workspace, "identity_subject", binding, 1, {"actor_id": grant.actor_id}
            )
            self.store.put(
                conn, self.workspace, "actor_grant", grant.actor_id, grant.revision, grant
            )
            self._audit(
                conn, administrator, "identity_grant", grant.actor_id, grant.model_dump(mode="json")
            )

    def revoke(
        self,
        kind: Literal["actor", "subject", "token", "approval"],
        identity: str,
        *,
        administrator: str,
    ) -> None:
        self._admin(administrator)
        if kind not in {"actor", "subject", "token", "approval"} or not identity:
            raise ValueError("invalid revocation")
        key = canonical_digest({"kind": kind, "identity": identity})
        with self.store.database.begin() as conn:
            # Shared authority lock establishes an ordering with grant checks and dispatch.
            self.store.lock_specification(conn, self.workspace, "authority-dispatch")
            try:
                self.store.get(self.workspace, "revocation", key, connection=conn)
                return
            except Missing:
                pass
            receipt = {"kind": kind, "identity_digest": key, "at": self.clock().isoformat()}
            self.store.put(conn, self.workspace, "revocation", key, 1, receipt)
            self._audit(conn, administrator, "identity_revocation", key, receipt)

    def _audit(
        self, conn: Connection, actor: str, action: str, subject: str, value: dict[str, Any]
    ) -> None:
        digest = canonical_digest(value)
        conn.execute(
            insert(audits).values(
                event_id=canonical_digest({"action": action, "digest": digest}),
                workspace=self.workspace,
                actor=actor,
                action=action,
                subject=subject,
                digest=digest,
                occurred_at=self.clock().isoformat(),
            )
        )

    def is_revoked(self, kind: str, identity: str, connection: Connection | None = None) -> bool:
        key = canonical_digest({"kind": kind, "identity": identity})
        try:
            self.store.get(self.workspace, "revocation", key, connection=connection)
            return True
        except Missing:
            return False

    def token_revoked(self, subject: str, token_id: str) -> bool:
        return self.is_revoked("subject", subject) or self.is_revoked("token", token_id)

    def grant(self, actor: str, connection: Connection | None = None) -> ActorGrant:
        value = self.store.get(self.workspace, "actor_grant", actor, connection=connection)
        grant = ActorGrant.model_validate_json(json.dumps(value))
        if (
            grant.workspace_id != self.workspace
            or grant.issuer != self.issuer
            or not grant.enabled
            or not grant.roles
            or not grant.issued_at <= self.clock() < grant.expires_at
            or self.is_revoked("actor", actor, connection)
            or self.is_revoked("subject", grant.subject, connection)
        ):
            raise PolicyError("grant inactive or revoked")
        return grant

    def resolve_subject(self, subject: str) -> Principal | None:
        try:
            binding = self.store.get(self.workspace, "identity_subject", self._subject_key(subject))
            grant = self.grant(binding["actor_id"])
            return Principal(
                actor_id=grant.actor_id,
                workspace_id=self.workspace,
                roles=grant.roles,
                grant_digest=canonical_digest(grant.model_dump(mode="json")),
            )
        except (Missing, ValueError):
            return None

    def check(self, principal: Principal, connection: Connection | None = None) -> ActorGrant:
        grant = self.grant(principal.actor_id, connection)
        if (
            principal.workspace_id != self.workspace
            or principal.roles != grant.roles
            or principal.grant_digest != canonical_digest(grant.model_dump(mode="json"))
        ):
            raise PolicyError("stale identity grant")
        return grant

    def bind_approval(
        self,
        conn: Connection,
        principal: Principal,
        approval: SpecificationApproval,
        specification: WorkSpecification,
    ) -> None:
        self.store.lock_specification(conn, self.workspace, "authority-dispatch")
        grant = self.check(principal, conn)
        self._scope(grant, specification)
        self.validate_clarifications(conn, specification)
        self.store.put(
            conn,
            self.workspace,
            "approval_authority",
            str(approval.approval_id),
            1,
            {
                "grant_digest": principal.grant_digest,
                "actor_id": principal.actor_id,
                "approval_digest": canonical_digest(approval.model_dump(mode="json")),
            },
        )

    def _scope(self, grant: ActorGrant, specification: WorkSpecification) -> None:
        if "product_approver" not in grant.roles:
            raise PolicyError("approver grant required")
        if specification.risk.tier >= 2 and "security_approver" not in grant.roles:
            raise PolicyError("security grant required for tier 2 or 3")
        if not {w.proposed_team_id for w in specification.work_items} <= set(grant.team_ids):
            raise PolicyError("team outside grant")
        repositories = {w.repository_id for w in specification.work_items if w.repository_id}
        if specification.repository_context:
            repositories.add(specification.repository_context.repository_id)
        if not grant.allow_any_repository and not repositories <= set(grant.repository_ids):
            raise PolicyError("repository outside grant")

    def validate_dispatch(
        self,
        conn: Connection,
        approval: SpecificationApproval,
        specification: WorkSpecification,
    ) -> None:
        self.store.lock_specification(conn, self.workspace, "authority-dispatch")
        grant = self.grant(approval.actor_id, conn)
        self._scope(grant, specification)
        self.validate_clarifications(conn, specification)
        receipt = self.store.get(
            self.workspace, "approval_authority", str(approval.approval_id), connection=conn
        )
        if (
            receipt["actor_id"] != grant.actor_id
            or receipt["grant_digest"] != canonical_digest(grant.model_dump(mode="json"))
            or receipt["approval_digest"] != canonical_digest(approval.model_dump(mode="json"))
            or self.is_revoked("approval", str(approval.approval_id), conn)
        ):
            raise PolicyError("approval authority stale or revoked")

    def bind_clarification(
        self,
        conn: Connection,
        principal: Principal,
        receipt: ClarificationReceipt,
    ) -> None:
        grant = self.check(principal, conn)
        if "product_approver" not in grant.roles or receipt.actor_id != grant.actor_id:
            raise PolicyError("clarification actor denied")
        self.store.put(
            conn,
            self.workspace,
            "clarification_authority",
            receipt.id,
            1,
            {
                "actor_id": grant.actor_id,
                "grant_digest": principal.grant_digest,
                "receipt_digest": canonical_digest(receipt.model_dump(mode="json")),
            },
        )

    def validate_clarifications(self, conn: Connection, specification: WorkSpecification) -> None:
        for identity in specification.provenance.clarification_refs:
            receipt = self.store.get(self.workspace, "clarification", identity, connection=conn)
            authority = self.store.get(
                self.workspace, "clarification_authority", identity, connection=conn
            )
            grant = self.grant(receipt["actor_id"], conn)
            if (
                "product_approver" not in grant.roles
                or authority["actor_id"] != grant.actor_id
                or authority["grant_digest"] != canonical_digest(grant.model_dump(mode="json"))
                or authority["receipt_digest"] != canonical_digest(receipt)
            ):
                raise PolicyError("clarification authority stale or revoked")
