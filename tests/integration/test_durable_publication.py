from datetime import timedelta

import pytest

from agentic_product_ops.adapters.linear.offline import FakeLinear, build_plan
from agentic_product_ops.adapters.persistence.store import Store, engine, metadata
from agentic_product_ops.cli import simulated_approval
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy
from agentic_product_ops.services.publication import DurableSimulationPublisher


def test_unknown_survives_publisher_restart(tmp_path, valid, now):
    db = engine(f"sqlite:///{tmp_path / 'publication.db'}", testing=True)
    metadata.create_all(db)
    provider = FakeLinear()
    provider.lose_next_response = True
    policy, plan, approval = (
        ServerPolicy(),
        build_plan(valid, ServerPolicy()),
        simulated_approval(valid, now),
    )
    first = DurableSimulationPublisher(Store(db), provider, lambda: now)
    assert first.publish(valid, plan, approval, policy, "offline-reviewer")[0].status == "UNKNOWN"
    db.dispose()
    reopened = engine(f"sqlite:///{tmp_path / 'publication.db'}", testing=True)
    second = DurableSimulationPublisher(Store(reopened), provider, lambda: now)
    receipts = second.publish(valid, plan, approval, policy, "offline-reviewer")
    assert all(r.status == "SUCCEEDED" for r in receipts)
    assert provider.calls == len(valid.work_items)
    second.publish(valid, plan, approval, policy, "offline-reviewer")
    assert provider.calls == len(valid.work_items)
    reopened.dispose()


def test_real_clock_rechecked_and_cancel_persisted(tmp_path, valid, now):
    db = engine(f"sqlite:///{tmp_path / 'publication.db'}", testing=True)
    metadata.create_all(db)
    provider = FakeLinear()
    ticks = iter([now, now, now + timedelta(hours=1)])
    publisher = DurableSimulationPublisher(Store(db), provider, lambda: next(ticks))
    approval, plan = simulated_approval(valid, now), build_plan(valid, ServerPolicy())
    with pytest.raises(PolicyError, match="expired"):
        publisher.publish(valid, plan, approval, ServerPolicy(), "offline-reviewer")
    assert provider.calls == 1
    publisher.cancel("offline-workspace", str(valid.specification_id))
    reopened = DurableSimulationPublisher(Store(db), provider, lambda: now)
    with pytest.raises(PolicyError, match="cancelled"):
        reopened.publish(valid, plan, approval, ServerPolicy(), "offline-reviewer")
    db.dispose()
