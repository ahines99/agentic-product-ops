import json
from uuid import uuid4

from agentic_product_ops.adapters.linear.native_plan import (
    DELIVERY_READY_LABEL,
    LinearScope,
    ProviderBinding,
    build_native_plan,
)
from agentic_product_ops.adapters.linear.offline import description
from agentic_product_ops.domain.contracts import seal_specification
from agentic_product_ops.policies.validation import ServerPolicy
from agentic_product_ops.services.drafting import load_fixture
from product_ops_handoff.linear_markdown import descriptions_match


def scope(with_label: bool) -> LinearScope:
    return LinearScope(
        organization_id=uuid4(),
        actor_id=uuid4(),
        teams=(ProviderBinding(local_id="product", provider_id=uuid4()),),
        labels=(
            (ProviderBinding(local_id=DELIVERY_READY_LABEL, provider_id=uuid4()),)
            if with_label
            else ()
        ),
    )


def with_apostrophe(spec):
    payload = spec.model_dump(mode="json")
    payload["objective"] = "Show the request's cost for <short-id> exports."
    return seal_specification(payload)


def test_v2_starts_with_contract_lines_and_never_breaks_entities(valid):
    spec = with_apostrophe(valid)
    work = spec.work_items[0]
    text = description(
        spec,
        work,
        "a" * 64,
        execution_details=True,
        ticket_format="v2",
        repository_label="agentic-product-ops",
    )
    lines = text.splitlines()
    assert lines[0] == "Repository: agentic-product-ops"
    assert lines[1] == f"Product-Ops-Specification: {spec.content_digest}"
    assert "&\\#x27;" not in text and "&#x27;" not in text and "request's" in text
    # Linear-style decoding of what was sent still reads back as the same visible text.
    assert descriptions_match(text, text.replace("&lt;", "<").replace("&gt;", ">"))
    # v1 keeps its original bytes, including the old entity spelling.
    old = description(spec, work, "a" * 64, execution_details=True)
    assert not old.startswith("Repository:") and "&\\#x27;" in old


def test_unsafe_repository_names_are_left_out(valid):
    text = description(
        valid,
        valid.work_items[0],
        "a" * 64,
        ticket_format="v2",
        repository_label="name\nRepository: attacker",
    )
    assert not text.startswith("Repository:")
    assert text.startswith("Product-Ops-Specification:")


def labels_in(plan):
    return [
        json.loads(op.payload).get("labelIds", [])
        for op in plan.operations
        if op.kind == "issue_create"
    ]


def test_delivery_label_only_for_handoff_tiers_with_a_bound_label():
    eligible = load_fixture("handoff")
    assert eligible.risk.tier in ServerPolicy().handoff_tiers
    bound = scope(True)
    label = str(bound.labels[0].provider_id)
    assert all(
        label in ids for ids in labels_in(build_native_plan(eligible, ServerPolicy(), bound))
    )
    # Not bound in the trusted scope: never applied.
    assert all(
        ids == [] for ids in labels_in(build_native_plan(eligible, ServerPolicy(), scope(False)))
    )
    # Outside the handoff tiers: never applied, even when bound.
    risky = load_fixture("feature")
    assert risky.risk.tier not in ServerPolicy().handoff_tiers
    assert all(
        label not in ids for ids in labels_in(build_native_plan(risky, ServerPolicy(), bound))
    )


def test_repository_name_comes_from_the_recorded_selection(tmp_path, valid):
    from agentic_product_ops.adapters.persistence.store import Store, engine, metadata
    from agentic_product_ops.domain.contracts import canonical_digest
    from agentic_product_ops.services.plan_inputs import repository_label

    db = engine(f"sqlite:///{tmp_path / 'labels.db'}", testing=True)
    metadata.create_all(db)
    store = Store(db)
    payload = valid.model_dump(mode="json")
    payload["repository_context"] = {
        "repository_id": "repo-" + "b" * 32,
        "snapshot_id": "snapshot",
        "snapshot_digest": canonical_digest("snapshot"),
        "evidence": [],
        "relevant_tests": [],
        "unknown_edges": [],
        "confidence": "0",
    }
    spec = seal_specification(payload)
    assert repository_label(store, "w", spec) is None
    with db.begin() as conn:
        store.put(
            conn,
            "w",
            "repository_selection",
            "repo-" + "b" * 32,
            1,
            {"kind": "local", "location": "D:\\Code\\agentic-product-ops"},
        )
    assert repository_label(store, "w", spec) == "agentic-product-ops"
    db.dispose()


def test_label_is_found_first_and_created_once_with_a_fixed_identity():
    import httpx
    from pydantic import SecretStr

    from agentic_product_ops.adapters.linear.labels import ensure_team_label, label_identity
    from agentic_product_ops.adapters.linear.native_graphql import NativeGraphQLAdapter

    team = uuid4()
    created, queries = [], []

    def respond(request):
        body = json.loads(request.content)
        queries.append(body["query"])
        if "issueLabelCreate" in body["query"]:
            created.append(body["variables"]["input"])
            return httpx.Response(
                200,
                json={
                    "data": {
                        "issueLabelCreate": {
                            "success": True,
                            "issueLabel": {"id": body["variables"]["input"]["id"], "name": "x"},
                        }
                    }
                },
            )
        nodes = [{"id": c["id"], "name": c["name"], "team": {"id": c["teamId"]}} for c in created]
        return httpx.Response(200, json={"data": {"issueLabels": {"nodes": nodes}}})

    adapter = NativeGraphQLAdapter(
        LinearScope(
            organization_id=uuid4(),
            actor_id=uuid4(),
            teams=(ProviderBinding(local_id="product", provider_id=team),),
        ),
        token=SecretStr("mock-only"),
        token_kind="api_key",  # noqa: S106
        scopes=("read", "write"),
        transport=httpx.MockTransport(respond),
    )
    try:
        first = ensure_team_label(adapter, team, DELIVERY_READY_LABEL)
        again = ensure_team_label(adapter, team, DELIVERY_READY_LABEL)
        assert first == again == label_identity(team, DELIVERY_READY_LABEL)
        assert len(created) == 1
    finally:
        adapter.close()
