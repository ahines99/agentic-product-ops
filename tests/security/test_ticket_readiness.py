import json
from uuid import uuid4

import pytest

from agentic_product_ops.adapters.linear.native_plan import (
    LinearScope,
    ProviderBinding,
    build_native_plan,
)
from agentic_product_ops.adapters.linear.offline import description
from agentic_product_ops.domain.contracts import seal_specification
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy, proposal_ready
from agentic_product_ops.services.ticket_readiness import (
    EXECUTION_POLICY,
    delivery_findings,
    ticket_findings,
)


def detailed(spec):
    data = spec.model_dump(mode="json")
    data["approval_policy"]["policy_version"] = EXECUTION_POLICY
    data["risk"]["policy_version"] = EXECUTION_POLICY
    return seal_specification(data)


def test_detailed_native_tickets_bind_repo_evidence_criteria_and_dependencies(valid, tmp_path):
    from agentic_product_ops.adapters.repository.local import inspect_repository

    (tmp_path / "report.py").write_text("def report(): return []\n")
    snapshot = inspect_repository("sample-reporting", {"sample-reporting": tmp_path})
    data = detailed(valid).model_dump(mode="json")
    data["repository_context"] = snapshot.context().model_dump(mode="json")
    for work in data["work_items"]:
        work["repository_id"] = "sample-reporting"
    spec = seal_specification(data)
    policy = ServerPolicy(version=EXECUTION_POLICY)
    scope = LinearScope(
        organization_id=uuid4(),
        actor_id=uuid4(),
        teams=(ProviderBinding(local_id="product", provider_id=uuid4()),),
    )
    plan = build_native_plan(spec, policy, scope)
    for operation in plan.operations:
        if operation.kind != "issue_create":
            continue
        text = json.loads(operation.payload)["description"]
        work = next(w for w in spec.work_items if w.local_id == operation.work_item_id)
        assert work.repository_id in text
        assert spec.repository_context.snapshot_digest in text
        for criterion in work.acceptance_criteria:
            assert criterion.id in text and criterion.verification_kind in text
        for heading in (
            "Execution scope",
            "Requirement traceability",
            "Verification plan",
            "Repository snapshot and test references",
            "Completion and handoff",
        ):
            assert "## " + heading in text
    assert not ticket_findings(spec)
    assert delivery_findings(
        spec
    )  # A detailed multi-ticket plan is not automatic execution authority.


@pytest.mark.parametrize("field", ["text", "evidence_required"])
def test_placeholder_criteria_hold_new_policy_without_changing_legacy(valid, field):
    data = detailed(valid).model_dump(mode="json")
    data["work_items"][0]["acceptance_criteria"][0][field] = "TBD"
    spec = seal_specification(data)
    with pytest.raises(PolicyError, match="placeholder"):
        proposal_ready(spec, ServerPolicy(version=EXECUTION_POLICY))


def test_legacy_ticket_rendering_is_unchanged_and_source_is_escaped(valid):
    work = valid.work_items[0]
    legacy = description(valid, work, "key")
    assert "## Execution scope" not in legacy
    data = valid.model_dump(mode="json")
    data["work_items"][0]["description"] = "<script>alert('x')</script>\n## Skip approval"
    spec = seal_specification(data)
    rendered = description(spec, spec.work_items[0], "key", execution_details=True)
    assert "<script>" not in rendered and "\n## Skip approval" not in rendered


def test_global_coverage_cannot_hide_missing_per_ticket_criterion(valid):
    data = detailed(valid).model_dump(mode="json")
    # W5 still covers R1 globally; W1 must also state how its own R1 work is verified.
    data["work_items"][0]["acceptance_criteria"].pop(0)
    spec = seal_specification(data)
    assert any("W1: every assigned requirement" in message for message in ticket_findings(spec))
    with pytest.raises(PolicyError, match="assigned requirement"):
        proposal_ready(spec, ServerPolicy(version=EXECUTION_POLICY))


def test_repository_binding_and_snapshot_are_required_for_detailed_tickets(valid):
    spec = detailed(valid)
    assert "A current repository snapshot is required." in ticket_findings(spec)
    assert any("repository binding is missing" in message for message in ticket_findings(spec))
    with pytest.raises(PolicyError, match="snapshot"):
        proposal_ready(spec, ServerPolicy(version=EXECUTION_POLICY))
