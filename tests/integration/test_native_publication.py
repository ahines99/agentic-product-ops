import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from agentic_product_ops.adapters.linear.native_graphql import NativeGraphQLAdapter
from agentic_product_ops.adapters.linear.native_plan import (
    LinearScope,
    NativePlan,
    ProviderBinding,
    build_native_plan,
)
from agentic_product_ops.adapters.persistence.encryption import StorageEncryption
from agentic_product_ops.adapters.persistence.store import Missing, Store, engine, metadata
from agentic_product_ops.api.app import TestAuthenticator, create_app
from agentic_product_ops.domain.contracts import (
    SpecificationApproval,
    WorkSpecification,
    seal_specification,
)
from agentic_product_ops.pilot.config import PilotSettings
from agentic_product_ops.pilot.runtime import PilotRuntime
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy
from agentic_product_ops.services.authority import ActorGrant, Authority
from agentic_product_ops.services.durable_analysis import analyze_specification
from agentic_product_ops.services.native_publication import NativePublisher


@pytest.fixture
def reviewed(tmp_path, valid, request):
    if getattr(request, "param", None) == "handoff":
        from agentic_product_ops.services.drafting import load_fixture

        valid = load_fixture("handoff")
    db = engine(f"sqlite:///{tmp_path / 'native.db'}", testing=True)
    metadata.create_all(db)
    yield prepare_reviewed(db, valid)
    db.dispose()


def prepare_reviewed(db, valid, revise=None):
    """Intake, record review and approve an exact native plan through the API."""
    store, tick = (
        Store(db, encryption=StorageEncryption({"test-key": secrets.token_bytes(32)}, "test-key")),
        [datetime.now(UTC)],
    )
    authority = Authority(
        store,
        workspace="offline-workspace",
        issuer="https://identity.example",
        administrators=("operator",),
        clock=lambda: tick[0],
    )
    authority.register(
        ActorGrant(
            workspace_id="offline-workspace",
            actor_id="offline-reviewer",
            issuer="https://identity.example",
            subject="person",
            revision=1,
            roles=("product_approver", "security_approver"),
            team_ids=("product",),
            repository_ids=("sample-reporting",),
            issued_at=tick[0],
            expires_at=tick[0] + timedelta(hours=1),
            enabled=True,
        ),
        administrator="operator",
    )
    scope = LinearScope(
        organization_id=uuid4(),
        actor_id=uuid4(),
        teams=(ProviderBinding(local_id="product", provider_id=uuid4()),),
    )
    token = secrets.token_urlsafe(32)
    app = create_app(
        store,
        authenticator=TestAuthenticator({token: authority.resolve_subject("person")}, testing=True),
        authority=authority,
        linear_scope=scope,
    )
    with TestClient(app) as client:
        client.headers["Authorization"] = f"Bearer {token}"
        intake = client.post(
            "/v1/intakes",
            headers={"Idempotency-Key": "intake"},
            json={"source": valid.source_statements[0].text},
        )
        assert intake.status_code == 201
        identity = intake.json()["specification_id"]
        spec = WorkSpecification.model_validate_json(
            client.get(f"/v1/specifications/{identity}").text
        )
        if revise is not None:
            # Store an edited next revision, as a revision workflow would, before review.
            payload = revise(spec.model_dump(mode="json"))
            payload["revision"] = spec.revision + 1
            spec = seal_specification(payload)
            with store.database.begin() as conn:
                store.put(conn, "offline-workspace", "specification", identity, spec.revision, spec)
        analyze_specification(
            store, "offline-workspace", identity, spec.content_digest, ServerPolicy()
        )
        plan = NativePlan.model_validate_json(
            json.dumps(client.get(f"/v1/specifications/{identity}/plan").json()["plan"])
        )
        body = {"revision": spec.revision, "content_digest": spec.content_digest}
        assert (
            client.post(
                f"/v1/specifications/{identity}/approve",
                headers={"Idempotency-Key": "unseen-plan"},
                json=body,
            ).status_code
            == 409
        )
        response = client.post(
            f"/v1/specifications/{identity}/approve",
            headers={"Idempotency-Key": "approved-plan"},
            json={**body, "plan_digest": plan.content_digest},
        )
        assert response.status_code == 200, response.text
        approval = SpecificationApproval.model_validate_json(
            json.dumps(response.json()["approval"])
        )
    tick[0] = approval.issued_at
    return store, authority, spec, plan, approval, tick


class LinearRecording:
    def __init__(self, plan, authority, tick, fault=None):
        self.plan, self.authority, self.tick, self.fault = plan, authority, tick, fault
        self.objects, self.mutations, self.queries = {}, [], []

    def __call__(self, request):
        body = json.loads(request.content)
        query, variables = body["query"], body["variables"]
        assert request.url == "https://api.linear.app/graphql"
        assert request.headers["Authorization"] == "mock-only"
        self.queries.append(query)
        if "ProductOpsIdentity" in query:
            value = {
                "organization": {"id": str(self.plan.scope.organization_id)},
                "viewer": {"id": str(self.plan.scope.actor_id)},
            }
        elif "ProductOpsTeam" in query:
            if self.fault == "revoked_before":
                self.authority.revoke("actor", "offline-reviewer", administrator="operator")
            elif self.fault == "expired_before":
                self.tick[0] += timedelta(minutes=31)
            value = {
                "team": {
                    "id": variables["id"],
                    "organization": {"id": str(self.plan.scope.organization_id)},
                }
            }
        elif "ProductOpsReconcile" in query:
            field = "issueRelation" if "issueRelation(id" in query else "issue"
            value = {field: self.objects.get(variables["id"])}
        else:
            assert "mutation ProductOpsWrite" in query
            payload = variables["input"]
            self.mutations.append(payload)
            if "issueRelationCreate" in query:
                operation, field = "issueRelationCreate", "issueRelation"
                observed = {
                    "id": payload["id"],
                    "type": payload["type"],
                    "issue": {"id": payload["issueId"]},
                    "relatedIssue": {"id": payload["relatedIssueId"]},
                }
                assert (
                    payload["issueId"] in self.objects and payload["relatedIssueId"] in self.objects
                )
            else:
                operation, field = "issueCreate", "issue"
                observed = {
                    "id": payload["id"],
                    "title": payload["title"],
                    "description": payload["description"],
                    "team": {"id": payload["teamId"]},
                    "project": None,
                    "labels": {"nodes": [], "pageInfo": {"hasNextPage": False}},
                }
            self.objects[payload["id"]] = observed
            if len(self.mutations) == 1 and self.fault in {"timeout", "missing", "content"}:
                if self.fault == "missing":
                    self.objects.clear()
                if self.fault == "content":
                    observed["description"] = "Provider changed the approved content"
                raise httpx.ReadTimeout("simulated lost response")
            if len(self.mutations) == 1 and self.fault == "revoked_after":
                self.authority.revoke("approval", self.approval_id, administrator="operator")
            value = {operation: {"success": True, field: observed}}
        return httpx.Response(
            200, json={"data": value}, headers={"x-request-id": f"request-{len(self.queries)}"}
        )


def adapter(plan, recording):
    return NativeGraphQLAdapter(
        plan.scope,
        token=SecretStr("mock-only"),
        token_kind="api_key",  # noqa: S106 -- enum selecting the credential header format
        scopes=("read", "write"),
        transport=httpx.MockTransport(recording),
    )


@pytest.mark.parametrize("fault", [None, "timeout", "missing", "content"])
def test_native_issues_relations_and_restart_reconciliation(reviewed, fault):
    store, authority, spec, plan, approval, tick = reviewed
    recording = LinearRecording(plan, authority, tick, fault)
    provider = adapter(plan, recording)
    try:
        first = NativePublisher(store, provider, authority, lambda: tick[0]).publish(
            spec, plan, approval, ServerPolicy()
        )
        if fault:
            assert first[-1].status == "UNKNOWN" and len(recording.mutations) == 1
        provider.close()
        provider = adapter(plan, recording)
        result = NativePublisher(store, provider, authority, lambda: tick[0]).publish(
            spec, plan, approval, ServerPolicy()
        )
        if fault in {"missing", "content"}:
            assert result[-1].status == "UNKNOWN" and len(recording.mutations) == 1
        else:
            assert all(r.status == "SUCCEEDED" for r in result)
            assert (
                len(recording.mutations)
                == len(plan.operations)
                == len(spec.work_items) + len(spec.dependencies)
            )
            assert any(operation.kind == "relation_create" for operation in plan.operations)
            NativePublisher(store, provider, authority, lambda: tick[0]).publish(
                spec, plan, approval, ServerPolicy()
            )
            assert len(recording.mutations) == len(plan.operations)
    finally:
        provider.close()


@pytest.mark.parametrize("fault", ["revoked_before", "expired_before", "revoked_after"])
def test_authority_rechecked_after_metadata_and_between_mutations(reviewed, fault):
    store, authority, spec, plan, approval, tick = reviewed
    recording = LinearRecording(plan, authority, tick, fault)
    recording.approval_id = str(approval.approval_id)
    provider = adapter(plan, recording)
    try:
        publisher = NativePublisher(store, provider, authority, lambda: tick[0])
        if fault == "revoked_after":
            with pytest.raises(PolicyError, match="revoked"):
                publisher.publish(spec, plan, approval, ServerPolicy())
            assert len(recording.mutations) == 1
        else:
            assert publisher.publish(spec, plan, approval, ServerPolicy())[0].status == "UNKNOWN"
            assert not recording.mutations
    finally:
        provider.close()


def test_native_relation_budget_and_scope_digest(reviewed):
    _, _, spec, plan, _, _ = reviewed
    with pytest.raises(PolicyError, match="mutation budget"):
        build_native_plan(spec, ServerPolicy(max_mutations=len(spec.work_items)), plan.scope)
    changed = plan.scope.model_copy(update={"actor_id": uuid4()})
    assert build_native_plan(spec, ServerPolicy(), changed).content_digest != plan.content_digest


def test_source_edit_stops_next_mutation(reviewed):
    store, authority, spec, plan, approval, tick = reviewed
    recording = LinearRecording(plan, authority, tick, None)
    provider = adapter(plan, recording)
    checked = []

    def source_guard(identifier):
        checked.append(identifier)
        if recording.mutations:
            raise PolicyError("source changed")

    try:
        result = NativePublisher(
            store, provider, authority, lambda: tick[0], source_guard=source_guard
        ).publish(spec, plan, approval, ServerPolicy())
        assert len(recording.mutations) == 1
        assert checked == [str(spec.specification_id)] * 2
        assert result[-1].status == "UNKNOWN"
    finally:
        provider.close()


def test_pilot_assembly_disabled_then_unknown_reconciliation(reviewed, monkeypatch, tmp_path):
    store, authority, spec, plan, _, tick = reviewed
    credential = tmp_path / "linear.env"
    credential.write_text("LINEAR_API_KEY=mock-only\n", encoding="utf-8")
    runtime = PilotRuntime.__new__(PilotRuntime)
    runtime.store, runtime.authority, runtime.policy = store, authority, ServerPolicy()
    runtime.settings = PilotSettings(
        workspace="offline-workspace",
        subject="person",
        database_url="postgresql+psycopg://postgres@127.0.0.1/product_ops_pilot",
        linear_scope=plan.scope,
        linear_key_file=str(credential),
        anthropic_key_file=str(tmp_path / "unused.env"),
        spend_authorization="mock-only",
        maximum_spend="10",
    )
    recording = LinearRecording(plan, authority, tick, "timeout")

    def factory(*args, **kwargs):
        assert kwargs["token_kind"] == "api_key" and kwargs["allow_mutations"]  # noqa: S105
        return adapter(plan, recording)

    monkeypatch.setattr("agentic_product_ops.pilot.runtime.NativeGraphQLAdapter", factory)
    actor = authority.resolve_subject("person")
    with pytest.raises(PolicyError, match="not enabled"):
        runtime.publish(str(spec.specification_id), actor, "pilot-publish")
    assert not recording.queries
    runtime.settings = runtime.settings.model_copy(update={"allow_publication": True})
    first = runtime.publish(str(spec.specification_id), actor, "pilot-publish")
    assert not first["complete"]
    with pytest.raises(Missing):
        store.get("offline-workspace", "publication", str(spec.specification_id))
    recovered = runtime.publish(str(spec.specification_id), actor, "pilot-publish")
    assert recovered["complete"] and len(recording.mutations) == len(plan.operations)
    assert runtime.publish(str(spec.specification_id), actor, "pilot-publish") == recovered


def test_reviewed_inference_is_approved_and_published_through_the_api(tmp_path, valid):
    def infer(payload):
        payload["requirements"][0]["provenance"] = "safe_inference"
        return payload

    db = engine(f"sqlite:///{tmp_path / 'inferred.db'}", testing=True)
    metadata.create_all(db)
    store, authority, spec, plan, approval, tick = prepare_reviewed(db, valid, infer)
    assert spec.requirements[0].provenance == "safe_inference"
    recording = LinearRecording(plan, authority, tick)
    provider = adapter(plan, recording)
    try:
        result = NativePublisher(store, provider, authority, lambda: tick[0]).publish(
            spec, plan, approval, ServerPolicy()
        )
        assert all(r.status == "SUCCEEDED" for r in result)
        assert len(recording.mutations) == len(plan.operations)
    finally:
        provider.close()
        db.dispose()
