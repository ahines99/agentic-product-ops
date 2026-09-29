import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from agentic_product_ops.adapters.identity.vault import SecretVault
from agentic_product_ops.adapters.linear.oauth import LinearOAuth
from agentic_product_ops.adapters.persistence.store import Store, artifacts, engine, metadata
from agentic_product_ops.policies.validation import PolicyError


@pytest.fixture
def storage(tmp_path):
    db = engine(f"sqlite:///{tmp_path / 'secrets.db'}", testing=True)
    metadata.create_all(db)
    store = Store(db)
    keys = {"key-1": secrets.token_bytes(32), "key-2": secrets.token_bytes(32)}
    yield store, keys
    db.dispose()


def test_authenticated_secret_rotation_and_wrong_binding(storage):
    store, keys = storage
    vault = SecretVault(store, keys, "key-1")
    secret = SecretStr(secrets.token_urlsafe(32))
    with store.database.begin() as conn:
        vault.put(conn, "workspace", "linear-account", 1, secret)
    assert vault.get("workspace", "linear-account") == secret
    with pytest.raises(ValueError, match="authentication"):
        SecretVault(store, {"wrong": secrets.token_bytes(32)}, "wrong").get(
            "workspace", "linear-account"
        )
    rotated = SecretVault(store, keys, "key-2")
    rotated.rotate("workspace", "linear-account")
    assert store.get("workspace", "sealed_secret", "linear-account")["revision"] == 2
    assert (
        SecretVault(store, {"key-2": keys["key-2"]}, "key-2").get("workspace", "linear-account")
        == secret
    )
    with store.database.begin() as conn:
        record = store.get("workspace", "sealed_secret", "linear-account", 2, connection=conn)
        store.put(conn, "workspace", "sealed_secret", "swapped", 2, record)
    with pytest.raises(ValueError, match="authentication"):
        rotated.get("workspace", "swapped")


@pytest.mark.parametrize("fault", [None, "timeout", "scope", "replay", "session", "expired"])
def test_pkce_single_use_state_encrypted_tokens_and_rotation(storage, fault):
    store, keys = storage
    vault = SecretVault(store, keys, "key-1")
    access, refresh, authorization_code = (secrets.token_urlsafe(32) for _ in range(3))
    calls = []
    now = [datetime.now(UTC)]

    def handler(request):
        calls.append(parse_qs(request.content.decode()))
        assert request.url == "https://api.linear.app/oauth/token"
        if fault == "timeout":
            raise httpx.ReadTimeout("do not echo secret")
        return httpx.Response(
            200,
            json={
                "access_token": access,
                "refresh_token": refresh,
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "read write" if fault == "scope" else "read issues:create",
            },
        )

    oauth = LinearOAuth(
        store,
        vault,
        workspace="workspace",
        client_id="configured-app",
        redirect_uri="https://app.example/callback",
        administrators=("operator",),
        transport=httpx.MockTransport(handler),
        clock=lambda: now[0],
    )
    url = oauth.begin(administrator="operator", session_id="session-1")
    query = parse_qs(urlsplit(url).query)
    assert query["actor"] == ["app"] and query["code_challenge_method"] == ["S256"]
    state = query["state"][0]
    session = "other-session" if fault == "session" else "session-1"
    if fault == "expired":
        now[0] += timedelta(minutes=11)
    arguments = dict(
        administrator="operator", session_id=session, state=state, code=authorization_code
    )
    if fault in {"timeout", "scope", "session", "expired"}:
        with pytest.raises(PolicyError):
            oauth.exchange(**arguments)
        if fault in {"timeout", "scope"}:
            with pytest.raises(PolicyError, match="consumed"):
                oauth.exchange(**arguments)
            assert len(calls) == 1
        else:
            assert not calls
    else:
        reference = oauth.exchange(**arguments)
        verifier = calls[0]["code_verifier"][0]
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        assert query["code_challenge"] == [expected]
        assert (
            json.loads(vault.get("workspace", reference).get_secret_value())["access_token"]
            == access
        )
        with pytest.raises(PolicyError, match="consumed"):
            oauth.exchange(**arguments)
        assert len(calls) == 1
        if fault is None:
            oauth.refresh(reference, administrator="operator")
            assert calls[1]["grant_type"] == ["refresh_token"]
            assert store.get("workspace", "sealed_secret", reference)["revision"] == 2
    with store.database.connect() as conn:
        stored = "\n".join(conn.execute(select(artifacts.c.payload)).scalars())
    assert all(value not in stored for value in (access, refresh, authorization_code))
    assert "verifier" not in stored
