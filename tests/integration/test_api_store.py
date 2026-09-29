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
from agentic_product_ops.services.drafting import load_fixture


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
