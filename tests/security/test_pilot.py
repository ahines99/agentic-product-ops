import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from agentic_product_ops.adapters.identity.local import LocalOperatorAuthenticator
from agentic_product_ops.adapters.persistence.store import Store, engine, metadata
from agentic_product_ops.adapters.repository.selection import (
    RepositoryResolver,
    RepositorySelection,
)
from agentic_product_ops.api.app import create_app
from agentic_product_ops.pilot.config import PilotSettings, secret_from_env
from agentic_product_ops.policies.validation import ServerPolicy
from agentic_product_ops.services.authority import ActorGrant, Authority


@pytest.fixture
def operator(tmp_path):
    database = engine(f"sqlite:///{tmp_path / 'pilot.db'}", testing=True)
    metadata.create_all(database)
    authority = Authority(
        Store(database),
        workspace="pilot",
        issuer="https://localhost/operator",
        administrators=("alex",),
    )
    now = datetime.now(UTC)
    grant = ActorGrant(
        workspace_id="pilot",
        actor_id="alex",
        issuer=authority.issuer,
        subject="local-user",
        revision=1,
        roles=("product_approver", "security_approver", "intake_reader"),
        team_ids=("product",),
        repository_ids=(),
        allow_any_repository=True,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        enabled=True,
    )
    authority.register(grant, administrator="alex")
    token = secrets.token_urlsafe(48)
    auth = LocalOperatorAuthenticator(authority, token=SecretStr(token), subject=grant.subject)
    policy = ServerPolicy(
        workspace_id="pilot",
        repositories=(),
        allow_any_repository=True,
        approvers=("alex",),
        security_approvers=("alex",),
    )
    yield authority, grant, auth, token, policy
    database.dispose()


def test_live_grant_and_revocation_each_authentication(operator):
    authority, grant, auth, token, _ = operator
    assert auth.authenticate("incorrect") is None
    assert auth.authenticate(token).actor_id == "alex"
    authority.register(
        grant.model_copy(update={"revision": 2, "enabled": False}), administrator="alex"
    )
    assert auth.authenticate(token) is None


def test_token_revocation(operator):
    authority, _, auth, token, _ = operator
    authority.revoke("token", auth.digest, administrator="alex")
    assert auth.authenticate(token) is None


def test_any_repository_still_requires_policy_grant_snapshot_and_no_execution(operator, tmp_path):
    authority, grant, auth, token, policy = operator
    resolver = RepositoryResolver()
    app = create_app(
        authority.store,
        policy,
        auth,
        authority,
        repository_resolver=resolver,
        force_model_intake=True,
    )
    selections = []
    for name in ("first", "second"):
        root = tmp_path / name
        (root / ".git").mkdir(parents=True)
        (root / "code.py").write_text(
            "raise RuntimeError('must never execute')\n", encoding="utf-8"
        )
        (root / ".local").mkdir()
        (root / ".local" / "private.py").write_text("PRIVATE = 'never send'", encoding="utf-8")
        selections.append(RepositorySelection(kind="local", location=str(root)))
    assert selections[0].repository_id() != selections[1].repository_id()
    with TestClient(app) as client:
        for selected in selections:
            snapshot = resolver(selected)
            assert [file.path for file in snapshot.files] == ["code.py"]
            body = {
                "source": "Document a small feature",
                "repository": selected.model_dump(mode="json"),
                "expected_snapshot_digest": snapshot.digest,
            }

            def post(body=body):
                return client.post(
                    "/v1/intakes",
                    json=body,
                    headers={
                        "Authorization": "Bearer " + token,
                        "Idempotency-Key": str(uuid4()),
                    },
                )

            result = post()
            assert result.status_code == 201
            assert result.json()["mode"] == "unrecognized_input"
            body["expected_snapshot_digest"] = "a" * 64
            assert post().status_code == 403
        authority.register(
            grant.model_copy(update={"revision": 2, "allow_any_repository": False}),
            administrator="alex",
        )
        body.pop("expected_snapshot_digest")
        assert post().status_code == 403


@pytest.mark.parametrize(
    "location", ["https://evil.example/a/b", "a/b/../c", "a/b;echo", "a/b?x=1"]
)
def test_github_selection_rejects_arbitrary_hosts_and_commands(location):
    with pytest.raises(ValidationError):
        RepositorySelection(kind="github", location=location, commit="a" * 40)


def test_github_requires_pin_and_transport_opt_in():
    with pytest.raises(ValidationError):
        RepositorySelection(kind="github", location="owner/repo")
    first = RepositorySelection(kind="github", location="owner/repo", commit="a" * 40)
    second = first.model_copy(update={"commit": "b" * 40})
    assert first.repository_id() == second.repository_id()
    with pytest.raises(ValueError, match="not enabled"):
        RepositoryResolver()(first)


def test_profile_loopback_isolation_and_explicit_secrets(tmp_path):
    credential = tmp_path / "credential.env"
    credential.write_text(
        "UNRELATED=value\nANTHROPIC_API_KEY=mock-only\n",  # pragma: allowlist secret
        encoding="utf-8",
    )
    assert secret_from_env(credential, "ANTHROPIC_API_KEY").get_secret_value() == "mock-only"
    credential.write_text("ANTHROPIC_API_KEY=one\nANTHROPIC_API_KEY=two", encoding="utf-8")
    with pytest.raises(ValueError):
        secret_from_env(credential, "ANTHROPIC_API_KEY")
    body = {
        "subject": "local",
        "database_url": "postgresql+psycopg://postgres@127.0.0.1/product_ops_pilot",
        "linear_scope": {
            "organization_id": str(uuid4()),
            "actor_id": str(uuid4()),
            "teams": [{"local_id": "product", "provider_id": str(uuid4())}],
        },
        "linear_key_file": str(credential),
        "anthropic_key_file": str(credential),
        "spend_authorization": "smoke-1",
        "maximum_spend": "10",
    }
    assert not PilotSettings.model_validate_json(json.dumps(body)).allow_publication
    for field, value in [
        ("database_url", "postgresql+psycopg://postgres@remote/product_ops_pilot"),
        ("database_url", "postgresql+psycopg://postgres@127.0.0.1/product_ops_test"),
        ("temporal_address", "remote:7233"),
        ("maximum_spend", "0"),
    ]:
        with pytest.raises(ValueError):
            PilotSettings.model_validate_json(json.dumps({**body, field: value}))
