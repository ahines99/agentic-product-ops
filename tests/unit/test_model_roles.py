from decimal import Decimal

import pytest

from agentic_product_ops.adapters.model.contracts import (
    Analysis,
    ModelBudget,
    ModelResponse,
    ProviderUsage,
    Review,
    ReviewFinding,
)
from agentic_product_ops.adapters.model.runner import RoleRunner, ScriptedProvider, pipeline
from agentic_product_ops.domain.contracts import seal_specification
from agentic_product_ops.policies.validation import ServerPolicy
from agentic_product_ops.services.drafting import load_fixture


def response(value):
    return ModelResponse(
        output_json=value.model_dump_json(),
        usage=ProviderUsage(input_tokens=100, output_tokens=100, provider_request_id="recording-1"),
    )


def budget(**changes):
    return ModelBudget(
        max_calls=changes.get("max_calls", 3),
        max_input_bytes=200_000,
        max_output_tokens=1000,
        max_estimated_cost=Decimal("1"),
        input_cost_per_million=Decimal("1"),
        output_cost_per_million=Decimal("1"),
    )


def analysis(spec):
    return Analysis(
        source_digest=spec.source_digest,
        objective=spec.objective,
        source_statements=spec.source_statements,
        requirements=spec.requirements,
        unresolved_questions=spec.unresolved_questions,
    )


def test_separate_contexts_and_usage(valid):
    provider = ScriptedProvider(
        (
            response(analysis(valid)),
            response(valid),
            response(Review(specification_digest=valid.content_digest, findings=())),
        )
    )
    runner = RoleRunner(provider, budget())
    result = pipeline(valid.source_statements[0].text, runner, ServerPolicy())
    assert result.state == "PROPOSED"
    assert len({r.context_id for r in result.receipts}) == 3
    assert [r.role for r in result.receipts] == [
        "requirements_analyst",
        "work_decomposer",
        "specification_reviewer",
    ]
    assert all(r.estimated_cost == Decimal("0.0002") for r in result.receipts)
    assert "untrusted" in provider.requests[0].system_policy


def test_ambiguity_stops_before_decomposition():
    spec = load_fixture("ambiguous")
    provider = ScriptedProvider((response(analysis(spec)),))
    result = pipeline(
        spec.source_statements[0].text, RoleRunner(provider, budget()), ServerPolicy()
    )
    assert result.state == "AWAITING_CLARIFICATION"
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError("do not log provider secrets"),
        ModelResponse(
            output_json='{"approved":true}',
            usage=ProviderUsage(input_tokens=5, output_tokens=5, provider_request_id="bad"),
        ),
    ],
)
def test_provider_failure_preserved_and_paused(valid, failure):
    runner = RoleRunner(ScriptedProvider((failure,)), budget())
    result = pipeline(valid.source_statements[0].text, runner, ServerPolicy())
    assert result.state == "PAUSED"
    assert result.receipts[0].status in {"INVALID_OUTPUT", "PROVIDER_UNAVAILABLE"}
    assert "do not log" not in result.model_dump_json()


def test_budget_and_cancellation_prevent_call(valid):
    provider = ScriptedProvider(())
    runner = RoleRunner(provider, budget(max_calls=0))
    assert pipeline(valid.source_statements[0].text, runner, ServerPolicy()).state == "PAUSED"
    assert not provider.requests
    runner = RoleRunner(provider, budget())
    runner.cancel()
    assert pipeline(valid.source_statements[0].text, runner, ServerPolicy()).state == "PAUSED"
    assert not provider.requests


def test_review_blocker_preserved(valid):
    review = Review(
        specification_digest=valid.content_digest,
        findings=(
            ReviewFinding(
                id="F1",
                kind="unsupported_requirement",
                summary="Missing support",
                blocking=True,
                references=("R1",),
            ),
        ),
    )
    provider = ScriptedProvider((response(analysis(valid)), response(valid), response(review)))
    result = pipeline(
        valid.source_statements[0].text, RoleRunner(provider, budget()), ServerPolicy()
    )
    assert result.state == "REVISION_REQUIRED"
    assert result.review == review


def test_decomposer_cannot_change_requirements(valid):
    payload = valid.model_dump(mode="json")
    payload["requirements"][0]["text"] = "Invented behavior"
    changed = seal_specification(payload)
    provider = ScriptedProvider((response(analysis(valid)), response(changed)))
    result = pipeline(
        valid.source_statements[0].text, RoleRunner(provider, budget()), ServerPolicy()
    )
    assert result.state == "PAUSED"
    assert len(provider.requests) == 2
