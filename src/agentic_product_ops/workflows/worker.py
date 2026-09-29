"""Development worker; explicit configured infrastructure, no live model or publication activity."""

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

from agentic_product_ops.adapters.persistence.store import Store, engine
from agentic_product_ops.policies.validation import ServerPolicy
from agentic_product_ops.workflows.activities import GovernanceActivities, dispatch_outbox
from agentic_product_ops.workflows.governance import GovernanceWorkflow


async def main() -> None:
    store = Store(engine(os.environ["PRODUCT_OPS_DATABASE_URL"]))
    client = await Client.connect(os.environ["PRODUCT_OPS_TEMPORAL_ADDRESS"])
    activities = GovernanceActivities(store, ServerPolicy())
    queue = "product-ops-governance"
    try:
        async with Worker(
            client,
            task_queue=queue,
            workflows=[GovernanceWorkflow],
            activities=[activities.prepare_governance, activities.validate_governance_receipt],
        ):
            while True:
                await dispatch_outbox(store, client, queue)
                await asyncio.sleep(1)
    finally:
        store.database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
