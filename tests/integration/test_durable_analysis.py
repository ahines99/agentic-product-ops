import json
from decimal import Decimal

import pytest
from sqlalchemy import select

from agentic_product_ops.adapters.model.contracts import Analysis, ModelBudget
from agentic_product_ops.adapters.model.runner import PROMPTS, RunStopped, ScriptedProvider
from agentic_product_ops.adapters.persistence.store import (
    Missing,
    Store,
    artifacts,
    engine,
    metadata,
)
from agentic_product_ops.domain.contracts import canonical_digest, seal_specification
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy
from agentic_product_ops.services.durable_analysis import (
    DurableRoleRunner,
    RoleRecordings,
    analyze_specification,
    recorded_review,
)


@pytest.fixture
def store(tmp_path, valid):
    database = engine(f"sqlite:///{tmp_path / 'roles.db'}", testing=True)
    metadata.create_all(database)
    store = Store(database)
    with database.begin() as conn:
        store.put(conn, "offline-workspace", "specification", str(valid.specification_id), 1, valid)
    yield store
    database.dispose()


def test_completed_runs_reused_with_same_receipts_after_restart(store, valid):
    args = ("offline-workspace", str(valid.specification_id), valid.content_digest, ServerPolicy())
    first = analyze_specification(store, *args)
    assert first.state == "PROPOSED"
    assert len(first.receipts) == 3
    second = analyze_specification(Store(store.database), *args)
    assert first == second
    with store.database.connect() as conn:
        kinds = [row[0] for row in conn.execute(select(artifacts.c.kind))]
    for kind in ("role_intent", "role_request", "role_response", "role_result"):
        assert kinds.count(kind) == 3
    assert recorded_review(store, "offline-workspace", valid, ServerPolicy())["state"] == "PROPOSED"
    with pytest.raises(Missing):
        recorded_review(store, "offline-workspace", valid, ServerPolicy(version="changed"))


def test_superseded_digest_never_reuses_analysis(store, valid):
    payload = valid.model_dump(mode="json")
    payload["revision"] = 2
    changed = seal_specification(payload)
    with store.database.begin() as conn:
        store.put(
            conn, "offline-workspace", "specification", str(valid.specification_id), 2, changed
        )
    with pytest.raises(PolicyError, match="superseded"):
        analyze_specification(
            store,
            "offline-workspace",
            str(valid.specification_id),
            valid.content_digest,
            ServerPolicy(),
        )


def test_uncertain_intent_cannot_invoke_provider_again(store, valid):
    budget = ModelBudget(
        max_calls=3,
        max_input_bytes=200_000,
        max_output_tokens=16000,
        max_estimated_cost=Decimal(0),
        input_cost_per_million=Decimal(0),
        output_cost_per_million=Decimal(0),
    )
    provider = ScriptedProvider(())
    runner = DurableRoleRunner(store, "offline-workspace", valid.content_digest, provider, budget)
    policy, role, payload = ServerPolicy(), "requirements_analyst", json.dumps({"source": "input"})
    binding = {
        "specification_digest": valid.content_digest,
        "role": role,
        "payload": payload,
        "policy": policy.model_dump(mode="json"),
        "schema": Analysis.model_json_schema(),
        "prompt": PROMPTS[role],
        "model": "offline-recording",
        "budget": budget.model_dump(mode="json"),
    }
    step = canonical_digest(binding)
    with store.database.begin() as conn:
        store.put(conn, "offline-workspace", "role_intent", step, 1, binding)
    with pytest.raises(RunStopped, match="uncertain"):
        runner.run(role, payload, policy, Analysis)
    assert provider.requests == []


def test_cached_individual_step_preserves_context_and_usage(store, valid):
    budget = ModelBudget(
        max_calls=3,
        max_input_bytes=200_000,
        max_output_tokens=16000,
        max_estimated_cost=Decimal(0),
        input_cost_per_million=Decimal(0),
        output_cost_per_million=Decimal(0),
    )
    first = DurableRoleRunner(
        store, "offline-workspace", valid.content_digest, RoleRecordings(valid), budget
    )
    output = first.run("requirements_analyst", "untrusted input", ServerPolicy(), Analysis)
    empty = ScriptedProvider(())
    second = DurableRoleRunner(store, "offline-workspace", valid.content_digest, empty, budget)
    assert second.run("requirements_analyst", "untrusted input", ServerPolicy(), Analysis) == output
    assert second.receipts == first.receipts
    assert empty.requests == []
