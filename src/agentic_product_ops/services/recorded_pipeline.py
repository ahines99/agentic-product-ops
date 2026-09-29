"""Runnable role orchestration backed by explicitly authored fixture responses."""

from decimal import Decimal

from agentic_product_ops.adapters.model.contracts import (
    Analysis,
    ModelBudget,
    ModelResponse,
    PipelineResult,
    ProviderUsage,
    Review,
)
from agentic_product_ops.adapters.model.runner import RoleRunner, ScriptedProvider, pipeline
from agentic_product_ops.domain.contracts import Contract, RepositoryContext, seal_specification
from agentic_product_ops.policies.validation import ServerPolicy, risk_floor
from agentic_product_ops.services.drafting import draft


def recorded_pipeline(source: str, context: RepositoryContext | None = None) -> PipelineResult:
    spec, _ = draft(source)
    policy = ServerPolicy(repositories=(context.repository_id,) if context else ())
    payload = spec.model_dump(mode="json")
    payload["repository_context"] = context.model_dump(mode="json") if context else None
    for work in payload["work_items"]:
        work["repository_id"] = context.repository_id if context else None
    staged = seal_specification(payload)
    payload["risk"]["tier"] = max(spec.risk.tier, risk_floor(staged))
    for work in payload["work_items"]:
        work["risk_tier"] = payload["risk"]["tier"]
    spec = seal_specification(payload)
    analysis = Analysis(
        source_digest=spec.source_digest,
        objective=spec.objective,
        source_statements=spec.source_statements,
        requirements=spec.requirements,
        unresolved_questions=spec.unresolved_questions,
    )

    def response(contract: Contract) -> ModelResponse:
        return ModelResponse(
            output_json=contract.model_dump_json(),
            usage=ProviderUsage(
                input_tokens=0, output_tokens=0, provider_request_id="authored-recording"
            ),
        )

    provider = ScriptedProvider(
        (
            response(analysis),
            response(spec),
            response(Review(specification_digest=spec.content_digest, findings=())),
        )
    )
    budget = ModelBudget(
        max_calls=3,
        max_input_bytes=200_000,
        max_output_tokens=16000,
        max_estimated_cost=Decimal(0),
        input_cost_per_million=Decimal(0),
        output_cost_per_million=Decimal(0),
    )
    return pipeline(source, RoleRunner(provider, budget), policy, context)
