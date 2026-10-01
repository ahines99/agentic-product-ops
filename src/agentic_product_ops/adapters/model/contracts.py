"""Strict role envelopes, schema-bound proposals and observable usage receipts."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from agentic_product_ops.domain.contracts import (
    ID,
    Assumption,
    Contract,
    Dependency,
    Digest,
    Requirement,
    SourceStatement,
    Text,
    Tier,
    Timestamp,
    UnresolvedQuestion,
    WorkItem,
    WorkSpecification,
    unique,
)

Role = Literal["requirements_analyst", "work_decomposer", "specification_reviewer"]
# roles-v2 calibrates when questions block (ADR-023); roles-v3 turns minor gaps into recorded
# assumptions (ADR-025); roles-v4 limits ticket splitting and domain-term questions (ADR-027).
# Older receipts keep their version.
PromptVersion = Literal["roles-v1", "roles-v2", "roles-v3", "roles-v4"]
PROMPT_VERSION: PromptVersion = "roles-v4"
Money = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=8, allow_inf_nan=False)]


class Analysis(Contract):
    source_digest: Digest
    objective: Text
    source_statements: Annotated[tuple[SourceStatement, ...], Field(min_length=1)]
    requirements: tuple[Requirement, ...]
    unresolved_questions: tuple[UnresolvedQuestion, ...]

    @model_validator(mode="after")
    def identifiers(self) -> Self:
        unique(tuple(r.id for r in self.requirements), "analysis requirement")
        unique(tuple(q.id for q in self.unresolved_questions), "analysis question")
        for requirement in self.requirements:
            if requirement.needs_human_decision and not any(
                q.blocking and requirement.id in q.affected_requirement_ids
                for q in self.unresolved_questions
            ):
                raise ValueError("human decision requires an associated blocking question")
        return self


class Decomposition(Contract):
    """Models suggest work; identity, policy, source, revision and digest stay server-owned."""

    work_items: tuple[WorkItem, ...]
    dependencies: tuple[Dependency, ...]
    assumptions: tuple[Assumption, ...]
    risk_tier: Tier
    risk_reasons: Annotated[tuple[Text, ...], Field(min_length=1)]


class ReviewFinding(Contract):
    id: ID
    kind: Literal[
        "unsupported_requirement",
        "missing_criterion",
        "hidden_ambiguity",
        "overlap",
        "dependency",
        "risk",
        "scope",
        "grounding",
    ]
    summary: Text
    blocking: bool
    references: tuple[ID, ...]


class Review(Contract):
    specification_digest: Digest
    findings: tuple[ReviewFinding, ...]


class ModelRequest(Contract):
    run_id: UUID
    context_id: UUID
    role: Role
    prompt_version: PromptVersion = PROMPT_VERSION
    model: ID
    system_policy: Text
    authorized_configuration: Text
    untrusted_payload: Annotated[str, Field(min_length=1, max_length=200_000)]
    input_digest: Digest
    output_schema: Annotated[str, Field(min_length=1, max_length=100_000)]
    max_output_tokens: Annotated[int, Field(gt=0, le=16000)]
    max_input_tokens: Annotated[int, Field(gt=0, le=200_000)]


class ProviderUsage(Contract):
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    provider_request_id: ID


class ModelResponse(Contract):
    output_json: Annotated[str, Field(max_length=200_000)]
    usage: ProviderUsage


class RunReceipt(Contract):
    run_id: UUID
    context_id: UUID
    role: Role
    model: ID
    prompt_version: PromptVersion
    input_digest: Digest
    output_digest: Digest | None
    started_at: Timestamp
    elapsed_ms: Annotated[int, Field(ge=0)]
    status: Literal["SUCCEEDED", "INVALID_OUTPUT", "PROVIDER_UNAVAILABLE", "BUDGET_EXCEEDED"]
    usage: ProviderUsage | None
    estimated_cost: Money | None
    # Cost is an estimate, never substituted for provider usage or actual billed money.


class ModelBudget(Contract):
    max_calls: Annotated[int, Field(ge=0, le=100)]
    max_input_bytes: Annotated[int, Field(gt=0, le=200_000)]
    max_output_tokens: Annotated[int, Field(gt=0, le=16000)]
    max_estimated_cost: Money
    input_cost_per_million: Money
    output_cost_per_million: Money


class RuntimeConfiguration(Contract):
    configuration_id: ID
    provider_id: ID
    model: ID
    budget: ModelBudget
    max_review_attempts: Annotated[int, Field(ge=1, le=2)] = 2


class PipelineResult(Contract):
    state: Literal["AWAITING_CLARIFICATION", "REVISION_REQUIRED", "PROPOSED", "PAUSED"]
    analysis: Analysis | None
    specification: WorkSpecification | None
    review: Review | None
    receipts: tuple[RunReceipt, ...]
    reason: ID
