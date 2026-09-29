import json
from datetime import timedelta

import pytest
from pydantic import ValidationError

from agentic_product_ops.adapters.artifacts.handoff import Handoff, export_handoff
from agentic_product_ops.adapters.linear.offline import FakeLinear, OfflinePublisher, build_plan
from agentic_product_ops.cli import simulated_approval
from agentic_product_ops.domain.contracts import SpecificationApproval, seal_specification
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy


def publish(publisher, spec, approval, now, policy=None):
    policy = policy or ServerPolicy()
    return publisher.publish(
        spec,
        build_plan(spec, policy),
        approval,
        policy,
        authenticated_actor="offline-reviewer",
        now=now,
    )


def test_duplicate_publish_exactly_one_fake_set(valid, now):
    provider = FakeLinear()
    publisher = OfflinePublisher(provider)
    approval = simulated_approval(valid, now)
    first = publish(publisher, valid, approval, now)
    assert publish(publisher, valid, approval, now) == first
    assert provider.calls == len(valid.work_items)


def test_response_lost_reconciles_without_recreate(valid, now):
    provider = FakeLinear()
    provider.lose_next_response = True
    publisher = OfflinePublisher(provider)
    approval = simulated_approval(valid, now)
    receipts = publish(publisher, valid, approval, now)
    assert receipts[0].status == "UNKNOWN"
    assert provider.calls == 1
    provider.lookup_available = False
    assert publish(publisher, valid, approval, now)[0].status == "UNKNOWN"
    assert provider.calls == 1
    provider.lookup_available = True
    receipts = publish(publisher, valid, approval, now)
    assert all(r.status == "SUCCEEDED" for r in receipts)
    assert provider.calls == len(valid.work_items)


@pytest.mark.parametrize(
    "change",
    [
        lambda a: a.update(revision=2),
        lambda a: a.update(content_digest="f" * 64),
        lambda a: a.update(actor_id="attacker"),
        lambda a: a.update(decision="reject"),
        lambda a: a.update(policy_version="stale"),
        lambda a: a["scope"].update(workspace_id="other"),
        lambda a: a["scope"].update(team_ids=["other"]),
        lambda a: a["scope"].update(repository_ids=["other"]),
        lambda a: a["scope"].update(allowed_mutation_count=100),
        lambda a: a["scope"].update(plan_digest="f" * 64),
        lambda a: a["scope"].update(operation_keys=["f" * 64]),
    ],
)
def test_invalid_approval_no_writes(valid, now, change):
    payload = simulated_approval(valid, now).model_dump(mode="json")
    change(payload)
    approval = SpecificationApproval.model_validate_json(json.dumps(payload))
    provider = FakeLinear()
    with pytest.raises(PolicyError):
        publish(OfflinePublisher(provider), valid, approval, now)
    assert provider.calls == 0


@pytest.mark.parametrize("offset", [-1, 1800, 3600])
def test_future_or_expired_approval(valid, now, offset):
    provider = FakeLinear()
    with pytest.raises(PolicyError, match="expired"):
        publish(
            OfflinePublisher(provider),
            valid,
            simulated_approval(valid, now),
            now + timedelta(seconds=offset),
        )
    assert provider.calls == 0


def test_revision_and_content_edits_invalidate_approval(valid, now):
    approval = simulated_approval(valid, now)
    payload = valid.model_dump(mode="json")
    payload["objective"] += " Updated."
    provider = FakeLinear()
    with pytest.raises(PolicyError, match="stale"):
        publish(OfflinePublisher(provider), seal_specification(payload), approval, now)
    payload["revision"] += 1
    with pytest.raises(PolicyError, match="stale"):
        publish(OfflinePublisher(provider), seal_specification(payload), approval, now)
    assert provider.calls == 0


def test_key_conflict(valid, now):
    provider = FakeLinear()
    publisher = OfflinePublisher(provider)
    publish(publisher, valid, simulated_approval(valid, now), now)
    payload = valid.model_dump(mode="json")
    payload["objective"] += " Changed without revision."
    changed = seal_specification(payload)
    with pytest.raises(PolicyError, match="key reused"):
        publish(publisher, changed, simulated_approval(changed, now), now)
    assert provider.calls == len(valid.work_items)


def test_cancel_no_new_writes(valid, now):
    provider = FakeLinear()
    publisher = OfflinePublisher(provider)
    publisher.cancel()
    with pytest.raises(PolicyError, match="cancelled"):
        publish(publisher, valid, simulated_approval(valid, now), now)
    assert provider.calls == 0


def test_handoff_exact_digest_and_tamper(low_risk, now):
    policy = ServerPolicy()
    approval = simulated_approval(low_risk, now)
    plan = build_plan(low_risk, policy)
    receipts = publish(OfflinePublisher(FakeLinear()), low_risk, approval, now)
    handoff = export_handoff(low_risk, approval, plan, receipts, policy)
    restored = Handoff.model_validate_json(handoff.model_dump_json())
    assert restored.specification == low_risk
    payload = handoff.model_dump(mode="json")
    payload["publications"][0]["provider_id"] = "tampered"
    with pytest.raises(ValidationError, match="digest"):
        Handoff.model_validate_json(json.dumps(payload))


def test_handoff_high_risk_and_unknown_denied(valid, low_risk, now):
    with pytest.raises(PolicyError, match="risk"):
        export_handoff(
            valid,
            simulated_approval(valid, now),
            build_plan(valid, ServerPolicy()),
            (),
            ServerPolicy(),
        )
    provider = FakeLinear()
    provider.lose_next_response = True
    approval = simulated_approval(low_risk, now)
    receipts = publish(OfflinePublisher(provider), low_risk, approval, now)
    with pytest.raises(ValidationError, match="unknown"):
        export_handoff(
            low_risk, approval, build_plan(low_risk, ServerPolicy()), receipts, ServerPolicy()
        )
