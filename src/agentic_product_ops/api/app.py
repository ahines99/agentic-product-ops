"""Factory-configured ingress with no implicit credential loading or live mutations."""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Protocol
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import Connection, insert, text, update

from agentic_product_ops.adapters.identity.contracts import Principal as Principal
from agentic_product_ops.adapters.linear.offline import build_plan
from agentic_product_ops.adapters.persistence.store import (
    Conflict,
    Missing,
    Store,
    audits,
    controls,
    outbox,
)
from agentic_product_ops.domain.contracts import (
    ID,
    ApprovalScope,
    Contract,
    Digest,
    IntakeRequest,
    SpecificationApproval,
    Text,
    WorkSpecification,
    seal_specification,
    source_digest,
)
from agentic_product_ops.policies.validation import (
    PolicyError,
    ServerPolicy,
    blocking_findings,
    validate_approval,
)
from agentic_product_ops.services.drafting import draft
from agentic_product_ops.services.durable_analysis import load_analysis, recorded_review


class Authenticator(Protocol):
    def authenticate(self, bearer: str) -> Principal | None: ...


class DenyAll:
    def authenticate(self, bearer: str) -> Principal | None:
        return None


class TestAuthenticator:
    """Explicit local test identity mapping, not a production identity provider."""

    __test__ = False

    def __init__(self, identities: dict[str, Principal], *, testing: bool):
        if not testing:
            raise ValueError("test authenticator unavailable in production")
        self.identities = {
            hashlib.sha256(token.encode()).hexdigest(): actor for token, actor in identities.items()
        }

    def authenticate(self, bearer: str) -> Principal | None:
        candidate = hashlib.sha256(bearer.encode()).hexdigest()
        for digest, principal in self.identities.items():
            if hmac.compare_digest(digest, candidate):
                return principal
        return None


class IntakeCommand(Contract):
    source: Text


class RevisionCommand(Contract):
    revision: Annotated[int, Field(ge=1)]
    content_digest: Digest


class DecisionCommand(RevisionCommand):
    expires_in_seconds: Annotated[int, Field(gt=0, le=3600)] = 1800


class ClarificationCommand(RevisionCommand):
    question_id: ID
    answer: Text


def create_app(
    store: Store | None = None,
    policy: ServerPolicy | None = None,
    authenticator: Authenticator | None = None,
) -> FastAPI:
    app = FastAPI(title="Agentic Product Ops", version="0.3.0", docs_url=None, redoc_url=None)
    active_policy = policy or ServerPolicy()
    auth = authenticator or DenyAll()

    @app.exception_handler(RequestValidationError)
    async def malformed(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "invalid command schema"})

    @app.exception_handler(Conflict)
    async def conflict(request: Request, exc: Conflict) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "command or revision conflict"})

    @app.exception_handler(Missing)
    async def missing(request: Request, exc: Missing) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "artifact not found"})

    @app.exception_handler(PolicyError)
    async def denied(request: Request, exc: PolicyError) -> JSONResponse:
        return JSONResponse(
            status_code=403, content={"detail": "deterministic policy denied command"}
        )

    @app.middleware("http")
    async def bound_request(request: Request, call_next: Any) -> Any:
        # Enforce actual streamed bytes, including requests without Content-Length.
        if request.method in {"POST", "PUT", "PATCH"}:
            chunks, length = [], 0
            async for chunk in request.stream():
                length += len(chunk)
                if length > 200_000:
                    return JSONResponse(status_code=413, content={"detail": "request too large"})
                chunks.append(chunk)
            request._body = b"".join(chunks)
        return await call_next(request)

    def identity(authorization: Annotated[str | None, Header()] = None) -> Principal:
        if authorization is None or not authorization.startswith("Bearer "):
            raise HTTPException(401, "authentication required")
        actor = auth.authenticate(authorization[7:])
        if actor is None:
            raise HTTPException(401, "authentication required")
        Principal.model_validate_json(actor.model_dump_json())
        if actor.workspace_id != active_policy.workspace_id:
            raise HTTPException(403, "workspace denied")
        return actor

    def database() -> Store:
        if store is None:
            raise HTTPException(503, "storage not configured")
        return store

    def key(idempotency_key: Annotated[str, Header()]) -> str:
        if not 1 <= len(idempotency_key) <= 128 or not idempotency_key.isascii():
            raise HTTPException(422, "invalid idempotency key")
        return idempotency_key

    def spec_for(
        db: Store,
        actor: Principal,
        identifier: UUID,
        body: RevisionCommand | None = None,
        connection: Connection | None = None,
    ) -> WorkSpecification:
        value = db.get(actor.workspace_id, "specification", str(identifier), connection=connection)
        spec = WorkSpecification.model_validate_json(json.dumps(value))
        if body and (spec.revision, spec.content_digest) != (body.revision, body.content_digest):
            raise Conflict("stale specification")
        return spec

    def audit(
        connection: Connection, actor: Principal, action: str, subject: str, digest: str
    ) -> None:
        connection.execute(
            insert(audits).values(
                event_id=str(uuid4()),
                workspace=actor.workspace_id,
                actor=actor.actor_id,
                action=action,
                subject=subject,
                digest=digest,
                occurred_at=datetime.now(UTC).isoformat(),
            )
        )

    def require_approver(actor: Principal) -> None:
        if "product_approver" not in actor.roles or actor.actor_id not in active_policy.approvers:
            raise HTTPException(403, "approver role required")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": "offline_foundation", "publication": "disabled"}

    @app.get("/ready")
    def ready(db: Annotated[Store, Depends(database)]) -> JSONResponse:
        try:
            with db.database.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(status_code=503, content={"ready": False})
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "storage": "reachable",
                "reason": "production identity/provider integration disabled",
            },
        )

    @app.post("/v1/intakes", status_code=201)
    def intake(
        body: IntakeCommand,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
        command_key: Annotated[str, Depends(key)],
    ) -> dict[str, Any]:
        def execute(conn: Connection) -> dict[str, Any]:
            identifier, now = uuid4(), datetime.now(UTC)
            source = IntakeRequest(
                intake_id=identifier,
                source_text=body.source,
                source_digest=source_digest(body.source),
                received_at=now,
                source_kind="prompt",
            )
            template, state = draft(body.source)
            payload = template.model_dump(mode="json")
            payload["specification_id"] = str(identifier)
            spec = seal_specification(payload)
            db.put(conn, actor.workspace_id, "intake", str(identifier), 1, source)
            db.put(conn, actor.workspace_id, "specification", str(identifier), 1, spec)
            conn.execute(
                insert(outbox).values(
                    workspace=actor.workspace_id,
                    workflow_id=f"product-ops-{identifier}",
                    payload=json.dumps(
                        {
                            "workspace": actor.workspace_id,
                            "specification_id": str(identifier),
                            "content_digest": spec.content_digest,
                            "proposed_state": state.value,
                        }
                    ),
                    dispatched=0,
                )
            )
            audit(conn, actor, "intake_received", str(identifier), spec.content_digest)
            return {
                "intake_id": str(identifier),
                "specification_id": str(identifier),
                "workflow": "queued",
                "mode": spec.provenance.mode,
                "proposal_state": state.value,
            }

        return db.command(
            actor.workspace_id,
            actor.actor_id,
            command_key,
            {"action": "intake", "body": body.model_dump(mode="json")},
            execute,
        )

    @app.get("/v1/intakes/{identifier}")
    def get_intake(
        identifier: UUID,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
    ) -> dict[str, Any]:
        return db.get(actor.workspace_id, "intake", str(identifier))

    @app.get("/v1/specifications/{identifier}")
    def get_spec(
        identifier: UUID,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
    ) -> dict[str, Any]:
        return spec_for(db, actor, identifier).model_dump(mode="json")

    @app.get("/v1/specifications/{identifier}/review")
    def get_review(
        identifier: UUID,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
    ) -> dict[str, Any]:
        spec = spec_for(db, actor, identifier)
        try:
            return {
                "mode": "recorded_roles",
                "result": load_analysis(db, actor.workspace_id, spec, active_policy).model_dump(
                    mode="json"
                ),
            }
        except Missing:
            pass
        return {
            "mode": "deterministic_checks_only",
            "content_digest": spec.content_digest,
            "blocking_findings": blocking_findings(spec),
        }

    def decision(
        identifier: UUID,
        body: DecisionCommand,
        actor: Principal,
        db: Store,
        command_key: str,
        approve: bool,
    ) -> dict[str, Any]:
        require_approver(actor)

        def execute(conn: Connection) -> dict[str, Any]:
            if db.lock_specification(conn, actor.workspace_id, str(identifier)):
                raise PolicyError("specification cancelled")
            spec = spec_for(db, actor, identifier, body, conn)
            try:
                recorded_review(db, actor.workspace_id, spec, active_policy)
            except Missing as exc:
                raise PolicyError("analysis and review have not completed") from exc
            plan = build_plan(spec, active_policy)
            now = datetime.now(UTC)
            approval = SpecificationApproval(
                approval_id=uuid4(),
                specification_id=identifier,
                revision=spec.revision,
                content_digest=spec.content_digest,
                actor_id=actor.actor_id,
                decision="approve" if approve else "reject",
                policy_version=active_policy.version,
                issued_at=now,
                expires_at=now + timedelta(seconds=body.expires_in_seconds),
                scope=ApprovalScope(
                    workspace_id=actor.workspace_id,
                    team_ids=tuple(sorted({w.proposed_team_id for w in spec.work_items})),
                    repository_ids=tuple(
                        sorted({w.repository_id for w in spec.work_items if w.repository_id})
                    ),
                    plan_digest=plan.content_digest,
                    operation_keys=tuple(o.operation_key for o in plan.operations),
                    allowed_mutation_count=len(plan.operations),
                ),
            )
            if approve:
                validate_approval(
                    spec,
                    approval,
                    active_policy,
                    authenticated_actor=actor.actor_id,
                    plan_digest=plan.content_digest,
                    operation_keys=tuple(o.operation_key for o in plan.operations),
                    now=now,
                )
            db.put(conn, actor.workspace_id, "approval", str(approval.approval_id), 1, approval)
            db.put(
                conn,
                actor.workspace_id,
                "decision",
                str(identifier),
                spec.revision,
                {"approval_id": str(approval.approval_id), "decision": approval.decision},
            )
            conn.execute(
                insert(outbox).values(
                    workspace=actor.workspace_id,
                    workflow_id=f"decision-{approval.approval_id}",
                    dispatched=0,
                    payload=json.dumps(
                        {
                            "action": "decision",
                            "specification_id": str(identifier),
                            "approval_id": str(approval.approval_id),
                            "target_workflow": f"product-ops-{identifier}"
                            + (f"-r{spec.revision}" if spec.revision > 1 else ""),
                        }
                    ),
                )
            )
            audit(
                conn,
                actor,
                "approval_recorded" if approve else "rejection_recorded",
                str(identifier),
                approval.content_digest,
            )
            return {"approval": approval.model_dump(mode="json"), "publication": "disabled"}

        return db.command(
            actor.workspace_id,
            actor.actor_id,
            command_key,
            {
                "id": str(identifier),
                "action": "approve" if approve else "reject",
                "body": body.model_dump(mode="json"),
            },
            execute,
        )

    @app.post("/v1/specifications/{identifier}/approve")
    def approve(
        identifier: UUID,
        body: DecisionCommand,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
        command_key: Annotated[str, Depends(key)],
    ) -> dict[str, Any]:
        return decision(identifier, body, actor, db, command_key, True)

    @app.post("/v1/specifications/{identifier}/reject")
    def reject(
        identifier: UUID,
        body: DecisionCommand,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
        command_key: Annotated[str, Depends(key)],
    ) -> dict[str, Any]:
        return decision(identifier, body, actor, db, command_key, False)

    @app.post("/v1/specifications/{identifier}/clarifications")
    def clarify(
        identifier: UUID,
        body: ClarificationCommand,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
        command_key: Annotated[str, Depends(key)],
    ) -> dict[str, Any]:
        require_approver(actor)

        def execute(conn: Connection) -> dict[str, Any]:
            if db.lock_specification(conn, actor.workspace_id, str(identifier)):
                raise PolicyError("specification cancelled")
            spec = spec_for(db, actor, identifier, body, conn)
            if spec.revision >= 11:
                raise PolicyError("clarification revision budget exhausted")
            question = next(
                (q for q in spec.unresolved_questions if q.id == body.question_id), None
            )
            if question is None or question.resolution is not None:
                raise Conflict("question missing or already answered")
            receipt_id, timestamp = f"C-{uuid4()}", datetime.now(UTC).isoformat()
            receipt = {
                "id": receipt_id,
                "specification_id": str(identifier),
                "base_revision": spec.revision,
                "base_digest": spec.content_digest,
                "question_id": body.question_id,
                "answer": body.answer,
                "actor_id": actor.actor_id,
                "resolved_at": timestamp,
            }
            payload = spec.model_dump(mode="json")
            payload["revision"] += 1
            for q in payload["unresolved_questions"]:
                if q["id"] == body.question_id:
                    q.update(
                        resolution=body.answer, resolved_by=actor.actor_id, resolved_at=timestamp
                    )
            payload["provenance"]["clarification_refs"].append(receipt_id)
            # A recorded answer requires fresh analysis/review. It never auto-approves a revision.
            payload["risk"]["tier"] = 3
            for work in payload["work_items"]:
                work["risk_tier"] = 3
            revised = seal_specification(payload)
            db.put(conn, actor.workspace_id, "clarification", receipt_id, 1, receipt)
            db.put(
                conn,
                actor.workspace_id,
                "specification",
                str(identifier),
                revised.revision,
                revised,
            )
            conn.execute(
                insert(outbox).values(
                    workspace=actor.workspace_id,
                    workflow_id=f"product-ops-{identifier}-r{revised.revision}",
                    dispatched=0,
                    payload=json.dumps(
                        {
                            "workspace": actor.workspace_id,
                            "specification_id": str(identifier),
                            "content_digest": revised.content_digest,
                            "proposed_state": "AWAITING_CLARIFICATION",
                        }
                    ),
                )
            )
            audit(conn, actor, "clarification_recorded", str(identifier), revised.content_digest)
            return {
                "revision": revised.revision,
                "content_digest": revised.content_digest,
                "requires_reanalysis": True,
                "receipt_id": receipt_id,
                "workflow": "queued",
            }

        return db.command(
            actor.workspace_id,
            actor.actor_id,
            command_key,
            {"id": str(identifier), "action": "clarify", "body": body.model_dump(mode="json")},
            execute,
        )

    @app.post("/v1/specifications/{identifier}/cancel")
    def cancel(
        identifier: UUID,
        body: RevisionCommand,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
        command_key: Annotated[str, Depends(key)],
    ) -> dict[str, Any]:
        require_approver(actor)

        def execute(conn: Connection) -> dict[str, Any]:
            db.lock_specification(conn, actor.workspace_id, str(identifier))
            spec = spec_for(db, actor, identifier, body, conn)
            conn.execute(
                update(controls)
                .where(
                    controls.c.workspace == actor.workspace_id,
                    controls.c.specification_id == str(identifier),
                )
                .values(cancelled=1)
            )
            receipt = {
                "specification_id": str(identifier),
                "revision": spec.revision,
                "content_digest": spec.content_digest,
                "actor_id": actor.actor_id,
            }
            db.put(conn, actor.workspace_id, "cancellation", str(identifier), 1, receipt)
            conn.execute(
                insert(outbox).values(
                    workspace=actor.workspace_id,
                    workflow_id=f"cancel-{identifier}",
                    dispatched=0,
                    payload=json.dumps(
                        {
                            "action": "cancel",
                            "specification_id": str(identifier),
                            "target_workflow": f"product-ops-{identifier}"
                            + (f"-r{spec.revision}" if spec.revision > 1 else ""),
                        }
                    ),
                )
            )
            audit(conn, actor, "cancellation_recorded", str(identifier), spec.content_digest)
            return {"cancelled": True, "publication": "disabled"}

        return db.command(
            actor.workspace_id,
            actor.actor_id,
            command_key,
            {"id": str(identifier), "action": "cancel", "body": body.model_dump(mode="json")},
            execute,
        )

    @app.post("/v1/specifications/{identifier}/publish")
    def publish(
        identifier: UUID,
        actor: Annotated[Principal, Depends(identity)],
        command_key: Annotated[str, Depends(key)],
    ) -> None:
        require_approver(actor)
        raise HTTPException(503, "live publication is disabled; no provider credentials configured")

    @app.get("/v1/publications/{identifier}")
    def publication(
        identifier: UUID,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
    ) -> dict[str, Any]:
        return db.get(actor.workspace_id, "publication", str(identifier))

    @app.get("/v1/handoffs/{identifier}")
    def handoff(
        identifier: UUID,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
    ) -> dict[str, Any]:
        return db.get(actor.workspace_id, "handoff", str(identifier))

    return app
