"""Connected API -> PostgreSQL outbox -> Temporal -> receipt validation, with test identity."""

import asyncio
import os
import secrets
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.engine import make_url
from temporalio.client import Client
from temporalio.worker import Worker

from agentic_product_ops.adapters.persistence.store import Store, engine, outbox
from agentic_product_ops.api.app import Principal, TestAuthenticator, create_app
from agentic_product_ops.policies.validation import ServerPolicy
from agentic_product_ops.services.drafting import load_fixture
from agentic_product_ops.workflows.activities import GovernanceActivities, dispatch_outbox
from agentic_product_ops.workflows.governance import GovernanceWorkflow
from alembic import command

pytestmark = pytest.mark.skipif(
    not (
        os.getenv("PRODUCT_OPS_TEST_TEMPORAL_ADDRESS")
        and os.getenv("PRODUCT_OPS_TEST_DATABASE_URL")
    ),
    reason="both explicit local test services required",
)


@pytest.mark.asyncio
async def test_api_postgres_temporal_connected_approval(valid):
    url = os.environ["PRODUCT_OPS_TEST_DATABASE_URL"]
    parsed = make_url(url)
    assert parsed.host in {"127.0.0.1", "localhost"}
    assert parsed.database and parsed.database.startswith("product_ops_test")
    database = engine(url)
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    with database.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, "head")
    store, token = Store(database), secrets.token_urlsafe(32)
    principal = Principal(
        actor_id="offline-reviewer", workspace_id="offline-workspace", roles=("product_approver",)
    )
    app = create_app(store, authenticator=TestAuthenticator({token: principal}, testing=True))
    with TestClient(app) as http:
        http.headers["Authorization"] = f"Bearer {token}"
        intake = http.post(
            "/v1/intakes",
            headers={"Idempotency-Key": str(uuid4())},
            json={"source": valid.source_statements[0].text},
        )
        assert intake.status_code == 201
        identifier = intake.json()["specification_id"]
        spec = http.get(f"/v1/specifications/{identifier}").json()
        premature = http.post(
            f"/v1/specifications/{identifier}/approve",
            headers={"Idempotency-Key": str(uuid4())},
            json={"revision": spec["revision"], "content_digest": spec["content_digest"]},
        )
        assert premature.status_code == 403
    client = await Client.connect(os.environ["PRODUCT_OPS_TEST_TEMPORAL_ADDRESS"])
    queue = f"connected-{uuid4()}"
    activities = GovernanceActivities(store, ServerPolicy())
    async with Worker(
        client,
        task_queue=queue,
        workflows=[GovernanceWorkflow],
        activities=[activities.prepare_governance, activities.validate_governance_receipt],
    ):
        assert await dispatch_outbox(store, client, queue) == 1
        assert await dispatch_outbox(store, client, queue) == 0
        handle = client.get_workflow_handle(f"product-ops-{identifier}")
        for _ in range(100):
            if await handle.query("status") == "AWAITING_APPROVAL":
                break
            await asyncio.sleep(0.05)
        assert await handle.query("status") == "AWAITING_APPROVAL"
        with TestClient(app) as http:
            http.headers["Authorization"] = f"Bearer {token}"
            assert (
                http.get(f"/v1/specifications/{identifier}/review").json()["mode"]
                == "recorded_roles"
            )
            decision = http.post(
                f"/v1/specifications/{identifier}/approve",
                headers={"Idempotency-Key": str(uuid4())},
                json={"revision": spec["revision"], "content_digest": spec["content_digest"]},
            )
            assert decision.status_code == 200
        assert await dispatch_outbox(store, client, queue) == 1
        assert await handle.result() == "APPROVED"
        # Lost outbox acknowledgement after successful start/signal must reconcile safely.
        with database.begin() as conn:
            conn.execute(update(outbox).values(dispatched=0))
        assert await dispatch_outbox(store, client, queue) == 2
        assert await handle.query("decision_receipt") == decision.json()["approval"]["approval_id"]
        with TestClient(app) as http:
            http.headers["Authorization"] = f"Bearer {token}"
            pending = http.post(
                "/v1/intakes",
                headers={"Idempotency-Key": str(uuid4())},
                json={"source": valid.source_statements[0].text},
            ).json()
            cancelled_id = pending["specification_id"]
            snapshot = http.get(f"/v1/specifications/{cancelled_id}").json()
            assert await dispatch_outbox(store, client, queue) == 1
            waiting = client.get_workflow_handle(f"product-ops-{cancelled_id}")
            for _ in range(100):
                if await waiting.query("status") == "AWAITING_APPROVAL":
                    break
                await asyncio.sleep(0.05)
            assert (
                http.post(
                    f"/v1/specifications/{cancelled_id}/cancel",
                    headers={"Idempotency-Key": str(uuid4())},
                    json={"revision": 1, "content_digest": snapshot["content_digest"]},
                ).status_code
                == 200
            )
            assert await dispatch_outbox(store, client, queue) == 1
            assert await waiting.result() == "CANCELLED"
            unclear = http.post(
                "/v1/intakes",
                headers={"Idempotency-Key": str(uuid4())},
                json={"source": load_fixture("ambiguous").source_statements[0].text},
            ).json()
            unclear_id = unclear["specification_id"]
            assert await dispatch_outbox(store, client, queue) == 1
            held = client.get_workflow_handle(f"product-ops-{unclear_id}")
            assert await held.result() == "AWAITING_CLARIFICATION"
            before = http.get(f"/v1/specifications/{unclear_id}").json()
            assert (
                http.post(
                    f"/v1/specifications/{unclear_id}/clarifications",
                    headers={"Idempotency-Key": str(uuid4())},
                    json={
                        "revision": 1,
                        "content_digest": before["content_digest"],
                        "question_id": "Q1",
                        "answer": "10,000 rows",
                    },
                ).status_code
                == 200
            )
            assert await dispatch_outbox(store, client, queue) == 1
            revision = client.get_workflow_handle(f"product-ops-{unclear_id}-r2")
            assert await revision.result() == "AWAITING_CLARIFICATION"
            assert (
                store.get("offline-workspace", "analysis_index", unclear_id)["content_digest"]
                != before["content_digest"]
            )
    assert decision.json()["publication"] == "disabled"
    database.dispose()
