"""Persist role intents/results; uncertain executions never repeat automatically."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, TypeVar

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from agentic_product_ops.adapters.model.contracts import (
    Analysis,
    ModelBudget,
    ModelRequest,
    ModelResponse,
    PipelineResult,
    ProviderUsage,
    Review,
    Role,
    RunReceipt,
)
from agentic_product_ops.adapters.model.runner import (
    PROMPTS,
    ModelProvider,
    RoleRunner,
    RunStopped,
    pipeline,
)
from agentic_product_ops.adapters.persistence.store import Missing, Store, artifacts, audits
from agentic_product_ops.domain.contracts import Contract, WorkSpecification, canonical_digest
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy

T = TypeVar("T", bound=Contract)


class CapturedProvider:
    def __init__(self, store: Store, workspace: str, step: str, provider: ModelProvider):
        self.store, self.workspace, self.step, self.provider = store, workspace, step, provider

    def complete(self, request: ModelRequest) -> ModelResponse:
        with self.store.database.begin() as conn:
            self.store.put(conn, self.workspace, "role_request", self.step, 1, request)
        response = self.provider.complete(request)
        # Validate before retaining any provider output. Do not persist exception text.
        validated = ModelResponse.model_validate_json(response.model_dump_json())
        with self.store.database.begin() as conn:
            self.store.put(conn, self.workspace, "role_response", self.step, 1, validated)
        return validated


class DurableRoleRunner(RoleRunner):
    def __init__(
        self,
        store: Store,
        workspace: str,
        specification_digest: str,
        provider: ModelProvider,
        budget: ModelBudget,
        identifier: str | None = None,
        model: str = "offline-recording",
    ):
        super().__init__(provider, budget, model)
        self.store, self.workspace, self.specification_digest = (
            store,
            workspace,
            specification_digest,
        )
        self.identifier = identifier

    def run(self, role: Role, payload: str, policy: ServerPolicy, output: type[T]) -> T:
        if self.identifier and self.store.cancelled(self.workspace, self.identifier):
            self.cancelled = True
        if self.cancelled or len(self.receipts) >= self.budget.max_calls:
            raise RunStopped("cancelled or call budget exhausted")
        binding = {
            "specification_digest": self.specification_digest,
            "role": role,
            "payload": payload,
            "policy": policy.model_dump(mode="json"),
            "schema": output.model_json_schema(),
            "prompt": PROMPTS[role],
            "model": self.model,
            "budget": self.budget.model_dump(mode="json"),
        }
        step = canonical_digest(binding)
        try:
            cached = self.store.get(self.workspace, "role_result", step)
        except Missing:
            cached = None
        if cached is not None:
            if cached["receipt"] is not None:
                cached_receipt = RunReceipt.model_validate_json(json.dumps(cached["receipt"]))
                self.receipts.append(cached_receipt)
                self.reserved_cost += Decimal(cached["reserved_cost"])
            if cached["output"] is None:
                self.cancelled = True
                raise RunStopped("previous run held")
            return output.model_validate_json(json.dumps(cached["output"]))
        try:
            with self.store.database.begin() as conn:
                if self.identifier and self.store.lock_specification(
                    conn, self.workspace, self.identifier
                ):
                    self.cancelled = True
                    raise RunStopped("cancelled before role reservation")
                exists = conn.execute(
                    select(artifacts.c.digest).where(
                        artifacts.c.workspace == self.workspace,
                        artifacts.c.kind == "role_intent",
                        artifacts.c.identity == step,
                        artifacts.c.revision == 1,
                    )
                ).first()
                if exists:
                    raise RunStopped("uncertain or concurrent role execution; operator hold")
                self.store.put(conn, self.workspace, "role_intent", step, 1, binding)
        except IntegrityError as exc:
            raise RunStopped("concurrent role execution; operator hold") from exc
        previous_provider, previous_cost = self.provider, self.reserved_cost
        self.provider = CapturedProvider(self.store, self.workspace, step, previous_provider)
        value: T | None = None
        receipt_count = len(self.receipts)
        try:
            value = super().run(role, payload, policy, output)
            return value
        finally:
            self.provider = previous_provider
            receipt = self.receipts[-1] if len(self.receipts) > receipt_count else None
            with self.store.database.begin() as conn:
                self.store.put(
                    conn,
                    self.workspace,
                    "role_result",
                    step,
                    1,
                    {
                        "output": value.model_dump(mode="json") if value else None,
                        "receipt": receipt.model_dump(mode="json") if receipt else None,
                        "reserved_cost": str(self.reserved_cost - previous_cost),
                    },
                )
                if receipt:
                    conn.execute(
                        insert(audits).values(
                            event_id=str(receipt.run_id),
                            workspace=self.workspace,
                            actor="role-runner",
                            action=f"role_{receipt.status.lower()}",
                            subject=step,
                            digest=receipt.input_digest,
                            occurred_at=receipt.started_at.isoformat(),
                        )
                    )


class RoleRecordings:
    """Trusted authored responses selected by role; supports safe replay of completed steps."""

    def __init__(self, spec: WorkSpecification):
        analysis = Analysis(
            source_digest=spec.source_digest,
            objective=spec.objective,
            source_statements=spec.source_statements,
            requirements=spec.requirements,
            unresolved_questions=spec.unresolved_questions,
        )
        self.recordings: dict[Role, Contract] = {
            "requirements_analyst": analysis,
            "work_decomposer": spec,
            "specification_reviewer": Review(specification_digest=spec.content_digest, findings=()),
        }

    def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            output_json=self.recordings[request.role].model_dump_json(),
            usage=ProviderUsage(
                input_tokens=0, output_tokens=0, provider_request_id="authored-recording"
            ),
        )


def analyze_specification(
    store: Store, workspace: str, identifier: str, digest: str, policy: ServerPolicy
) -> PipelineResult:
    if workspace != policy.workspace_id:
        raise PolicyError("workspace denied")
    spec = WorkSpecification.model_validate_json(
        json.dumps(store.get(workspace, "specification", identifier))
    )
    if spec.content_digest != digest:
        raise PolicyError("superseded specification")
    binding = canonical_digest(
        {"specification": digest, "policy": policy.model_dump(mode="json"), "runner": "recorded-v1"}
    )
    try:
        cached = store.get(workspace, "analysis_result", binding)
    except Missing:
        cached = None
    if cached:
        return PipelineResult.model_validate_json(json.dumps(cached))
    if spec.provenance.mode == "model_proposal" and not spec.provenance.clarification_refs:
        raise PolicyError("model proposal requires its original durable review")
    budget = ModelBudget(
        max_calls=3,
        max_input_bytes=200_000,
        max_output_tokens=16000,
        max_estimated_cost=Decimal(0),
        input_cost_per_million=Decimal(0),
        output_cost_per_million=Decimal(0),
    )
    runner = DurableRoleRunner(store, workspace, digest, RoleRecordings(spec), budget, identifier)
    result = pipeline(spec.source_statements[0].text, runner, policy, spec.repository_context)
    # A concurrent/uncertain step is held without writing a competing terminal result.
    if result.state == "PAUSED" and not runner.cancelled:
        return result
    with store.database.begin() as conn:
        store.put(conn, workspace, "analysis_result", binding, 1, result)
        store.put(
            conn,
            workspace,
            "analysis_index",
            identifier,
            spec.revision,
            {"binding": binding, "content_digest": digest},
        )
    return result


def load_analysis(
    store: Store, workspace: str, spec: WorkSpecification, policy: ServerPolicy
) -> PipelineResult:
    binding = canonical_digest(
        {
            "specification": spec.content_digest,
            "policy": policy.model_dump(mode="json"),
            "runner": "recorded-v1",
        }
    )
    result = store.get(workspace, "analysis_result", binding)
    return PipelineResult.model_validate_json(json.dumps(result))


def recorded_review(
    store: Store, workspace: str, spec: WorkSpecification, policy: ServerPolicy
) -> dict[str, Any]:
    parsed = load_analysis(store, workspace, spec, policy)
    if parsed.state != "PROPOSED" or parsed.specification != spec or parsed.review is None:
        raise PolicyError("analysis/review not ready")
    if parsed.review.specification_digest != spec.content_digest or any(
        f.blocking for f in parsed.review.findings
    ):
        raise PolicyError("blocking or mismatched review")
    return parsed.model_dump(mode="json")


def analysis_mode(store: Store, workspace: str, spec: WorkSpecification) -> dict[str, Any]:
    index = store.get(workspace, "analysis_index", str(spec.specification_id), spec.revision)
    try:
        runtime = store.get(workspace, "analysis_runtime", index["binding"])
    except Missing:
        return {"mode": "recorded_roles"}
    return {"mode": "configured_provider", "runtime": runtime}
