from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from agentic_product_ops.adapters.identity.jwt import JWTAuthenticator
from agentic_product_ops.adapters.linear.offline import FakeLinear, build_plan
from agentic_product_ops.adapters.persistence.store import Store, engine, metadata
from agentic_product_ops.api.app import create_app
from agentic_product_ops.cli import simulated_approval
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy
from agentic_product_ops.services.authority import ActorGrant, Authority
from agentic_product_ops.services.publication import DurableSimulationPublisher


@pytest.fixture
def authority(tmp_path):
    db = engine(f"sqlite:///{tmp_path / 'authority.db'}", testing=True)
    metadata.create_all(db)
    tick = datetime.now(UTC)
    authority = Authority(
        Store(db),
        workspace="offline-workspace",
        issuer="https://identity.example",
        administrators=("operator",),
        clock=lambda: tick,
    )
    grant = ActorGrant(
        workspace_id="offline-workspace",
        actor_id="offline-reviewer",
        issuer="https://identity.example",
        subject="human-1",
        revision=1,
        roles=("product_approver", "security_approver"),
        team_ids=("product",),
        repository_ids=("sample-reporting",),
        issued_at=tick,
        expires_at=tick + timedelta(hours=1),
        enabled=True,
    )
    authority.register(grant, administrator="operator")
    yield authority, grant
    db.dispose()


def auth_and_token(authority, signing, key_id="key-1", keys=None):
    now = int(datetime.now(UTC).timestamp())
    auth = JWTAuthenticator(
        issuer=authority.issuer,
        audience="product-ops",
        keys=keys or {key_id: signing.public_key()},
        resolve_subject=authority.resolve_subject,
        revoked=authority.token_revoked,
    )
    token = jwt.encode(
        {
            "iss": authority.issuer,
            "aud": "product-ops",
            "sub": "human-1",
            "jti": "token-1",
            "iat": now,
            "nbf": now,
            "exp": now + 300,
            "roles": ["arbitrary-admin"],
            "workspace_id": "attacker-workspace",
        },
        signing,
        algorithm="RS256",
        headers={"kid": key_id},
    )
    return auth, token


def test_token_revocation_blocks_even_idempotent_command(authority):
    service, _ = authority
    signing = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    auth, token = auth_and_token(service, signing)
    with TestClient(create_app(service.store, authenticator=auth, authority=service)) as client:
        headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "same-command"}
        body = {"source": "Clarify an example request"}
        assert client.post("/v1/intakes", headers=headers, json=body).status_code == 201
        service.revoke("token", "token-1", administrator="operator")
        assert client.post("/v1/intakes", headers=headers, json=body).status_code == 401


@pytest.mark.parametrize("kind", ["actor", "approval", "subject", "grant"])
def test_revocation_between_publication_operations_holds_remaining(authority, valid, kind):
    service, grant = authority
    approval = simulated_approval(valid, service.clock())
    principal = service.resolve_subject("human-1")
    with service.store.database.begin() as conn:
        service.bind_approval(conn, principal, approval, valid)

    class RevokingProvider(FakeLinear):
        def create(self, operation):
            result = super().create(operation)
            if kind == "grant":
                service.register(grant.model_copy(update={"revision": 2}), administrator="operator")
            else:
                identity = {
                    "actor": grant.actor_id,
                    "subject": grant.subject,
                    "approval": str(approval.approval_id),
                }[kind]
                service.revoke(kind, identity, administrator="operator")
            return result

    provider = RevokingProvider()
    publisher = DurableSimulationPublisher(service.store, provider, service.clock, service)
    with pytest.raises(PolicyError, match="stale|revoked"):
        publisher.publish(
            valid, build_plan(valid, ServerPolicy()), approval, ServerPolicy(), principal.actor_id
        )
    assert provider.calls == 1
    with pytest.raises(PolicyError):
        DurableSimulationPublisher(service.store, provider, service.clock, service).publish(
            valid,
            build_plan(valid, ServerPolicy()),
            approval,
            ServerPolicy(),
            principal.actor_id,
        )
    assert provider.calls == 1


def test_scope_and_grant_revisions_fail_closed(authority, valid):
    service, grant = authority
    principal = service.resolve_subject("human-1")
    with pytest.raises(PolicyError, match="administrator"):
        service.register(grant, administrator="model-output")
    service.register(
        grant.model_copy(update={"revision": 2, "team_ids": ()}), administrator="operator"
    )
    with pytest.raises(PolicyError, match="stale"):
        service.check(principal)
    with service.store.database.begin() as conn, pytest.raises(PolicyError, match="team"):
        service.bind_approval(
            conn,
            service.resolve_subject("human-1"),
            simulated_approval(valid, service.clock()),
            valid,
        )


def test_pinned_key_rotation_has_explicit_overlap_and_retirement(authority):
    service, _ = authority
    old = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    new = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _, old_token = auth_and_token(service, old)
    both, new_token = auth_and_token(
        service,
        new,
        "key-2",
        {
            "key-1": old.public_key(),
            "key-2": new.public_key(),
        },
    )
    assert both.authenticate(old_token) and both.authenticate(new_token)
    rotated, _ = auth_and_token(service, new, "key-2")
    assert rotated.authenticate(old_token) is None
    assert rotated.authenticate(new_token).roles == ("product_approver", "security_approver")
