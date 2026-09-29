import json
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from agentic_product_ops.adapters.persistence.store import (
    Conflict,
    Store,
    artifacts,
    audits,
    engine,
    metadata,
)
from agentic_product_ops.api.app import Principal, TestAuthenticator, create_app
from agentic_product_ops.policies.validation import ServerPolicy
from agentic_product_ops.services.drafting import load_fixture
from agentic_product_ops.services.durable_analysis import analyze_specification


@pytest.fixture
def application(tmp_path):
    database = engine(f"sqlite:///{tmp_path / 'records.db'}", testing=True)
    metadata.create_all(database)
    store = Store(database)
    token = secrets.token_urlsafe(32)
    principal = Principal(
        actor_id="offline-reviewer", workspace_id="offline-workspace", roles=("product_approver",)
    )
    app = create_app(store, authenticator=TestAuthenticator({token: principal}, testing=True))
    with TestClient(app) as client:
        client.headers["Authorization"] = f"Bearer {token}"
        yield client, store
    database.dispose()


def intake(client, name="feature", key="intake-1"):
    response = client.post(
        "/v1/intakes",
        headers={"Idempotency-Key": key},
        json={"source": load_fixture(name).source_statements[0].text},
    )
    assert response.status_code == 201, response.text
    return response.json()["specification_id"]


def analyze(store, identifier):
    spec = store.get("offline-workspace", "specification", identifier)
    return analyze_specification(
        store, "offline-workspace", identifier, spec["content_digest"], ServerPolicy()
    )


def test_default_denies_and_never_ready():
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        assert client.post("/v1/intakes", json={"source": "untrusted"}).status_code == 401


def test_idempotent_intake_and_conflict(application):
    client, store = application
    identifier = intake(client)
    assert intake(client) == identifier
    response = client.post(
        "/v1/intakes", headers={"Idempotency-Key": "intake-1"}, json={"source": "different"}
    )
    assert response.status_code == 409
    with store.database.connect() as conn:
        assert len(conn.execute(select(audits)).all()) == 1
        assert len(conn.execute(select(artifacts)).all()) == 2
    # Database record persists when a new Store instance is created.
    assert (
        Store(store.database).get("offline-workspace", "specification", identifier)["revision"] == 1
    )


def test_approval_auth_bound_and_stale_denied(application):
    client, store = application
    identifier = intake(client)
    analyze(store, identifier)
    spec = client.get(f"/v1/specifications/{identifier}").json()
    body = {"revision": spec["revision"], "content_digest": spec["content_digest"]}
    result = client.post(
        f"/v1/specifications/{identifier}/approve",
        json=body,
        headers={"Idempotency-Key": "approval-1"},
    )
    assert result.status_code == 200, result.text
    approval = result.json()["approval"]
    assert approval["actor_id"] == "offline-reviewer"
    assert (
        client.post(
            f"/v1/specifications/{identifier}/approve",
            json={**body, "actor_id": "admin"},
            headers={"Idempotency-Key": "bad"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/v1/specifications/{identifier}/approve",
            json={**body, "revision": 10},
            headers={"Idempotency-Key": "stale"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/v1/specifications/{identifier}/publish", headers={"Idempotency-Key": "publish-1"}
        ).status_code
        == 503
    )


def test_clarification_new_revision_and_gate(application):
    client, store = application
    identifier = intake(client, "ambiguous")
    before = client.get(f"/v1/specifications/{identifier}").json()
    body = {
        "revision": 1,
        "content_digest": before["content_digest"],
        "question_id": "Q1",
        "answer": "At most 10,000 rows.",
    }
    result = client.post(
        f"/v1/specifications/{identifier}/clarifications",
        json=body,
        headers={"Idempotency-Key": "clarify-1"},
    )
    assert result.status_code == 200, result.text
    after = client.get(f"/v1/specifications/{identifier}").json()
    assert after["revision"] == 2
    assert store.get("offline-workspace", "specification", identifier, 1) == before
    assert (
        client.post(
            f"/v1/specifications/{identifier}/approve",
            json={"revision": 2, "content_digest": after["content_digest"]},
            headers={"Idempotency-Key": "hold"},
        ).status_code
        == 403
    )


def test_request_bounds_and_redacted_validation(application):
    client, _ = application
    oversized = client.post(
        "/v1/intakes", content=b"a" * 200_001, headers={"Idempotency-Key": "large"}
    )
    assert oversized.status_code == 413
    response = client.post(
        "/v1/intakes",
        json={"source": "x", "token": "private marker"},
        headers={"Idempotency-Key": "extra"},
    )
    assert response.status_code == 422
    assert "private marker" not in response.text
    assert (
        client.patch("/v1/specifications/anything", json={"state": "APPROVED"}).status_code == 405
    )
    assert "Bearer" not in json.dumps(response.json())


def test_stored_artifact_integrity_is_rechecked(application):
    client, store = application
    identifier = intake(client)
    # SQLite deliberately has no production immutability trigger; simulate storage corruption.
    with store.database.begin() as conn:
        conn.execute(update(artifacts).values(payload='{"tampered": true}'))
    with pytest.raises(Conflict, match="integrity"):
        store.get("offline-workspace", "specification", identifier)


def test_decision_cannot_be_contradicted_and_identity_is_server_owned(application):
    client, store = application
    identifier = intake(client)
    analyze(store, identifier)
    spec = client.get(f"/v1/specifications/{identifier}").json()
    body = {"revision": 1, "content_digest": spec["content_digest"]}
    assert (
        client.post(
            f"/v1/specifications/{identifier}/approve",
            json=body,
            headers={"Idempotency-Key": "decision-one"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/v1/specifications/{identifier}/reject",
            json=body,
            headers={"Idempotency-Key": "contradiction"},
        ).status_code
        == 409
    )
    outsider = Principal(
        actor_id="offline-reviewer", workspace_id="other", roles=("product_approver",)
    )
    token = secrets.token_urlsafe(32)
    app = create_app(store, authenticator=TestAuthenticator({token: outsider}, testing=True))
    with TestClient(app) as stranger:
        assert (
            stranger.get(
                f"/v1/specifications/{identifier}", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 403
        )


def test_approval_requires_review_and_cancellation_blocks_future_commands(application):
    client, store = application
    identifier = intake(client)
    spec = client.get(f"/v1/specifications/{identifier}").json()
    body = {"revision": 1, "content_digest": spec["content_digest"]}
    assert (
        client.post(
            f"/v1/specifications/{identifier}/approve",
            json=body,
            headers={"Idempotency-Key": "too-early"},
        ).status_code
        == 403
    )
    analyze(store, identifier)
    for _ in range(2):
        response = client.post(
            f"/v1/specifications/{identifier}/cancel",
            json=body,
            headers={"Idempotency-Key": "cancel-once"},
        )
        assert response.status_code == 200
        assert response.json()["cancelled"] is True
    assert Store(store.database).cancelled("offline-workspace", identifier)
    assert (
        client.post(
            f"/v1/specifications/{identifier}/approve",
            json=body,
            headers={"Idempotency-Key": "after-cancel"},
        ).status_code
        == 403
    )


def test_clarification_reanalysis_is_queued_and_stays_held(application):
    client, store = application
    identifier = intake(client, "ambiguous")
    assert analyze(store, identifier).state == "AWAITING_CLARIFICATION"
    spec = client.get(f"/v1/specifications/{identifier}").json()
    result = client.post(
        f"/v1/specifications/{identifier}/clarifications",
        json={
            "revision": 1,
            "content_digest": spec["content_digest"],
            "question_id": "Q1",
            "answer": "10,000 rows",
        },
        headers={"Idempotency-Key": "answer"},
    )
    assert result.status_code == 200
    assert result.json()["workflow"] == "queued"
    assert any(row["workflow_id"].endswith("-r2") for row in store.pending_workflows())
    revised = analyze(store, identifier)
    assert revised.state == "AWAITING_CLARIFICATION"
    assert revised.analysis.unresolved_questions[0].resolution == "10,000 rows"
    review = client.get(f"/v1/specifications/{identifier}/review").json()
    assert review["result"]["state"] == "AWAITING_CLARIFICATION"


def test_allowlisted_repository_snapshot_bound_to_intake(application, tmp_path):
    _, store = application
    repository = tmp_path / "sample"
    repository.mkdir()
    module = repository / "reporting.py"
    module.write_text("def export_report(): pass\n", encoding="utf-8")
    principal = Principal(
        actor_id="offline-reviewer", workspace_id="offline-workspace", roles=("product_approver",)
    )
    token = secrets.token_urlsafe(32)
    app = create_app(
        store,
        authenticator=TestAuthenticator({token: principal}, testing=True),
        repository_roots={"sample-reporting": repository},
    )
    with TestClient(app) as client:
        client.headers["Authorization"] = f"Bearer {token}"
        snapshot = client.get("/v1/repositories/sample-reporting/snapshot")
        assert snapshot.status_code == 200, snapshot.text
        assert client.get("/v1/repositories/unknown/snapshot").status_code == 403
        body = {
            "source": load_fixture("feature").source_statements[0].text,
            "repository_id": "sample-reporting",
            "expected_snapshot_digest": snapshot.json()["digest"],
        }
        result = client.post("/v1/intakes", headers={"Idempotency-Key": "grounded"}, json=body)
        assert result.status_code == 201, result.text
        spec = store.get("offline-workspace", "specification", result.json()["specification_id"])
        assert spec["repository_context"]["snapshot_digest"] == snapshot.json()["digest"]
        module.write_text("def changed(): pass\n", encoding="utf-8")
        assert (
            client.post(
                "/v1/intakes", headers={"Idempotency-Key": "changed"}, json=body
            ).status_code
            == 403
        )
