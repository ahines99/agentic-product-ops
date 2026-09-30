"""Transactional immutable artifacts, command receipts, audits, outbox and write intents."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Column,
    Connection,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from agentic_product_ops.adapters.persistence.encryption import StorageEncryption
from agentic_product_ops.domain.contracts import Contract, canonical_digest

metadata = MetaData()
artifacts = Table(
    "artifacts",
    metadata,
    Column("workspace", String(128), primary_key=True),
    Column("kind", String(64), primary_key=True),
    Column("identity", String(128), primary_key=True),
    Column("revision", Integer, primary_key=True),
    Column("digest", String(64), nullable=False),
    Column("payload", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
)
commands = Table(
    "commands",
    metadata,
    Column("workspace", String(128), primary_key=True),
    Column("actor", String(128), primary_key=True),
    Column("key", String(128), primary_key=True),
    Column("digest", String(64), nullable=False),
    Column("result", Text, nullable=False),
)
audits = Table(
    "audit_events",
    metadata,
    Column("event_id", String(128), primary_key=True),
    Column("workspace", String(128), nullable=False),
    Column("actor", String(128), nullable=False),
    Column("action", String(128), nullable=False),
    Column("subject", String(128), nullable=False),
    Column("digest", String(64), nullable=False),
    Column("occurred_at", String(40), nullable=False),
)
outbox = Table(
    "workflow_outbox",
    metadata,
    Column("workspace", String(128), primary_key=True),
    Column("workflow_id", String(128), primary_key=True),
    Column("payload", Text, nullable=False),
    Column("dispatched", Integer, nullable=False, default=0),
)
operations = Table(
    "publication_operations",
    metadata,
    Column("workspace", String(128), primary_key=True),
    Column("operation_key", String(64), primary_key=True),
    Column("request_digest", String(64), nullable=False),
    Column("request", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("attempt", Integer, nullable=False),
    Column("provider_id", String(128)),
    Column("provider_request_id", String(128)),
    Column("observed_at", String(40), nullable=False),
)
controls = Table(
    "publication_controls",
    metadata,
    Column("workspace", String(128), primary_key=True),
    Column("specification_id", String(128), primary_key=True),
    Column("cancelled", Integer, nullable=False, default=0),
)


class Conflict(ValueError):
    """Immutable revision, command identity, or operation identity conflict."""


class Missing(KeyError):
    """Tenant-scoped artifact not found."""


def engine(url: str, *, testing: bool = False) -> Engine:
    if not url.startswith("postgresql+psycopg://") and not (testing and url.startswith("sqlite")):
        raise ValueError("production storage requires PostgreSQL; SQLite is a test double only")
    return create_engine(url, pool_pre_ping=True, hide_parameters=True)


class Store:
    def __init__(
        self,
        database: Engine,
        *,
        encryption: StorageEncryption | None = None,
        retention_seconds: Mapping[str, int] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.database = database
        self.encryption, self.retention, self.clock = (
            encryption,
            dict(retention_seconds or {}),
            clock,
        )
        if any(
            kind not in {"role_request", "role_response"}
            or type(seconds) is not int
            or seconds <= 0
            for kind, seconds in self.retention.items()
        ):
            raise ValueError("only raw role request/response retention may expire")

    def encode_record(self, identity: tuple[str | int, ...], value: dict[str, Any]) -> str:
        return self.encryption.encode(identity, value) if self.encryption else json.dumps(value)

    def decode_record(self, identity: tuple[str | int, ...], raw: str) -> dict[str, Any]:
        if self.encryption:
            return self.encryption.decode(identity, raw)
        value: dict[str, Any] = json.loads(raw)
        if "storage_version" in value:
            raise Conflict("encrypted store requires its configured keyring")
        return value

    def lock_specification(self, conn: Connection, workspace: str, identifier: str) -> bool:
        factory = pg_insert if conn.dialect.name == "postgresql" else sqlite_insert
        conn.execute(
            factory(controls)
            .values(workspace=workspace, specification_id=identifier, cancelled=0)
            .on_conflict_do_nothing()
        )
        return bool(
            conn.execute(
                select(controls.c.cancelled)
                .where(
                    controls.c.workspace == workspace,
                    controls.c.specification_id == identifier,
                )
                .with_for_update()
            ).scalar_one()
        )

    def cancelled(self, workspace: str, identifier: str) -> bool:
        with self.database.connect() as conn:
            return bool(
                conn.execute(
                    select(controls.c.cancelled).where(
                        controls.c.workspace == workspace,
                        controls.c.specification_id == identifier,
                    )
                ).scalar_one_or_none()
            )

    def put(
        self,
        connection: Connection,
        workspace: str,
        kind: str,
        identity: str,
        revision: int,
        value: Contract | dict[str, Any],
    ) -> None:
        payload = value.model_dump(mode="json") if isinstance(value, Contract) else value
        digest = canonical_digest(payload)
        existing = connection.execute(
            select(artifacts.c.digest).where(
                artifacts.c.workspace == workspace,
                artifacts.c.kind == kind,
                artifacts.c.identity == identity,
                artifacts.c.revision == revision,
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing != digest:
                raise Conflict("immutable revision conflict")
            return
        connection.execute(
            insert(artifacts).values(
                workspace=workspace,
                kind=kind,
                identity=identity,
                revision=revision,
                digest=digest,
                payload=self.encode_record((workspace, kind, identity, revision), payload),
                created_at=self.clock().isoformat(),
            )
        )

    def get(
        self,
        workspace: str,
        kind: str,
        identity: str,
        revision: int | None = None,
        connection: Connection | None = None,
    ) -> dict[str, Any]:
        query = select(
            artifacts.c.payload, artifacts.c.digest, artifacts.c.revision, artifacts.c.created_at
        ).where(
            artifacts.c.workspace == workspace,
            artifacts.c.kind == kind,
            artifacts.c.identity == identity,
        )
        if revision is not None:
            query = query.where(artifacts.c.revision == revision)
        query = query.order_by(artifacts.c.revision.desc()).limit(1)
        if connection is None:
            with self.database.connect() as conn:
                raw = conn.execute(query).mappings().first()
        else:
            raw = connection.execute(query).mappings().first()
        if raw is None:
            raise Missing("artifact not found")
        if (
            kind in self.retention
            and (self.clock() - datetime.fromisoformat(raw["created_at"])).total_seconds()
            >= self.retention[kind]
        ):
            raise Missing("raw artifact access retention expired; audit metadata retained")
        value = self.decode_record((workspace, kind, identity, raw["revision"]), raw["payload"])
        if canonical_digest(value) != raw["digest"]:
            raise Conflict("stored artifact integrity mismatch")
        return value

    def command(
        self,
        workspace: str,
        actor: str,
        key: str,
        request: dict[str, Any],
        execute: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        digest = canonical_digest(request)
        query = select(commands).where(
            commands.c.workspace == workspace, commands.c.actor == actor, commands.c.key == key
        )
        try:
            with self.database.begin() as connection:
                row = connection.execute(query).mappings().first()
                if row is not None:
                    if row["digest"] != digest:
                        raise Conflict("idempotency key reused with different request")
                    result: dict[str, Any] = json.loads(row["result"])
                    return result
                # Transaction rolls back all side effects if a concurrent command wins the key.
                result = execute(connection)
                connection.execute(
                    insert(commands).values(
                        workspace=workspace,
                        actor=actor,
                        key=key,
                        digest=digest,
                        result=json.dumps(result),
                    )
                )
                return result
        except IntegrityError as error:
            with self.database.connect() as connection:
                row = connection.execute(query).mappings().first()
                if row is not None and row["digest"] == digest:
                    recovered: dict[str, Any] = json.loads(row["result"])
                    return recovered
            raise Conflict("concurrent command or revision conflict") from error

    def pending_workflows(self, workspace: str | None = None) -> list[dict[str, Any]]:
        query = select(outbox).where(outbox.c.dispatched == 0)
        if workspace is not None:
            query = query.where(outbox.c.workspace == workspace)
        with self.database.connect() as connection:
            return [dict(row) for row in connection.execute(query).mappings()]

    def mark_dispatched(self, workspace: str, workflow_id: str) -> None:
        with self.database.begin() as connection:
            connection.execute(
                update(outbox)
                .where(outbox.c.workspace == workspace, outbox.c.workflow_id == workflow_id)
                .values(dispatched=1)
            )
