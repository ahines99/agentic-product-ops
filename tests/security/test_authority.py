from datetime import UTC, datetime, timedelta

import pytest

from agentic_product_ops.adapters.persistence.store import Store, engine, metadata
from agentic_product_ops.cli import simulated_approval
from agentic_product_ops.policies.validation import PolicyError
from agentic_product_ops.services.authority import ActorGrant, Authority


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
