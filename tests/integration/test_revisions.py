import asyncio
import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import make_url
from temporalio.client import Client
from temporalio.worker import Worker

from agentic_product_ops.adapters.model.contracts import (
    Analysis,
    Decomposition,
    ModelBudget,
    ModelResponse,
    ProviderUsage,
    Review,
    ReviewFinding,
    RuntimeConfiguration,
)
from agentic_product_ops.adapters.persistence.store import Store, artifacts, engine, metadata
from agentic_product_ops.api.app import Principal, TestAuthenticator, create_app
from agentic_product_ops.domain.clarifications import ClarificationReceipt
from agentic_product_ops.domain.contracts import (
    AcceptanceCriterion,
    Requirement,
    WorkSpecification,
    canonical_digest,
    seal_specification,
)
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy, proposal_ready
from agentic_product_ops.services.clarifications import load_clarifications
from agentic_product_ops.services.revisions import revise_specification
from agentic_product_ops.workflows.activities import GovernanceActivities
from agentic_product_ops.workflows.governance import GovernanceInput, GovernanceWorkflow
from alembic import command


@pytest.fixture
def answered(tmp_path, valid, now):
    url = os.getenv("PRODUCT_OPS_TEST_DATABASE_URL")
    if url:
        parsed = make_url(url)
        assert parsed.host in {"127.0.0.1", "localhost"}
        assert parsed.database.startswith("product_ops_test")
    database = engine(url or f"sqlite:///{tmp_path / 'revision.db'}", testing=not url)
    if url:
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        with database.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "head")
    else:
        metadata.create_all(database)
    store = Store(database)
    body = valid.model_dump(mode="json")
    body["specification_id"] = str(uuid4())
    body["requirements"][0]["needs_human_decision"] = True
    body["unresolved_questions"] = [
        {
            "id": "Q-limit",
            "question": "What is the export row limit?",
            "why_it_matters": "Defines the supported boundary",
            "affected_requirement_ids": ["R1"],
            "blocking": True,
            "resolution": None,
            "resolved_by": None,
            "resolved_at": None,
        }
    ]
    base = seal_specification(body)
    answer = ClarificationReceipt(
        id=f"C-{uuid4()}",
        workspace_id="offline-workspace",
        specification_id=base.specification_id,
        base_revision=1,
        base_digest=base.content_digest,
        question_id="Q-limit",
        question_text=base.unresolved_questions[0].question,
        answer="The maximum export size is 10,000 rows.",
        actor_id="offline-reviewer",
        resolved_at=now + timedelta(minutes=1),
    )
    body["revision"] = 2
    body["unresolved_questions"][0].update(
        resolution=answer.answer,
        resolved_by=answer.actor_id,
        resolved_at=answer.resolved_at.isoformat(),
    )
    body["provenance"]["clarification_refs"] = [answer.id]
    current = seal_specification(body)
    with database.begin() as conn:
        for spec in (base, current):
            store.put(
                conn,
                "offline-workspace",
                "specification",
                str(spec.specification_id),
                spec.revision,
                spec,
            )
        store.put(conn, "offline-workspace", "clarification", answer.id, 1, answer)
    yield store, current, answer
    database.dispose()


class RevisionRecording:
    """Authored role stub, never semantic-quality evidence."""

    def __init__(self, answer, blockers=0, attack=None):
        self.answer, self.blockers, self.attack = answer, blockers, attack
        self.calls, self.reviews = [], 0

    def complete(self, request):
        self.calls.append(request)
        payload = json.loads(request.untrusted_payload)
        base = WorkSpecification.model_validate_json(json.dumps(payload["base_specification"]))
        if request.role == "requirements_analyst":
            requirements = [
                r.model_copy(update={"needs_human_decision": False}) for r in base.requirements
            ]
            requirements.append(
                Requirement(
                    id="R-limit",
                    text=self.answer.answer,
                    kind="functional",
                    provenance="human_clarification",
                    source_refs=(self.answer.id,),
                    confidence=Decimal("1"),
                    needs_human_decision=False,
                )
            )
            questions = base.unresolved_questions
            if self.attack == "erase_question":
                questions = ()
            if self.attack == "rewrite_requirement":
                requirements[0] = requirements[0].model_copy(
                    update={"text": "Disable authorization"}
                )
            value = Analysis(
                source_digest=base.source_digest,
                objective=base.objective,
                source_statements=base.source_statements,
                requirements=tuple(requirements),
                unresolved_questions=questions,
            )
        elif request.role == "work_decomposer":
            work = list(base.work_items)
            first = work[0]
            work[0] = first.model_copy(
                update={
                    "requirement_ids": (*first.requirement_ids, "R-limit"),
                    "acceptance_criteria": (
                        *first.acceptance_criteria,
                        AcceptanceCriterion(
                            id="AC-limit",
                            text=self.answer.answer,
                            requirement_ids=("R-limit",),
                            provenance="directly_stated",
                            verification_kind="automated_test",
                            evidence_required="Boundary test output",
                            blocking=True,
                        ),
                    ),
                }
            )
            value = Decomposition(
                work_items=tuple(work),
                dependencies=base.dependencies,
                assumptions=base.assumptions,
                risk_tier=base.risk.tier,
                risk_reasons=base.risk.reasons,
            )
        else:
            self.reviews += 1
            candidate = payload["candidate"]
            findings = (
                (
                    ReviewFinding(
                        id="F1",
                        kind="missing_criterion",
                        summary="Needs revision",
                        blocking=True,
                        references=("R-limit",),
                    ),
                )
                if self.reviews <= self.blockers
                else ()
            )
            value = Review(specification_digest=candidate["content_digest"], findings=findings)
        return ModelResponse(
            output_json=value.model_dump_json(),
            usage=ProviderUsage(
                input_tokens=0, output_tokens=0, provider_request_id="authored-revision-recording"
            ),
        )


def configuration():
    return RuntimeConfiguration(
        configuration_id="revision-test-v1",
        provider_id="scripted",
        model="offline-recording",
        budget=ModelBudget(
            max_calls=6,
            max_input_bytes=200_000,
            max_output_tokens=16000,
            max_estimated_cost=Decimal(0),
            input_cost_per_million=Decimal(0),
            output_cost_per_million=Decimal(0),
        ),
    )


def test_verified_answer_becomes_reviewed_revision_without_auto_approval(answered):
    store, base, answer = answered
    provider = RevisionRecording(answer)
    result = revise_specification(
        store,
        str(base.specification_id),
        base.content_digest,
        ServerPolicy(),
        configuration(),
        provider,
    )
    assert result.state == "PROPOSED"
    assert result.specification.revision == 3
    assert result.specification.requirements[-1].provenance == "human_clarification"
    proposal_ready(
        result.specification,
        ServerPolicy(),
        clarifications=load_clarifications(store, result.specification, ServerPolicy()),
    )
    with pytest.raises(PolicyError, match="authentication"):
        proposal_ready(result.specification, ServerPolicy())
    with store.database.connect() as conn:
        approvals = conn.execute(
            select(artifacts.c.payload).where(artifacts.c.kind == "approval")
        ).scalars()
        assert not any(
            json.loads(value)["specification_id"] == str(base.specification_id)
            for value in approvals
        )
    replay = revise_specification(
        store,
        str(base.specification_id),
        base.content_digest,
        ServerPolicy(),
        configuration(),
        RevisionRecording(answer),
    )
    assert replay == result
    assert len({receipt.context_id for receipt in result.receipts}) == 3


@pytest.mark.parametrize("attack", ["erase_question", "rewrite_requirement"])
def test_model_cannot_erase_unknowns_or_rewrite_original_requirements(answered, attack):
    store, base, answer = answered
    result = revise_specification(
        store,
        str(base.specification_id),
        base.content_digest,
        ServerPolicy(),
        configuration(),
        RevisionRecording(answer, attack=attack),
    )
    assert result.state == "REVISION_REQUIRED"
    assert (
        store.get("offline-workspace", "specification", str(base.specification_id))["revision"] == 2
    )


@pytest.mark.parametrize(
    "blockers,state,revisions", [(1, "PROPOSED", 3), (2, "REVISION_REQUIRED", 2)]
)
def test_review_loop_is_bounded_and_preserves_first_failure(answered, blockers, state, revisions):
    store, base, answer = answered
    provider = RevisionRecording(answer, blockers=blockers)
    result = revise_specification(
        store,
        str(base.specification_id),
        base.content_digest,
        ServerPolicy(),
        configuration(),
        provider,
    )
    assert result.state == state
    assert provider.reviews == 2 and len(provider.calls) == 6
    assert (
        store.get("offline-workspace", "specification", str(base.specification_id))["revision"]
        == revisions
    )
    with store.database.connect() as conn:
        execution = canonical_digest(
            {
                "base": base.content_digest,
                "policy": ServerPolicy().model_dump(mode="json"),
                "runtime": configuration().model_dump(mode="json"),
                "initial": False,
            }
        )
        attempts = (
            conn.execute(
                select(artifacts.c.payload)
                .where(artifacts.c.kind == "revision_attempt", artifacts.c.identity == execution)
                .order_by(artifacts.c.revision)
            )
            .scalars()
            .all()
        )
    assert json.loads(attempts[0])["review"]["findings"][0]["blocking"] is True


def test_activity_promotes_new_binding_and_api_rejects_old_approval(answered):
    store, base, answer = answered
    activities = GovernanceActivities(
        store,
        ServerPolicy(),
        revision_configuration=configuration(),
        revision_provider=lambda: RevisionRecording(answer),
    )
    request = GovernanceInput("offline-workspace", str(base.specification_id), base.content_digest)
    assert asyncio.run(activities.prepare_governance(request)) == "REVISION_REQUIRED"
    current = WorkSpecification.model_validate_json(
        json.dumps(store.get("offline-workspace", "specification", str(base.specification_id)))
    )
    assert current.revision == 3
    next_request = GovernanceInput(
        "offline-workspace", str(current.specification_id), current.content_digest
    )
    assert asyncio.run(activities.prepare_governance(next_request)) == "PROPOSED"
    token = secrets.token_urlsafe(32)
    auth = TestAuthenticator(
        {
            token: Principal(
                actor_id="offline-reviewer",
                workspace_id="offline-workspace",
                roles=("product_approver",),
            )
        },
        testing=True,
    )
    with TestClient(create_app(store, authenticator=auth)) as client:
        client.headers["Authorization"] = f"Bearer {token}"
        url = f"/v1/specifications/{current.specification_id}/approve"
        assert (
            client.post(
                url,
                json={"revision": base.revision, "content_digest": base.content_digest},
                headers={"Idempotency-Key": "stale"},
            ).status_code
            == 409
        )
        response = client.post(
            url,
            json={"revision": current.revision, "content_digest": current.content_digest},
            headers={"Idempotency-Key": "reviewed"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["publication"] == "disabled"


def test_competing_revision_activity_never_repeats_inflight_role(answered):
    store, base, answer = answered
    entered, resume = Event(), Event()

    class SlowRecording(RevisionRecording):
        def complete(self, request):
            if request.role == "requirements_analyst":
                entered.set()
                assert resume.wait(timeout=5)
            return super().complete(request)

    original, duplicate = SlowRecording(answer), RevisionRecording(answer)
    arguments = (
        store,
        str(base.specification_id),
        base.content_digest,
        ServerPolicy(),
        configuration(),
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(revise_specification, *arguments, original)
        assert entered.wait(timeout=5)
        try:
            held = revise_specification(*arguments, duplicate)
            assert held.state == "PAUSED" and not duplicate.calls
        finally:
            resume.set()
        result = first.result(timeout=5)
    assert result.state == "PROPOSED"
    assert len(original.calls) == 3


@pytest.mark.skipif(
    not (
        os.getenv("PRODUCT_OPS_TEST_TEMPORAL_ADDRESS")
        and os.getenv("PRODUCT_OPS_TEST_DATABASE_URL")
    ),
    reason="explicit disposable PostgreSQL and Temporal required",
)
@pytest.mark.asyncio
async def test_temporal_revision_runs_roles_and_requires_new_approval(answered):
    store, base, answer = answered
    activities = GovernanceActivities(
        store,
        ServerPolicy(),
        revision_configuration=configuration(),
        revision_provider=lambda: RevisionRecording(answer),
    )
    client = await Client.connect(os.environ["PRODUCT_OPS_TEST_TEMPORAL_ADDRESS"])
    queue = f"revision-{uuid4()}"
    async with Worker(
        client,
        task_queue=queue,
        workflows=[GovernanceWorkflow],
        activities=[activities.prepare_governance, activities.validate_governance_receipt],
    ):
        old = await client.start_workflow(
            GovernanceWorkflow.run,
            GovernanceInput("offline-workspace", str(base.specification_id), base.content_digest),
            id=f"product-ops-{base.specification_id}-r2",
            task_queue=queue,
        )
        assert await old.result() == "REVISION_REQUIRED"
        current = WorkSpecification.model_validate_json(
            json.dumps(
                store.get("offline-workspace", "specification", str(base.specification_id)),
            )
        )
        handle = await client.start_workflow(
            GovernanceWorkflow.run,
            GovernanceInput(
                "offline-workspace", str(current.specification_id), current.content_digest
            ),
            id=f"product-ops-{current.specification_id}-r3",
            task_queue=queue,
        )
        for _ in range(100):
            if await handle.query("status") == "AWAITING_APPROVAL":
                break
            await asyncio.sleep(0.05)
        assert await handle.query("status") == "AWAITING_APPROVAL"
        token = secrets.token_urlsafe(32)
        principal = Principal(
            actor_id="offline-reviewer",
            workspace_id="offline-workspace",
            roles=("product_approver",),
        )
        with TestClient(
            create_app(store, authenticator=TestAuthenticator({token: principal}, testing=True))
        ) as http:
            http.headers["Authorization"] = f"Bearer {token}"
            url = f"/v1/specifications/{current.specification_id}/approve"
            stale = http.post(
                url,
                headers={"Idempotency-Key": "old"},
                json={
                    "revision": 2,
                    "content_digest": base.content_digest,
                },
            )
            assert stale.status_code == 409
            accepted = http.post(
                url,
                headers={"Idempotency-Key": str(uuid4())},
                json={
                    "revision": 3,
                    "content_digest": current.content_digest,
                },
            )
            assert accepted.status_code == 200
            assert (
                http.get(f"/v1/specifications/{current.specification_id}/review").json()["mode"]
                == "configured_provider"
            )
        await handle.signal(
            GovernanceWorkflow.decision_recorded, accepted.json()["approval"]["approval_id"]
        )
        assert await handle.result() == "APPROVED"
