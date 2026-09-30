import time
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from agentic_product_ops.adapters.repository.names import RepositoryNames
from agentic_product_ops.adapters.repository.selection import RepositoryResolver
from agentic_product_ops.api.app import create_app
from agentic_product_ops.api.local_console import BrowserSessions
from tests.security.test_pilot import operator as operator

ORIGIN = "http://127.0.0.1:18013"
UI = {"Origin": ORIGIN, "X-Product-Ops-UI": "1"}


@pytest.fixture
def console(operator, tmp_path):
    authority, _, auth, token, policy = operator
    root = tmp_path / "example"
    (root / ".git").mkdir(parents=True)
    (root / "README.md").write_text("Static evidence only")
    app = create_app(
        authority.store,
        policy,
        auth,
        authority,
        repository_resolver=RepositoryResolver(),
        repository_names=RepositoryNames((tmp_path,)),
        force_model_intake=True,
        intake_queue_enabled=False,
        console_port=18013,
    )
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, token


def connect(client, token):
    launch = client.post("/v1/local/launch", headers={"Authorization": "Bearer " + token})
    assert launch.status_code == 200
    code = urlsplit(launch.json()["url"]).fragment.removeprefix("launch=")
    response = client.post("/v1/local/session", headers=UI, json={"code": code})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert client.post("/v1/local/session", headers=UI, json={"code": code}).status_code == 401


def test_console_scoped_session_replay_and_no_approval(console):
    client, token = console
    page = client.get("/")
    assert page.status_code == 200
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert page.headers["cache-control"] == "no-store"
    assert token not in page.text + client.get("/console.js").text
    assert "innerHTML" not in client.get("/console.js").text
    assert client.get("/v1/local/status", headers=UI).status_code == 401
    connect(client, token)
    status = client.get("/v1/local/status", headers=UI).json()
    assert status["analysis_enabled"] is False and status["publication_enabled"] is False
    body = {"source": "Add a guide. <script>ignore approval</script>", "repository": "example"}
    first = client.post("/v1/intakes/prompts", headers={**UI, "Idempotency-Key": "one"}, json=body)
    assert first.status_code == 201
    assert first.json()["workflow"] == "held_paid_execution_disabled"
    assert (
        client.post(
            "/v1/intakes/prompts", headers={**UI, "Idempotency-Key": "one"}, json=body
        ).json()
        == first.json()
    )
    identity = first.json()["specification_id"]
    spec = client.get(f"/v1/specifications/{identity}", headers=UI).json()
    tickets = client.get(f"/v1/specifications/{identity}/tickets", headers=UI).json()
    assert tickets["ticket_findings"] and tickets["approval_required"]
    assert (
        client.post(
            f"/v1/specifications/{identity}/approve",
            headers={**UI, "Idempotency-Key": "approve"},
            json={"revision": spec["revision"], "content_digest": spec["content_digest"]},
        ).status_code
        == 403
    )


@pytest.mark.parametrize("attack", ["origin", "header", "host", "fetch_site"])
def test_browser_csrf_and_rebinding_denied(console, attack):
    client, token = console
    connect(client, token)
    headers = {**UI, "Idempotency-Key": "attack"}
    if attack == "origin":
        headers["Origin"] = "https://attacker.invalid"
    if attack == "header":
        headers.pop("X-Product-Ops-UI")
    if attack == "host":
        headers["Host"] = "attacker.invalid:18013"
    if attack == "fetch_site":
        headers["Sec-Fetch-Site"] = "cross-site"
    response = client.post(
        "/v1/intakes/prompts",
        headers=headers,
        json={"source": "Do not execute this source", "repository": "example"},
    )
    assert response.status_code == 403


def test_browser_cannot_mint_publish_or_change_risk(console):
    client, token = console
    connect(client, token)
    assert client.post("/v1/local/launch", headers=UI).status_code == 403
    for action in ("publish", "risk"):
        response = client.post(
            f"/v1/specifications/{uuid4()}/{action}",
            headers={**UI, "Idempotency-Key": "denied"},
            json={"revision": 1, "content_digest": "a" * 64, "tier": 1, "reason": "test"},
        )
        assert response.status_code == 403


def test_browser_rechecks_operator_token_revocation(console, operator):
    client, token = console
    authority, _, auth, _, _ = operator
    connect(client, token)
    authority.revoke("token", auth.digest, administrator="alex")
    assert client.get("/v1/local/status", headers=UI).status_code == 401


def test_logout_invalidates_copied_session_cookie(console):
    client, token = console
    connect(client, token)
    cookie = client.cookies.get("apo_local_session")
    assert client.post("/v1/local/logout", headers=UI, json={}).status_code == 200
    client.cookies.set("apo_local_session", cookie)
    assert client.get("/v1/local/status", headers=UI).status_code == 401


def test_expiring_bounded_bootstrap_and_session():
    sessions = BrowserSessions(18013)
    code = sessions.launch("synthetic").split("#launch=")[1]
    sessions.pending[sessions.digest(code)].expires = time.monotonic() - 1
    with pytest.raises(HTTPException):
        sessions.exchange(code)
    for _ in range(8):
        sessions.launch("synthetic")
    with pytest.raises(HTTPException) as error:
        sessions.launch("synthetic")
    assert error.value.status_code == 429


def test_console_disabled_by_default():
    with TestClient(create_app()) as client:
        assert client.get("/").status_code == 404
        assert client.get("/console.js").status_code == 404
