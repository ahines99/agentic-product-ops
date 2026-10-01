"""Factory-configured ingress with no implicit credential loading or live mutations."""

import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Protocol
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import Connection, insert, text, update

from agentic_product_ops.adapters.identity.contracts import Principal as Principal
from agentic_product_ops.adapters.linear.graphql import UnknownOutcome
from agentic_product_ops.adapters.linear.intake import LinearSource, repository_name
from agentic_product_ops.adapters.linear.native_plan import LinearScope, build_native_plan
from agentic_product_ops.adapters.linear.offline import build_plan
from agentic_product_ops.adapters.persistence.store import (
    Conflict,
    Missing,
    Store,
    audits,
    controls,
    outbox,
)
from agentic_product_ops.adapters.repository.local import Snapshot, inspect_repository
from agentic_product_ops.adapters.repository.selection import RepositorySelection
from agentic_product_ops.api.local_console import BrowserSessions, mount_console
from agentic_product_ops.domain.clarifications import ClarificationReceipt
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
from agentic_product_ops.services.authority import Authority
from agentic_product_ops.services.clarifications import load_clarifications
from agentic_product_ops.services.decisions import record_decision
from agentic_product_ops.services.drafting import draft
from agentic_product_ops.services.durable_analysis import (
    analysis_mode,
    load_analysis,
    passing_review,
    recorded_review,
)
from agentic_product_ops.services.native_publication import publication_writes
from agentic_product_ops.services.plan_inputs import repository_label
from agentic_product_ops.services.publication_state import publication_state
from agentic_product_ops.services.risk_reassessment import RiskCommand
from agentic_product_ops.services.signed_handoff import HandoffGone
from agentic_product_ops.services.ticket_readiness import delivery_findings, ticket_findings


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
    repository_id: ID | None = None
    expected_snapshot_digest: Digest | None = None
    repository: RepositorySelection | None = None


class RevisionCommand(Contract):
    revision: Annotated[int, Field(ge=1)]
    content_digest: Digest


class LinearIntakeCommand(Contract):
    issue: Annotated[str, Field(min_length=1, max_length=2048)]
    repository: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    # The enrolled specification that this edited issue explicitly replaces.
    supersedes: (
        Annotated[str, Field(pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")] | None
    ) = None


class PromptIntakeCommand(Contract):
    source: Text
    repository: Annotated[str, Field(min_length=1, max_length=128)]


class DecisionCommand(RevisionCommand):
    expires_in_seconds: Annotated[int, Field(gt=0, le=3600)] = 1800
    plan_digest: Digest | None = None


class ClarificationCommand(RevisionCommand):
    question_id: ID
    answer: Text


def create_app(
    store: Store | None = None,
    policy: ServerPolicy | None = None,
    authenticator: Authenticator | None = None,
    authority: Authority | None = None,
    linear_scope: LinearScope | None = None,
    repository_roots: dict[str, Path] | None = None,
    repository_resolver: Callable[[RepositorySelection], Snapshot] | None = None,
    force_model_intake: bool = False,
    publication_handler: Callable[[str, Principal, str], dict[str, Any]] | None = None,
    reconciliation_handler: Callable[[str, Principal], dict[str, Any]] | None = None,
    state_handler: Callable[[str], dict[str, Any]] | None = None,
    handoff_reader: Callable[[str, str], dict[str, Any]] | None = None,
    readiness: Callable[[], dict[str, Any]] | None = None,
    risk_handler: Callable[[str, Principal, RiskCommand, str], dict[str, Any]] | None = None,
    linear_source_reader: Callable[[str], LinearSource] | None = None,
    repository_names: Callable[[str], RepositorySelection] | None = None,
    source_guard: Callable[[str], None] | None = None,
    intake_queue_enabled: bool = True,
    decision_queue_enabled: bool = True,
    console_port: int | None = None,
    console_publication_enabled: bool = False,
) -> FastAPI:
    app = FastAPI(title="Agentic Product Ops", version="0.6.0", docs_url=None, redoc_url=None)
    active_policy = policy or ServerPolicy()
    auth = authenticator or DenyAll()
    roots = dict(repository_roots or {})
    browser = (
        BrowserSessions(console_port, publication=console_publication_enabled)
        if console_port is not None
        else None
    )
    if browser:
        mount_console(app, browser)
    if not active_policy.allow_any_repository and not roots.keys() <= set(
        active_policy.repositories
    ):
        raise ValueError("configured repository roots exceed server policy")

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

    def identity(
        request: Request, authorization: Annotated[str | None, Header()] = None
    ) -> Principal:
        if authorization is None and browser:
            credential = browser.credential(request)
        elif authorization is not None and authorization.startswith("Bearer "):
            credential = authorization[7:]
        else:
            raise HTTPException(401, "authentication required")
        actor = auth.authenticate(credential)
        if actor is None:
            raise HTTPException(401, "authentication required")
        Principal.model_validate_json(actor.model_dump_json())
        if actor.workspace_id != active_policy.workspace_id:
            raise HTTPException(403, "workspace denied")
        if authority:
            authority.check(actor)
        return actor

    if browser:

        @app.post("/v1/local/launch", include_in_schema=False)
        def launch_browser(
            actor: Annotated[Principal, Depends(identity)],
            authorization: Annotated[str, Header()],
        ) -> dict[str, Any]:
            if browser is None:
                raise HTTPException(404, "local console disabled")
            return {"url": browser.launch(authorization[7:]), "expires_in_seconds": 60}

        @app.get("/v1/local/status", include_in_schema=False)
        def browser_status(actor: Annotated[Principal, Depends(identity)]) -> dict[str, Any]:
            return {
                "operator": actor.actor_id,
                "analysis_enabled": intake_queue_enabled,
                "publication_enabled": console_publication_enabled,
                "policy_version": active_policy.version,
            }

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

    def current_authority(conn: Connection, actor: Principal) -> None:
        if authority:
            db = database()
            db.lock_specification(conn, actor.workspace_id, "authority-dispatch")
            authority.check(actor, conn)

    def require_approver(actor: Principal) -> None:
        if "product_approver" not in actor.roles or actor.actor_id not in active_policy.approvers:
            raise HTTPException(403, "approver role required")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "mode": "configured_pilot" if force_model_intake else "offline_foundation",
            "publication": "guarded" if publication_handler else "disabled",
        }

    @app.get("/ready")
    def ready(db: Annotated[Store, Depends(database)]) -> JSONResponse:
        try:
            with db.database.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(status_code=503, content={"ready": False})
        if readiness is not None:
            report = readiness()
            return JSONResponse(
                status_code=200 if report.get("ready") is True else 503, content=report
            )
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
        if not {"product_approver", "intake_reader"} & set(actor.roles):
            raise PolicyError("intake requires an approver or intake reader role")
        return submit_intake(body, actor, db, command_key)

    def submit_intake(
        body: IntakeCommand,
        actor: Principal,
        db: Store,
        command_key: str,
        linear_source: LinearSource | None = None,
        supersedes: str | None = None,
    ) -> dict[str, Any]:
        def execute(conn: Connection) -> dict[str, Any]:
            current_authority(conn, actor)
            if supersedes is not None:
                supersede_source(conn, actor, db, supersedes, linear_source)
            if linear_source is not None:
                if "intake_reader" not in actor.roles or linear_scope is None:
                    raise PolicyError("intake reader role and Linear scope required")
                grant = authority.check(actor, conn) if authority else None
                if grant is None:
                    raise PolicyError("Linear intake requires durable authority")
                allowed = {
                    str(t.provider_id) for t in linear_scope.teams if t.local_id in grant.team_ids
                }
                if str(linear_source.team_id) not in allowed:
                    raise PolicyError("source team exceeds actor scope")
            if body.repository is not None and body.repository_id is not None:
                raise PolicyError("one repository selection required")
            if (
                body.expected_snapshot_digest is not None
                and body.repository_id is None
                and body.repository is None
            ):
                raise PolicyError("snapshot digest requires repository identity")
            repository = (
                read_snapshot(actor, body.repository_id, body.expected_snapshot_digest)
                if body.repository_id
                else None
            )
            if body.repository is not None:
                if not active_policy.allow_any_repository or repository_resolver is None:
                    raise PolicyError("ticket repository selection not enabled")
                grant = authority.check(actor) if authority else None
                if grant is None or not grant.allow_any_repository:
                    raise PolicyError("ticket repository selection requires durable operator grant")
                try:
                    repository = repository_resolver(body.repository)
                    if repository.repository_id != body.repository.repository_id():
                        raise ValueError("repository identity mismatch")
                    if (
                        body.expected_snapshot_digest is not None
                        and repository.digest != body.expected_snapshot_digest
                    ):
                        raise ValueError("repository snapshot changed")
                except (ValueError, OSError):
                    raise PolicyError("selected repository unavailable or changed") from None
                db.put(
                    conn,
                    actor.workspace_id,
                    "repository_selection",
                    repository.repository_id,
                    1,
                    body.repository.model_dump(mode="json", exclude={"commit"}),
                )
            identifier, now = uuid4(), datetime.now(UTC)
            source = IntakeRequest(
                intake_id=identifier,
                source_text=body.source,
                source_digest=source_digest(body.source),
                received_at=now,
                source_kind="prompt",
            )
            template, state = draft(body.source, use_fixtures=not force_model_intake)
            payload = template.model_dump(mode="json")
            payload["specification_id"] = str(identifier)
            payload["approval_policy"].update(
                workspace_id=active_policy.workspace_id,
                policy_version=active_policy.version,
                max_age_seconds=active_policy.max_approval_seconds,
            )
            payload["risk"]["policy_version"] = active_policy.version
            payload["provenance"]["created_at"] = now.isoformat()
            if repository:
                payload["repository_context"] = repository.context().model_dump(mode="json")
            spec = seal_specification(payload)
            db.put(conn, actor.workspace_id, "intake", str(identifier), 1, source)
            db.put(conn, actor.workspace_id, "specification", str(identifier), 1, spec)
            if linear_source is not None:
                db.put(conn, actor.workspace_id, "linear_source", str(identifier), 1, linear_source)
            if supersedes is not None:
                db.put(
                    conn,
                    actor.workspace_id,
                    "source_supersession",
                    str(identifier),
                    1,
                    {"supersedes": supersedes, "actor_id": actor.actor_id},
                )
            if intake_queue_enabled:
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
                "workflow": "queued" if intake_queue_enabled else "held_paid_execution_disabled",
                "mode": spec.provenance.mode,
                "proposal_state": state.value,
            }

        return db.command(
            actor.workspace_id,
            actor.actor_id,
            command_key,
            {
                "action": "intake",
                "body": body.model_dump(mode="json"),
                **(
                    {"linear_source": linear_source.model_dump(mode="json")}
                    if linear_source
                    else {}
                ),
                **({"supersedes": supersedes} if supersedes else {}),
            },
            execute,
        )

    def record_cancellation(
        conn: Connection, actor: Principal, db: Store, spec: WorkSpecification, reason: str | None
    ) -> None:
        identifier = str(spec.specification_id)
        conn.execute(
            update(controls)
            .where(
                controls.c.workspace == actor.workspace_id,
                controls.c.specification_id == identifier,
            )
            .values(cancelled=1)
        )
        receipt = {
            "specification_id": identifier,
            "revision": spec.revision,
            "content_digest": spec.content_digest,
            "actor_id": actor.actor_id,
            **({"reason": reason} if reason else {}),
        }
        db.put(conn, actor.workspace_id, "cancellation", identifier, 1, receipt)
        if decision_queue_enabled:
            conn.execute(
                insert(outbox).values(
                    workspace=actor.workspace_id,
                    workflow_id=f"cancel-{identifier}",
                    dispatched=0,
                    payload=json.dumps(
                        {
                            "action": "cancel",
                            "specification_id": identifier,
                            "target_workflow": f"product-ops-{identifier}"
                            + (f"-r{spec.revision}" if spec.revision > 1 else ""),
                        }
                    ),
                )
            )
        audit(conn, actor, "cancellation_recorded", identifier, spec.content_digest)

    def supersede_source(
        conn: Connection,
        actor: Principal,
        db: Store,
        supersedes: str,
        source: LinearSource | None,
    ) -> None:
        """Cancel the stale specification in the same transaction that enrolls the edit.

        Only an approver may do this, only for the same issue after a real edit, and never
        once the stale specification has publication writes: those tickets need a human.
        """
        require_approver(actor)
        if source is None:
            raise PolicyError("only an enrolled Linear source can be superseded")
        if db.lock_specification(conn, actor.workspace_id, supersedes):
            raise PolicyError("superseded specification is already cancelled")
        enrolled = LinearSource.model_validate_json(
            json.dumps(db.get(actor.workspace_id, "linear_source", supersedes, connection=conn))
        )
        if enrolled.issue_id != source.issue_id or enrolled.digest() == source.digest():
            raise PolicyError("supersession requires an edit of the same enrolled issue")
        stale = spec_for(db, actor, UUID(supersedes), connection=conn)
        if publication_writes(
            db, conn, actor.workspace_id, supersedes, range(1, stale.revision + 1)
        ):
            raise PolicyError("published work cannot be superseded by a source edit")
        record_cancellation(conn, actor, db, stale, "superseded_by_source_edit")

    @app.post("/v1/intakes/prompts", status_code=201)
    def prompt_intake(
        body: PromptIntakeCommand,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
        command_key: Annotated[str, Depends(key)],
    ) -> dict[str, Any]:
        if repository_names is None:
            raise HTTPException(503, "Named repository intake is not configured")
        if "intake_reader" not in actor.roles:
            raise PolicyError("intake reader role required")
        declared = [
            line[len("Repository:") :].strip()
            for line in body.source.splitlines()
            if line.startswith("Repository:")
        ]
        if len(declared) > 1 or (declared and declared[0] != body.repository):
            raise PolicyError("conflicting repository declarations")
        return submit_intake(
            IntakeCommand(source=body.source, repository=repository_names(body.repository)),
            actor,
            db,
            command_key,
        )

    @app.post("/v1/intakes/linear", status_code=201)
    def linear_intake(
        body: LinearIntakeCommand,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
    ) -> dict[str, Any]:
        if linear_source_reader is None or repository_names is None:
            raise HTTPException(503, "Linear intake is not configured")
        if "intake_reader" not in actor.roles:
            raise PolicyError("intake reader role required")
        grant = authority.check(actor) if authority else None
        if (
            grant is None
            or linear_scope is None
            or not grant.allow_any_repository
            or not active_policy.allow_any_repository
        ):
            raise PolicyError("durable repository selection authority required")
        try:
            source = linear_source_reader(body.issue)
            allowed = {t.provider_id for t in linear_scope.teams if t.local_id in grant.team_ids}
            if (
                source.team_id not in allowed
                or source.organization_id != linear_scope.organization_id
            ):
                raise PolicyError("source exceeds current operator scope")
            selected = repository_names(repository_name(source, body.repository))
        except ValueError:
            raise PolicyError("invalid Linear reference or repository selection") from None
        except UnknownOutcome:
            raise HTTPException(503, "Linear source temporarily unavailable") from None
        # One durable command per issue/operator, independent of HTTP retry keys.
        # Editing an enrolled issue conflicts; it never silently replaces approved work.
        # An explicit supersession is one command per issue content.
        return submit_intake(
            IntakeCommand(source=source.text(), repository=selected),
            actor,
            db,
            "linear-source-"
            + str(source.issue_id)
            + ("-" + source.digest()[:32] if body.supersedes else ""),
            source,
            body.supersedes,
        )

    def read_snapshot(
        actor: Principal, repository_id: str, expected: str | None = None
    ) -> Snapshot:
        if (
            not active_policy.allow_any_repository
            and repository_id not in active_policy.repositories
        ) or repository_id not in roots:
            raise PolicyError("repository outside configured scope")
        if authority:
            grant = authority.check(actor)
            if not grant.allow_any_repository and repository_id not in grant.repository_ids:
                raise PolicyError("repository outside identity grant")
        try:
            return inspect_repository(repository_id, roots, expected_digest=expected)
        except (OSError, ValueError):
            raise PolicyError("repository snapshot unavailable or changed") from None

    @app.get("/v1/repositories/{repository_id}/snapshot")
    def get_snapshot(
        repository_id: str, actor: Annotated[Principal, Depends(identity)]
    ) -> dict[str, Any]:
        return read_snapshot(actor, repository_id).model_dump(mode="json")

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
                **analysis_mode(db, actor.workspace_id, spec),
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

    @app.get("/v1/specifications/{identifier}/tickets")
    def get_tickets(
        identifier: UUID,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
    ) -> dict[str, Any]:
        from agentic_product_ops.adapters.linear.offline import description
        from agentic_product_ops.services.ticket_readiness import (
            EXECUTION_POLICIES,
            EXECUTION_POLICY_V2,
        )

        spec = spec_for(db, actor, identifier)
        if authority:
            authority._scope(authority.check(actor), spec)
        return {
            "specification_digest": spec.content_digest,
            "revision": spec.revision,
            "ticket_findings": ticket_findings(spec),
            "delivery_findings": delivery_findings(spec),
            "approval_required": True,
            "semantic_review_required": True,
            "tickets": [
                {
                    "id": work.local_id,
                    "title": work.title,
                    "description": description(
                        spec,
                        work,
                        "PREVIEW-NOT-PUBLISHED",
                        execution_details=active_policy.version in EXECUTION_POLICIES,
                        ticket_format="v2"
                        if active_policy.version == EXECUTION_POLICY_V2
                        else "v1",
                        repository_label=repository_label(db, actor.workspace_id, spec),
                    ),
                }
                for work in spec.work_items
            ],
        }

    @app.get("/v1/specifications/{identifier}/plan")
    def get_plan(
        identifier: UUID,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
    ) -> dict[str, Any]:
        spec = spec_for(db, actor, identifier)
        answers = load_clarifications(db, spec, active_policy)
        review = passing_review(db, actor.workspace_id, spec, active_policy)
        plan = (
            build_native_plan(
                spec,
                active_policy,
                linear_scope,
                clarifications=answers,
                review=review,
                repository_label=repository_label(db, actor.workspace_id, spec),
            )
            if linear_scope
            else build_plan(spec, active_policy, clarifications=answers, review=review)
        )
        return {"publication": "disabled", "plan": plan.model_dump(mode="json")}

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
            current_authority(conn, actor)
            spec = spec_for(db, actor, identifier, body, conn)
            try:
                recorded_review(db, actor.workspace_id, spec, active_policy)
            except Missing as exc:
                raise PolicyError("analysis and review have not completed") from exc
            answers = load_clarifications(db, spec, active_policy)
            review = passing_review(db, actor.workspace_id, spec, active_policy)
            plan = (
                build_native_plan(
                    spec,
                    active_policy,
                    linear_scope,
                    clarifications=answers,
                    review=review,
                    repository_label=repository_label(db, actor.workspace_id, spec),
                )
                if linear_scope
                else build_plan(spec, active_policy, clarifications=answers, review=review)
            )
            if (
                linear_scope is not None or body.plan_digest is not None
            ) and body.plan_digest != plan.content_digest:
                raise Conflict("reviewed publication plan changed or was not acknowledged")
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
                    clarifications=answers,
                    review=review,
                )
            db.put(conn, actor.workspace_id, "approval", str(approval.approval_id), 1, approval)
            db.put(
                conn, actor.workspace_id, "publication_plan", str(identifier), spec.revision, plan
            )
            if authority:
                authority.bind_approval(conn, actor, approval, spec)
            renewal = record_decision(db, conn, actor.workspace_id, str(identifier), approval, now)
            # A renewed revision's workflow already completed; durable records carry authority.
            if decision_queue_enabled and not renewal:
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
                ("approval_renewed" if renewal else "approval_recorded")
                if approve
                else "rejection_recorded",
                str(identifier),
                approval.content_digest,
            )
            return {
                "approval": approval.model_dump(mode="json"),
                "publication": "disabled",
                "renewal": renewal,
            }

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
        if source_guard is not None:
            source_guard(str(identifier))
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
            current_authority(conn, actor)
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
                "workspace_id": actor.workspace_id,
                "specification_id": str(identifier),
                "base_revision": spec.revision,
                "base_digest": spec.content_digest,
                "question_id": body.question_id,
                "question_text": question.question,
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
            parsed_receipt = ClarificationReceipt.model_validate_json(json.dumps(receipt))
            if authority:
                authority.bind_clarification(conn, actor, parsed_receipt)
            db.put(
                conn,
                actor.workspace_id,
                "clarification",
                receipt_id,
                1,
                parsed_receipt,
            )
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
            current_authority(conn, actor)
            spec = spec_for(db, actor, identifier, body, conn)
            record_cancellation(conn, actor, db, spec, None)
            return {"cancelled": True, "publication": "disabled"}

        return db.command(
            actor.workspace_id,
            actor.actor_id,
            command_key,
            {"id": str(identifier), "action": "cancel", "body": body.model_dump(mode="json")},
            execute,
        )

    @app.post("/v1/specifications/{identifier}/risk")
    def risk(
        identifier: UUID,
        body: RiskCommand,
        actor: Annotated[Principal, Depends(identity)],
        command_key: Annotated[str, Depends(key)],
    ) -> dict[str, Any]:
        require_approver(actor)
        if risk_handler is None:
            raise HTTPException(503, "risk reassessment provider is not configured")
        return risk_handler(str(identifier), actor, body, command_key)

    @app.post("/v1/specifications/{identifier}/publish")
    def publish(
        identifier: UUID,
        actor: Annotated[Principal, Depends(identity)],
        command_key: Annotated[str, Depends(key)],
    ) -> dict[str, Any]:
        require_approver(actor)
        if publication_handler is not None:
            return publication_handler(str(identifier), actor, command_key)
        raise HTTPException(503, "live publication is disabled; no provider credentials configured")

    @app.post("/v1/specifications/{identifier}/reconcile")
    def reconcile(
        identifier: UUID, actor: Annotated[Principal, Depends(identity)]
    ) -> dict[str, Any]:
        # Read-only observation of recorded write intents; it cannot create provider objects.
        require_approver(actor)
        if reconciliation_handler is None:
            raise HTTPException(503, "publication reconciliation is not configured")
        return reconciliation_handler(str(identifier), actor)

    @app.get("/v1/specifications/{identifier}/state")
    def lifecycle_state(
        identifier: UUID,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
    ) -> dict[str, Any]:
        if state_handler is not None:
            return state_handler(str(identifier))
        state = publication_state(db, actor.workspace_id, str(identifier), datetime.now(UTC))
        return {
            "specification_id": str(identifier),
            "state": state.value if state else "PRE_DECISION_WORKFLOW",
            "source": "durable_records",
        }

    @app.get("/v1/publications/{identifier}")
    def publication(
        identifier: UUID,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
    ) -> dict[str, Any]:
        return db.get(actor.workspace_id, "publication", str(identifier))

    @app.get("/handoffs/{digest}", response_model=None)
    def handoff_by_specification(
        digest: str, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, Any] | JSONResponse:
        # Delivery OS's read-only credential, separate from the operator and the browser.
        # 200: freshly signed envelope; 404: unknown or not yet available; 410 + Reason:
        # superseded or revoked (pull contract, ADR-028).
        if handoff_reader is None:
            raise HTTPException(503, "handoff reading is not configured")
        if authorization is None or not authorization.startswith("Bearer "):
            raise HTTPException(401, "authentication required")
        try:
            return handoff_reader(authorization[7:], digest)
        except HandoffGone as gone:
            return JSONResponse(
                status_code=410,
                content={"detail": "handoff no longer valid", "reason": gone.reason},
                headers={"Reason": gone.reason},
            )

    @app.get("/v1/handoffs/{identifier}")
    def handoff(
        identifier: UUID,
        actor: Annotated[Principal, Depends(identity)],
        db: Annotated[Store, Depends(database)],
    ) -> dict[str, Any]:
        return db.get(actor.workspace_id, "handoff", str(identifier))

    return app
