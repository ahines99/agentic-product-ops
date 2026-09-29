import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from agentic_product_ops.adapters.model.contracts import (
    ModelBudget,
    ModelResponse,
    ProviderUsage,
    RuntimeConfiguration,
)
from agentic_product_ops.adapters.persistence.store import (
    Conflict,
    Store,
    artifacts,
    engine,
    metadata,
)
from agentic_product_ops.domain.contracts import seal_specification
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy
from agentic_product_ops.services.authority import ActorGrant, Authority
from agentic_product_ops.services.durable_analysis import analyze_specification
from agentic_product_ops.services.risk_reassessment import RiskCommand, reassess_risk


@pytest.fixture
def setup(tmp_path, low_risk):
    db = engine(f"sqlite:///{tmp_path / 'risk.db'}", testing=True)
    metadata.create_all(db)
    store = Store(db)
    policy = ServerPolicy()
    body = low_risk.model_dump(mode="json")
    body["risk"]["tier"] = 3
    for w in body["work_items"]:
        w["risk_tier"] = 3
    spec = seal_specification(body)
    with db.begin() as conn:
        store.put(conn, policy.workspace_id, "specification", str(spec.specification_id), 1, spec)
    assert (
        analyze_specification(
            store, policy.workspace_id, str(spec.specification_id), spec.content_digest, policy
        ).state
        == "PROPOSED"
    )
    authority = Authority(
        store,
        workspace=policy.workspace_id,
        issuer="https://localhost/operator",
        administrators=("operator",),
    )
    now = datetime.now(UTC)
    authority.register(
        ActorGrant(
            workspace_id=policy.workspace_id,
            actor_id="offline-reviewer",
            issuer=authority.issuer,
            subject="operator",
            revision=1,
            roles=("product_approver", "security_approver"),
            team_ids=policy.teams,
            repository_ids=policy.repositories,
            issued_at=now,
            expires_at=now + timedelta(hours=1),
            enabled=True,
        ),
        administrator="operator",
    )
    actor = authority.resolve_subject("operator")
    config = RuntimeConfiguration(
        configuration_id="risk-test",
        provider_id="authored",
        model="recorded",
        budget=ModelBudget(
            max_calls=1,
            max_input_bytes=200000,
            max_output_tokens=1000,
            max_estimated_cost=Decimal(0),
            input_cost_per_million=Decimal(0),
            output_cost_per_million=Decimal(0),
        ),
    )
    yield store, authority, policy, actor, spec, config
    db.dispose()


class Reviewer:
    def __init__(self, blocker=False, revoke=None):
        self.calls, self.blocker, self.revoke = [], blocker, revoke

    def complete(self, request):
        self.calls.append(request)
        candidate = json.loads(request.untrusted_payload)["candidate"]
        if self.revoke:
            self.revoke()
        return ModelResponse(
            output_json=json.dumps(
                {
                    "specification_digest": candidate["content_digest"],
                    "findings": [
                        {
                            "id": "risk-finding",
                            "kind": "risk",
                            "summary": "Needs review",
                            "blocking": True,
                            "references": [],
                        }
                    ]
                    if self.blocker
                    else [],
                }
            ),
            usage=ProviderUsage(input_tokens=0, output_tokens=0, provider_request_id="authored"),
        )


def run(setup, provider, command=None, key="risk-command"):
    store, authority, policy, actor, spec, config = setup
    command = command or RiskCommand(
        revision=1,
        content_digest=spec.content_digest,
        tier=1,
        reason="Operator assessed documentation-only bounded impact",
    )
    return reassess_risk(
        store, authority, policy, config, provider, str(spec.specification_id), actor, command, key
    )


def test_risk_change_needs_fresh_review_and_approval_with_immutable_history(setup):
    store, _, policy, _, original, _ = setup
    provider = Reviewer()
    result = run(setup, provider)
    assert result.state == "PROPOSED" and result.specification.revision == 2
    candidate = result.specification
    for key in type(original).model_fields:
        if key not in {"revision", "risk", "work_items", "content_digest"}:
            assert getattr(candidate, key) == getattr(original, key)
    assert candidate.content_digest != original.content_digest
    assert run(setup, provider) == result and len(provider.calls) == 1
    assert (
        store.get(policy.workspace_id, "specification", str(original.specification_id), 1)["risk"][
            "tier"
        ]
        == 3
    )
    with store.database.connect() as conn:
        assert not conn.execute(select(artifacts).where(artifacts.c.kind == "approval")).first()


def test_blocking_review_cannot_promote(setup):
    provider = Reviewer(blocker=True)
    result = run(setup, provider)
    assert result.state == "REVISION_REQUIRED"
    store, _, policy, _, spec, _ = setup
    assert (
        store.get(policy.workspace_id, "specification", str(spec.specification_id))["revision"] == 1
    )


def test_stale_digest_floor_and_revocation_hold(setup):
    _, authority, _, _, spec, _ = setup
    provider = Reviewer()
    with pytest.raises(Conflict):
        run(
            setup,
            provider,
            RiskCommand(revision=1, content_digest="a" * 64, tier=1, reason="reason"),
        )
    with pytest.raises(PolicyError, match="risk floor"):
        run(
            setup,
            provider,
            RiskCommand(revision=1, content_digest=spec.content_digest, tier=0, reason="reason"),
        )
    assert not provider.calls
    provider = Reviewer(
        revoke=lambda: authority.revoke("actor", "offline-reviewer", administrator="operator")
    )
    with pytest.raises(PolicyError):
        run(setup, provider)
