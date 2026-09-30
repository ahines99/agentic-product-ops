"""Recovery after expiry: stranded intents, read-only reconciliation and approval renewal."""

import json
import secrets
from datetime import datetime, timedelta

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from pydantic import SecretStr

from agentic_product_ops.adapters.linear.native_graphql import NativeGraphQLAdapter
from agentic_product_ops.api.app import TestAuthenticator, create_app
from agentic_product_ops.domain.contracts import SpecificationApproval
from agentic_product_ops.pilot.config import PilotSettings
from agentic_product_ops.pilot.runtime import PilotRuntime
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy
from agentic_product_ops.services.authority import Authority
from agentic_product_ops.services.native_publication import NativePublisher
from agentic_product_ops.services.publication_state import publication_state
from agentic_product_ops.services.signed_handoff import (
    dispatch_approval_id,
    export_signed_handoff,
)
from agentic_product_ops.workflows.lifecycle import EDGES, State
from tests.integration.test_native_publication import LinearRecording, adapter
from tests.integration.test_native_publication import reviewed as reviewed

WORKSPACE = "offline-workspace"


def state(store, spec, tick):
    return publication_state(store, WORKSPACE, str(spec.specification_id), tick[0])


def reachable(start):
    seen, frontier = {start}, [start]
    while frontier:
        for target in EDGES.get(frontier.pop(), ()):
            if target not in seen:
                seen.add(target)
                frontier.append(target)
    return seen


def decide(store, authority, plan, spec, tick, monkeypatch, *, expect=200):
    """Approve the same exact revision again through the authenticated API at the test clock."""

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return tick[0]

    monkeypatch.setattr("agentic_product_ops.api.app.datetime", Clock)
    token = secrets.token_urlsafe(32)
    app = create_app(
        store,
        authenticator=TestAuthenticator({token: authority.resolve_subject("person")}, testing=True),
        authority=authority,
        linear_scope=plan.scope,
    )
    with TestClient(app) as client:
        response = client.post(
            f"/v1/specifications/{spec.specification_id}/approve",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": secrets.token_hex(8)},
            json={
                "revision": spec.revision,
                "content_digest": spec.content_digest,
                "plan_digest": plan.content_digest,
            },
        )
        assert response.status_code == expect, response.text
        observed = client.get(
            f"/v1/specifications/{spec.specification_id}/state",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert observed.json()["source"] == "durable_records"
        return response.json()


def export(store, authority, spec, approval, tick):
    return export_signed_handoff(
        store,
        authority,
        ServerPolicy(),
        specification_id=str(spec.specification_id),
        approval_id=str(approval.approval_id),
        issuer="product-ops-test",
        key_id="key-1",
        signing_key=Ed25519PrivateKey.generate(),
        now=tick[0] + timedelta(seconds=1),
    )


@pytest.mark.parametrize("reviewed", ["handoff"], indirect=True)
def test_stranded_intent_is_dispatched_only_under_a_renewed_approval(reviewed, monkeypatch):
    store, authority, spec, plan, approval, tick = reviewed
    assert state(store, spec, tick) == State.APPROVED
    recording = LinearRecording(plan, authority, tick, "expired_before")
    provider = adapter(plan, recording)
    try:
        publisher = NativePublisher(store, provider, authority, lambda: tick[0])
        # Expiry during preflight reserves an intent but never acquires dispatch authority.
        assert publisher.publish(spec, plan, approval, ServerPolicy())[-1].status == "UNKNOWN"
        assert not recording.mutations
        assert state(store, spec, tick) == State.LINEAR_PUBLISHING
        with pytest.raises(PolicyError, match="expired"):
            publisher.publish(spec, plan, approval, ServerPolicy())
        # Reconciliation has nothing to observe and cannot turn an intent into a write.
        assert publisher.reconcile(spec, plan, ServerPolicy())[-1].status == "UNKNOWN"
        assert not recording.mutations

        renewed = decide(store, authority, plan, spec, tick, monkeypatch)
        assert renewed["renewal"] == 1
        # A second approval inside the renewed window stays a conflict.
        decide(store, authority, plan, spec, tick, monkeypatch, expect=409)
        fresh = SpecificationApproval.model_validate_json(json.dumps(renewed["approval"]))
        with pytest.raises(PolicyError):
            publisher.publish(spec, plan, approval, ServerPolicy())  # superseded approval
        recording.fault = None
        result = publisher.publish(spec, plan, fresh, ServerPolicy())
        assert all(r.status == "SUCCEEDED" for r in result)
        assert len(recording.mutations) == len(plan.operations)
        assert state(store, spec, tick) == State.PUBLISHED
        export(store, authority, spec, fresh, tick)
        assert state(store, spec, tick) == State.HANDOFF_READY
    finally:
        provider.close()


@pytest.mark.parametrize("reviewed", ["handoff", None], indirect=True)
def test_lost_response_is_reconciled_read_only_after_expiry(reviewed, monkeypatch):
    store, authority, spec, plan, approval, tick = reviewed
    recording = LinearRecording(plan, authority, tick, "timeout")
    provider = adapter(plan, recording)
    observed = [state(store, spec, tick)]
    try:
        publisher = NativePublisher(store, provider, authority, lambda: tick[0])
        assert publisher.publish(spec, plan, approval, ServerPolicy())[-1].status == "UNKNOWN"
        assert len(recording.mutations) == 1
        observed.append(state(store, spec, tick))
        assert observed[-1] == State.RECONCILIATION_REQUIRED
        tick[0] += timedelta(minutes=31)
        with pytest.raises(PolicyError, match="expired"):
            publisher.publish(spec, plan, approval, ServerPolicy())

        # A reconciling adapter cannot send a mutation even with the same credential.
        reader = NativeGraphQLAdapter(
            plan.scope,
            token=SecretStr("mock-only"),
            token_kind="api_key",  # noqa: S106
            scopes=("read", "write"),
            transport=httpx.MockTransport(recording),
        )
        reader.allow_mutations = False
        try:
            receipts = NativePublisher(store, reader, authority, lambda: tick[0]).reconcile(
                spec, plan, ServerPolicy()
            )
        finally:
            reader.close()
        assert [r.status for r in receipts] == ["SUCCEEDED"] and len(recording.mutations) == 1
        observed.append(state(store, spec, tick))

        if len(plan.operations) == 1:
            # Reconciliation completed the publication under the original, now expired approval.
            assert observed[-1] == State.PUBLISHED
            decide(store, authority, plan, spec, tick, monkeypatch, expect=409)
            assert dispatch_approval_id(store, WORKSPACE, plan) == str(approval.approval_id)
            export(store, authority, spec, approval, tick)
            observed.append(state(store, spec, tick))
            assert observed[-1] == State.HANDOFF_READY
        else:
            renewed = decide(store, authority, plan, spec, tick, monkeypatch)
            fresh = SpecificationApproval.model_validate_json(json.dumps(renewed["approval"]))
            result = publisher.publish(spec, plan, fresh, ServerPolicy())
            assert all(r.status == "SUCCEEDED" for r in result)
            assert len(recording.mutations) == len(plan.operations)  # nothing sent twice
            observed.append(state(store, spec, tick))
            assert observed[-1] == State.PUBLISHED
            # Writes span two approvals; the single-approval handoff contract holds it.
            with pytest.raises(PolicyError, match="one approval"):
                dispatch_approval_id(store, WORKSPACE, plan)
        # Every sampled state is reachable from the previous one in the declared graph.
        for before, after in zip(observed, observed[1:], strict=False):
            assert after in reachable(before)
    finally:
        provider.close()


def test_absent_object_stays_unknown_and_is_never_recreated(reviewed):
    store, authority, spec, plan, approval, tick = reviewed
    recording = LinearRecording(plan, authority, tick, "missing")
    provider = adapter(plan, recording)
    try:
        publisher = NativePublisher(store, provider, authority, lambda: tick[0])
        publisher.publish(spec, plan, approval, ServerPolicy())
        for _ in range(2):
            assert publisher.reconcile(spec, plan, ServerPolicy())[-1].status == "UNKNOWN"
        assert len(recording.mutations) == 1
        assert state(store, spec, tick) == State.RECONCILIATION_REQUIRED
        with pytest.raises(PolicyError, match="unrecorded"):
            publisher.reconcile(
                spec, plan.model_copy(update={"specification_digest": "0" * 64}), ServerPolicy()
            )
    finally:
        provider.close()


@pytest.mark.parametrize("reviewed", ["handoff"], indirect=True)
def test_incomplete_publication_cannot_be_handed_off(reviewed):
    store, authority, spec, plan, approval, tick = reviewed
    recording = LinearRecording(plan, authority, tick, "timeout")
    provider = adapter(plan, recording)
    try:
        NativePublisher(store, provider, authority, lambda: tick[0]).publish(
            spec, plan, approval, ServerPolicy()
        )
    finally:
        provider.close()
    with pytest.raises(PolicyError, match="complete publication"):
        export(store, authority, spec, approval, tick)
    assert state(store, spec, tick) == State.RECONCILIATION_REQUIRED


def test_rejection_and_cancellation_are_terminal_derived_states(reviewed, monkeypatch):
    store, authority, spec, plan, approval, tick = reviewed
    tick[0] += timedelta(minutes=31)
    assert state(store, spec, tick) == State.EXPIRED
    with store.database.begin() as conn:
        store.lock_specification(conn, WORKSPACE, str(spec.specification_id))
        from sqlalchemy import update

        from agentic_product_ops.adapters.persistence.store import controls

        conn.execute(
            update(controls)
            .where(controls.c.specification_id == str(spec.specification_id))
            .values(cancelled=1)
        )
    assert state(store, spec, tick) == State.CANCELLED
    decide(store, authority, plan, spec, tick, monkeypatch, expect=403)


def test_wire_gate_refuses_undeclared_or_unscoped_mutations():
    sent = []

    def respond(request):
        sent.append(request)
        return httpx.Response(200, json={"data": {}})

    def build(scopes):
        from tests.integration.test_native_publication import LinearScope, ProviderBinding, uuid4

        return NativeGraphQLAdapter(
            LinearScope(
                organization_id=uuid4(),
                actor_id=uuid4(),
                teams=(ProviderBinding(local_id="product", provider_id=uuid4()),),
            ),
            token=SecretStr("mock-only"),
            token_kind="api_key",  # noqa: S106
            scopes=scopes,
            transport=httpx.MockTransport(respond),
        )

    reader, writer = build(("read",)), build(("read", "write"))
    try:
        document = 'mutation Sneaky { issueDelete(id: "x") { success } }'
        for client, query, write in [
            (reader, document, False),  # a read call carrying a mutation
            (reader, document, True),  # declared, but no write-capable scope
            (writer, document, False),  # capable, but not declared by the caller
            (writer, "query Fine { viewer { id } }", True),  # declared write that is not one
            (writer, "query A { viewer { id } } mutation B { x }", False),
        ]:
            with pytest.raises(PolicyError, match="explicit write authority"):
                client._query(query, {}, write=write)
        writer.allow_mutations = False
        with pytest.raises(PolicyError, match="explicit write authority"):
            writer._query(document, {}, write=True)
        assert not sent
    finally:
        reader.close()
        writer.close()


def test_grant_renewal_stales_old_approvals_and_revocation_is_permanent(reviewed, tmp_path):
    store, _, spec, plan, approval, tick = reviewed
    runtime = PilotRuntime.__new__(PilotRuntime)
    runtime.store, runtime.policy = store, ServerPolicy()
    runtime.authority = Authority(
        store,
        workspace=WORKSPACE,
        issuer="https://identity.example",
        administrators=("offline-reviewer",),
        clock=lambda: tick[0],
    )
    runtime.settings = PilotSettings(
        workspace=WORKSPACE,
        operator="offline-reviewer",
        subject="person",
        database_url="postgresql+psycopg://postgres@127.0.0.1/product_ops_pilot",
        linear_scope=plan.scope,
        linear_key_file=str(tmp_path / "unused-linear.env"),
        anthropic_key_file=str(tmp_path / "unused.env"),
        spend_authorization="mock-only",
        maximum_spend="10",
    )
    with pytest.raises(PolicyError, match="30 days"):
        runtime.renew_grant(31)
    before = runtime.authority.resolve_subject("person")
    assert runtime.renew_grant(7)["revision"] == 2
    after = runtime.authority.resolve_subject("person")
    assert after.roles == before.roles and after.grant_digest != before.grant_digest
    recording = LinearRecording(plan, runtime.authority, tick)
    provider = adapter(plan, recording)
    try:
        with pytest.raises(PolicyError, match="stale"):
            NativePublisher(store, provider, runtime.authority, lambda: tick[0]).publish(
                spec, plan, approval, ServerPolicy()
            )
        assert not recording.mutations
    finally:
        provider.close()
    assert runtime.revoke("actor", "offline-reviewer") == {"revoked": "actor"}
    assert runtime.authority.resolve_subject("person") is None
    with pytest.raises(PolicyError, match="revoked"):
        runtime.renew_grant(7)


def test_intake_role_and_unconfigured_reconciliation(tmp_path):
    from uuid import uuid4

    from agentic_product_ops.adapters.persistence.store import Store, engine, metadata
    from agentic_product_ops.api.app import Principal

    db = engine(f"sqlite:///{tmp_path / 'roles.db'}", testing=True)
    metadata.create_all(db)
    tokens = {role: secrets.token_urlsafe(32) for role in ("reader", "product_approver")}
    app = create_app(
        Store(db),
        authenticator=TestAuthenticator(
            {
                token: Principal(actor_id="offline-reviewer", workspace_id=WORKSPACE, roles=(role,))
                for role, token in tokens.items()
            },
            testing=True,
        ),
    )
    try:
        with TestClient(app) as client:
            reader = {"Authorization": "Bearer " + tokens["reader"], "Idempotency-Key": "a"}
            response = client.post("/v1/intakes", headers=reader, json={"source": "untrusted"})
            assert response.status_code == 403
            approver = {"Authorization": "Bearer " + tokens["product_approver"]}
            identifier = uuid4()
            assert (
                client.post(f"/v1/specifications/{identifier}/reconcile", headers=approver)
            ).status_code == 503
            assert (
                client.get(f"/v1/specifications/{identifier}/state", headers=approver)
            ).status_code == 404
            created = client.post(
                "/v1/intakes",
                headers={**approver, "Idempotency-Key": "b"},
                json={"source": "untrusted"},
            )
            assert created.status_code == 201
            state = client.get(
                f"/v1/specifications/{created.json()['specification_id']}/state", headers=approver
            )
            assert state.json()["state"] == "PRE_DECISION_WORKFLOW"
    finally:
        db.dispose()


class InterleavedProvider:
    """Deterministic interleaving: another publisher runs between this one's check and guard."""

    mode = "mock_transport"
    last_request_id = None

    def __init__(self, scope, sends, name, before=None, fail_before_guard=False):
        self.scope, self.sends, self.name = scope, sends, name
        self.before, self.fail_before_guard = before, fail_before_guard

    def create(self, operation, guard):
        if self.fail_before_guard:
            raise RuntimeError("preflight failed")
        if self.before:
            hook, self.before = self.before, None
            hook()
        guard()
        self.sends.append((self.name, operation.operation_key))
        return str(operation.target_id)

    def reconcile(self, operation):
        return None


@pytest.mark.parametrize("reviewed", ["handoff"], indirect=True)
def test_concurrent_publishers_never_both_dispatch_a_stranded_intent(reviewed):
    store, authority, spec, plan, approval, tick = reviewed
    sends = []

    def publisher(provider):
        return NativePublisher(store, provider, authority, lambda: tick[0])

    # A frozen clock gives both publishers byte-identical dispatch-authority payloads.
    publisher(InterleavedProvider(plan.scope, sends, "seed", fail_before_guard=True)).publish(
        spec, plan, approval, ServerPolicy()
    )
    assert not sends

    def second():
        publisher(InterleavedProvider(plan.scope, sends, "B")).publish(
            spec, plan, approval, ServerPolicy()
        )

    result = publisher(InterleavedProvider(plan.scope, sends, "A", before=second)).publish(
        spec, plan, approval, ServerPolicy()
    )
    first = plan.operations[0].operation_key
    assert [name for name, key in sends if key == first] == ["B"]
    assert result[0].status == "UNKNOWN"  # the loser holds; it never sends
