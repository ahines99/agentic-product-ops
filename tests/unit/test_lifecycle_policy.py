import pytest

from agentic_product_ops.domain.contracts import seal_specification
from agentic_product_ops.policies.validation import (
    PolicyError,
    ServerPolicy,
    blocking_findings,
    proposal_ready,
    risk_floor,
)
from agentic_product_ops.services.drafting import draft, load_fixture
from agentic_product_ops.workflows.lifecycle import Lifecycle, State, transition


def test_proposal_path(valid):
    current = Lifecycle(state=State.RECEIVED, content_digest=valid.content_digest)
    for target in (
        State.NORMALIZED,
        State.REQUIREMENTS_DRAFTED,
        State.CONTEXT_GATHERED,
        State.WORK_DECOMPOSED,
        State.INDEPENDENT_SPEC_REVIEW,
        State.PROPOSED,
        State.AWAITING_APPROVAL,
    ):
        current = transition(current, target, valid, ServerPolicy())
    with pytest.raises(PolicyError, match="derived from durable records"):
        transition(current, State.APPROVED, valid, ServerPolicy())


def test_no_arbitrary_patch_or_terminal_escape(valid):
    current = Lifecycle(state=State.RECEIVED, content_digest=valid.content_digest)
    with pytest.raises(PolicyError, match="illegal"):
        transition(current, State.PUBLISHED, valid, ServerPolicy())
    cancelled = transition(current, State.CANCELLED, valid, ServerPolicy())
    with pytest.raises(PolicyError, match="terminal"):
        transition(cancelled, State.NORMALIZED, valid, ServerPolicy())


def test_material_ambiguity_cannot_progress():
    spec = load_fixture("ambiguous")
    state = Lifecycle(state=State.REQUIREMENTS_DRAFTED, content_digest=spec.content_digest)
    with pytest.raises(PolicyError, match="ambiguity"):
        transition(state, State.CONTEXT_GATHERED, spec, ServerPolicy())
    held = transition(state, State.AWAITING_CLARIFICATION, spec, ServerPolicy())
    assert held.state == State.AWAITING_CLARIFICATION
    assert len(spec.unresolved_questions) == 5


def test_safe_assumption_visible(valid):
    assert valid.assumptions[0].non_behavioral
    proposal_ready(valid, ServerPolicy())


def test_confidence_never_overrides_decision(valid):
    payload = valid.model_dump(mode="json")
    payload["requirements"][0]["needs_human_decision"] = True
    with pytest.raises(PolicyError, match="human decision"):
        proposal_ready(seal_specification(payload), ServerPolicy())


def test_duplicate_and_unsupported_inference(valid):
    payload = valid.model_dump(mode="json")
    payload["work_items"][1]["title"] = payload["work_items"][0]["title"]
    payload["requirements"][0]["provenance"] = "safe_inference"
    findings = blocking_findings(seal_specification(payload))
    assert "duplicate work item titles" in findings
    assert "inferred behavior needs independent review" in findings


@pytest.mark.parametrize(
    "text,tier",
    [
        ("Delete production data", 3),
        ("Modify authorization", 2),
        ("Write about payments", 2),
        ("Purge every customer record and wipe backups", 3),
        ("Rotate the database password", 3),
        ("Add OAuth sign-in", 2),
        ("Change the invoice layout", 2),
    ],
)
def test_deterministic_risk_floor(text, tier):
    spec, _ = draft(text)
    assert risk_floor(spec) == tier


@pytest.mark.parametrize(
    "field,value",
    [
        ("proposed_team_id", "attacker"),
        ("proposed_project_id", "other-project"),
        ("proposed_labels", ["unapproved"]),
    ],
)
def test_scope_allowlists(valid, field, value):
    payload = valid.model_dump(mode="json")
    payload["work_items"][0][field] = value
    with pytest.raises(PolicyError, match="not allowed"):
        proposal_ready(seal_specification(payload), ServerPolicy())
