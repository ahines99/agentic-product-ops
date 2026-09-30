"""Durable, bounded Linear notification inbox; payloads never confer work authority."""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select

from agentic_product_ops.adapters.persistence.store import Missing, Store, artifacts
from agentic_product_ops.domain.contracts import Contract, Timestamp, canonical_digest
from agentic_product_ops.policies.validation import PolicyError


class LinearEvent(Contract):
    issue_id: UUID
    organization_id: UUID
    team_id: UUID
    action: Literal["create", "update", "remove", "sync"]
    created_at: Timestamp
    updated_at: Timestamp

    def key(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


def verify_event(
    raw: bytes,
    signature: str,
    secret: str,
    organization: UUID,
    teams: set[UUID],
    now: datetime,
) -> LinearEvent:
    if (
        len(raw) > 256000
        or len(signature) != 64
        or not secret
        or any(character not in "0123456789abcdef" for character in signature)
    ):
        raise PolicyError("invalid webhook envelope")
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise PolicyError("invalid webhook signature")
    try:
        body = json.loads(raw)
        timestamp = body["webhookTimestamp"]
        if type(timestamp) is not int or abs(now.timestamp() - timestamp / 1000) > 60:
            raise ValueError("stale webhook")
        if body["type"] != "Issue":
            raise ValueError("unsupported event")
        data = body["data"]
        event = LinearEvent.model_validate_json(
            json.dumps(
                {
                    "issue_id": data["id"],
                    "organization_id": body["organizationId"],
                    "team_id": data["teamId"],
                    "action": body["action"],
                    "created_at": data["createdAt"],
                    "updated_at": data["updatedAt"],
                }
            )
        )
        if event.organization_id != organization or event.team_id not in teams:
            raise ValueError("scope mismatch")
        if (
            event.created_at > event.updated_at
            or event.updated_at.timestamp() > now.timestamp() + 60
        ):
            raise ValueError("invalid source times")
        return event
    except (KeyError, TypeError, ValueError):
        raise PolicyError("invalid or out-of-scope webhook") from None


class LinearInbox:
    def __init__(self, store: Store, workspace: str):
        self.store, self.workspace = store, workspace

    def receive(self, event: LinearEvent) -> dict[str, Any]:
        def save(conn: Any) -> dict[str, Any]:
            self.store.put(conn, self.workspace, "linear_event", event.key(), 1, event)
            return {"accepted": True}

        return self.store.command(
            self.workspace, "linear-monitor", event.key(), event.model_dump(mode="json"), save
        )

    def pending(self, limit: int = 20) -> list[LinearEvent]:
        done = artifacts.alias("done")
        query = (
            select(artifacts.c.identity)
            .outerjoin(
                done,
                (
                    (done.c.workspace == artifacts.c.workspace)
                    & (done.c.kind == "linear_event_result")
                    & (done.c.identity == artifacts.c.identity)
                ),
            )
            .where(
                artifacts.c.workspace == self.workspace,
                artifacts.c.kind == "linear_event",
                done.c.identity.is_(None),
            )
            .order_by(artifacts.c.created_at, artifacts.c.identity)
            .limit(limit)
        )
        with self.store.database.connect() as conn:
            identifiers: list[str] = list(conn.execute(query).scalars())
        return [
            LinearEvent.model_validate_json(
                json.dumps(self.store.get(self.workspace, "linear_event", identity))
            )
            for identity in identifiers
        ]

    def latest(self, kind: str) -> dict[str, Any]:
        if kind not in {"linear_event", "linear_event_result"}:
            raise ValueError("monitor metadata kind required")
        with self.store.database.connect() as conn:
            row = conn.execute(
                select(artifacts.c.identity, artifacts.c.created_at)
                .where(
                    artifacts.c.workspace == self.workspace,
                    artifacts.c.kind == kind,
                )
                .order_by(artifacts.c.created_at.desc())
                .limit(1)
            ).first()
        if row is None:
            return {}
        result = {"at": row.created_at}
        if kind == "linear_event_result":
            result["status"] = self.store.get(self.workspace, kind, row.identity)["status"]
        return result

    def finish(self, event: LinearEvent, status: str, detail: dict[str, Any] | None = None) -> None:
        self.store.command(
            self.workspace,
            "linear-monitor-result",
            event.key(),
            {"event": event.key()},
            lambda conn: self._result(conn, event, status, detail),
        )

    def _result(
        self, conn: Any, event: LinearEvent, status: str, detail: dict[str, Any] | None
    ) -> dict[str, Any]:
        value = {"status": status, "detail": detail or {}, "at": datetime.now(UTC).isoformat()}
        self.store.put(conn, self.workspace, "linear_event_result", event.key(), 1, value)
        return {"recorded": True}

    def cursor(self, initial: datetime) -> datetime:
        try:
            record = self.store.get(self.workspace, "linear_poll_cursor", "monitor")
            return datetime.fromisoformat(record["until"])
        except Missing:
            return initial

    def advance(self, until: datetime) -> None:
        with self.store.database.begin() as conn:
            self.store.lock_specification(conn, self.workspace, "linear-poll-cursor")
            try:
                previous = self.store.get(
                    self.workspace, "linear_poll_cursor", "monitor", connection=conn
                )
                if datetime.fromisoformat(previous["until"]) >= until:
                    return
                revision = previous["revision"] + 1
            except Missing:
                revision = 1
            self.store.put(
                conn,
                self.workspace,
                "linear_poll_cursor",
                "monitor",
                revision,
                {"revision": revision, "until": until.isoformat()},
            )
