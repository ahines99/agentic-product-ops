"""Real local Temporal integration, enabled only with an explicit test-server address."""

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from temporalio.client import Client
from temporalio.worker import Replayer, Worker

from agentic_product_ops.adapters.persistence.store import Store, engine, metadata
from agentic_product_ops.cli import simulated_approval
from agentic_product_ops.policies.validation import ServerPolicy
from agentic_product_ops.workflows.activities import GovernanceActivities
from agentic_product_ops.workflows.governance import GovernanceInput, GovernanceWorkflow

pytestmark = pytest.mark.skipif(
    not os.getenv("PRODUCT_OPS_TEST_TEMPORAL_ADDRESS"),
    reason="explicit local Temporal test server required",
)


@pytest.mark.asyncio
async def test_wait_survives_worker_restart_and_replay(tmp_path, valid):
    database = engine(f"sqlite:///{tmp_path / 'temporal-records.db'}", testing=True)
    metadata.create_all(database)
    store = Store(database)
    with database.begin() as connection:
        store.put(
            connection, "offline-workspace", "specification", str(valid.specification_id), 1, valid
        )
    activities = GovernanceActivities(store, ServerPolicy())
    client = await Client.connect(os.environ["PRODUCT_OPS_TEST_TEMPORAL_ADDRESS"])
    queue = f"test-{uuid4()}"
    arguments = dict(
        client=client,
        task_queue=queue,
        workflows=[GovernanceWorkflow],
        activities=[activities.prepare_governance, activities.validate_governance_receipt],
    )
    async with Worker(**arguments):
        handle = await client.start_workflow(
            GovernanceWorkflow.run,
            GovernanceInput(
                workspace="offline-workspace",
                specification_id=str(valid.specification_id),
                content_digest=valid.content_digest,
                wait_seconds=30,
            ),
            id=f"workflow-{uuid4()}",
            task_queue=queue,
        )
        for _ in range(100):
            if await handle.query(GovernanceWorkflow.status) == "AWAITING_APPROVAL":
                break
            await asyncio.sleep(0.05)
        assert await handle.query(GovernanceWorkflow.status) == "AWAITING_APPROVAL"
    approval = simulated_approval(valid, datetime.now(UTC))
    with database.begin() as connection:
        store.put(
            connection, "offline-workspace", "approval", str(approval.approval_id), 1, approval
        )
    # No worker exists while this signal is durably accepted by Temporal.
    await handle.signal(GovernanceWorkflow.decision_recorded, str(approval.approval_id))
    async with Worker(**arguments):
        assert await handle.result() == "APPROVED"
    history = await handle.fetch_history()
    await Replayer(workflows=[GovernanceWorkflow]).replay_workflow(history)
    database.dispose()


@pytest.mark.asyncio
async def test_untrusted_signal_timeout_and_cancellation(tmp_path, valid):
    database = engine(f"sqlite:///{tmp_path / 'signals.db'}", testing=True)
    metadata.create_all(database)
    store = Store(database)
    with database.begin() as connection:
        store.put(
            connection, "offline-workspace", "specification", str(valid.specification_id), 1, valid
        )
    activities = GovernanceActivities(store, ServerPolicy())
    client = await Client.connect(os.environ["PRODUCT_OPS_TEST_TEMPORAL_ADDRESS"])
    queue = f"test-{uuid4()}"
    async with Worker(
        client,
        task_queue=queue,
        workflows=[GovernanceWorkflow],
        activities=[activities.prepare_governance, activities.validate_governance_receipt],
    ):
        request = GovernanceInput(
            "offline-workspace", str(valid.specification_id), valid.content_digest, 2
        )
        handle = await client.start_workflow(
            GovernanceWorkflow.run, request, id=f"expire-{uuid4()}", task_queue=queue
        )
        await handle.signal(GovernanceWorkflow.decision_recorded, "forged-approval")
        assert await handle.result() == "EXPIRED"
        cancelled = await client.start_workflow(
            GovernanceWorkflow.run, request, id=f"cancel-{uuid4()}", task_queue=queue
        )
        await cancelled.signal(GovernanceWorkflow.cancel)
        assert await cancelled.result() == "CANCELLED"
    database.dispose()
