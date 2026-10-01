import json
from decimal import Decimal

import pytest
from sqlalchemy import select

from agentic_product_ops.adapters.model.contracts import (
    Analysis,
    Decomposition,
    ModelBudget,
    ModelResponse,
    ProviderUsage,
    Review,
    ReviewFinding,
    RuntimeConfiguration,
)
from agentic_product_ops.adapters.persistence.store import Store, artifacts, engine, metadata
from agentic_product_ops.domain.contracts import seal_specification
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy, proposal_ready
from agentic_product_ops.services.drafting import draft
from agentic_product_ops.services.durable_analysis import analysis_mode
from agentic_product_ops.services.revisions import revise_specification
from agentic_product_ops.workflows.activities import GovernanceActivities
from agentic_product_ops.workflows.governance import GovernanceInput


@pytest.mark.parametrize("ambiguous", [False, True])
@pytest.mark.parametrize("invalid_provenance", [False, True])
def test_transport_to_durable_proposal_or_clarification(
    tmp_path, valid, ambiguous, invalid_provenance
):
    source = valid.source_statements[0].text + "\nThis is a new request."
    seed, _ = draft(source)
    body = seed.model_dump(mode="json")
    body["repository_context"] = None
    seed = seal_specification(body)
    database = engine(f"sqlite:///{tmp_path / 'generation.db'}", testing=True)
    metadata.create_all(database)
    store = Store(database)
    with database.begin() as conn:
        store.put(conn, "offline-workspace", "specification", str(seed.specification_id), 1, seed)
    roles = []

    def handler(request):
        role = request.role
        roles.append(role)
        payload = json.loads(request.untrusted_payload)
        if role == "requirements_analyst":
            value = Analysis(
                source_digest=seed.source_digest,
                objective=valid.objective,
                source_statements=seed.source_statements,
                requirements=(
                    tuple(
                        r.model_copy(update={"source_refs": ("missing-source",)})
                        for r in valid.requirements
                    )
                    if invalid_provenance
                    else valid.requirements
                ),
                unresolved_questions=seed.unresolved_questions if ambiguous else (),
            )
        elif role == "work_decomposer":
            value = Decomposition(
                work_items=valid.work_items,
                dependencies=valid.dependencies,
                assumptions=valid.assumptions,
                risk_tier=valid.risk.tier,
                risk_reasons=valid.risk.reasons,
            )
        else:
            value = Review(specification_digest=payload["candidate"]["content_digest"], findings=())
        return ModelResponse(
            output_json=value.model_dump_json(),
            usage=ProviderUsage(
                input_tokens=20, output_tokens=10, provider_request_id="authored-recording"
            ),
        )

    class Recording:
        """Authored role outputs, never semantic-quality evidence."""

        def complete(self, request):
            return handler(request)

    provider = Recording()
    config = RuntimeConfiguration(
        configuration_id="recorded-roles-v1",
        provider_id="recording",
        model="test-model",
        budget=ModelBudget(
            max_calls=6,
            max_input_bytes=200_000,
            max_output_tokens=16000,
            max_estimated_cost=Decimal("10"),
            input_cost_per_million=Decimal("1"),
            output_cost_per_million=Decimal("1"),
        ),
    )
    result = revise_specification(
        store,
        str(seed.specification_id),
        seed.content_digest,
        ServerPolicy(),
        config,
        provider,
        initial=True,
    )
    if invalid_provenance:
        assert result.state == "REVISION_REQUIRED" and result.reason == "composed_schema_gate"
        with database.connect() as conn:
            assert (
                conn.execute(select(artifacts).where(artifacts.c.kind == "revision_result")).first()
                is not None
            )
        replay = revise_specification(
            store,
            str(seed.specification_id),
            seed.content_digest,
            ServerPolicy(),
            config,
            provider,
            initial=True,
        )
        assert replay == result and len(roles) == (1 if ambiguous else 2)
        database.dispose()
        return
    assert result.state == ("AWAITING_CLARIFICATION" if ambiguous else "PROPOSED")
    candidate = result.specification
    assert candidate.revision == 2 and candidate.specification_id == seed.specification_id
    assert candidate.source_digest == seed.source_digest
    assert candidate.repository_context == seed.repository_context
    assert candidate.risk.tier == 3  # Unknown intake can never downclassify itself.
    assert len(roles) == (1 if ambiguous else 3)
    assert analysis_mode(store, "offline-workspace", candidate)["runtime"]["model"] == "test-model"
    if ambiguous:
        with pytest.raises(PolicyError, match="ambiguity"):
            proposal_ready(candidate, ServerPolicy())
    else:
        proposal_ready(candidate, ServerPolicy())
    activities = GovernanceActivities(store, ServerPolicy())
    request = GovernanceInput(
        "offline-workspace", str(candidate.specification_id), candidate.content_digest
    )
    assert activities.prepare(request) == result.state
    replay = revise_specification(
        store,
        str(seed.specification_id),
        seed.content_digest,
        ServerPolicy(),
        config,
        provider,
        initial=True,
    )
    assert replay == result and len(roles) == (1 if ambiguous else 3)
    with database.connect() as conn:
        assert conn.execute(select(artifacts).where(artifacts.c.kind == "approval")).first() is None
    database.dispose()


def test_inference_is_ready_only_with_a_passing_review_of_that_exact_content(tmp_path, valid):
    source = valid.source_statements[0].text + "\nThis is a new request."
    seed, _ = draft(source)
    body = seed.model_dump(mode="json")
    body["repository_context"] = None
    seed = seal_specification(body)
    database = engine(f"sqlite:///{tmp_path / 'inference.db'}", testing=True)
    metadata.create_all(database)
    store = Store(database)
    with database.begin() as conn:
        store.put(conn, "offline-workspace", "specification", str(seed.specification_id), 1, seed)
    inferred = (
        valid.requirements[0].model_copy(update={"provenance": "safe_inference"}),
        *valid.requirements[1:],
    )

    class Recording:
        def complete(self, request):
            payload = json.loads(request.untrusted_payload)
            if request.role == "requirements_analyst":
                value = Analysis(
                    source_digest=seed.source_digest,
                    objective=valid.objective,
                    source_statements=seed.source_statements,
                    requirements=inferred,
                    unresolved_questions=(),
                )
            elif request.role == "work_decomposer":
                value = Decomposition(
                    work_items=valid.work_items,
                    dependencies=valid.dependencies,
                    assumptions=valid.assumptions,
                    risk_tier=valid.risk.tier,
                    risk_reasons=valid.risk.reasons,
                )
            else:
                value = Review(
                    specification_digest=payload["candidate"]["content_digest"], findings=()
                )
            return ModelResponse(
                output_json=value.model_dump_json(),
                usage=ProviderUsage(
                    input_tokens=1, output_tokens=1, provider_request_id="authored-recording"
                ),
            )

    config = RuntimeConfiguration(
        configuration_id="recorded-inference-v1",
        provider_id="recording",
        model="test-model",
        budget=ModelBudget(
            max_calls=6,
            max_input_bytes=200_000,
            max_output_tokens=16000,
            max_estimated_cost=Decimal("10"),
            input_cost_per_million=Decimal("1"),
            output_cost_per_million=Decimal("1"),
        ),
    )
    result = revise_specification(
        store,
        str(seed.specification_id),
        seed.content_digest,
        ServerPolicy(),
        config,
        Recording(),
        initial=True,
    )
    assert result.state == "PROPOSED", result.reason
    spec = result.specification
    assert any(r.provenance == "safe_inference" for r in spec.requirements)
    proposal_ready(spec, ServerPolicy(), review=result.review)
    # Without a review, with a review of other content, or with a blocking finding: held.
    with pytest.raises(PolicyError, match="inferred"):
        proposal_ready(spec, ServerPolicy())
    elsewhere = result.review.model_copy(update={"specification_digest": "0" * 64})
    with pytest.raises(PolicyError, match="inferred"):
        proposal_ready(spec, ServerPolicy(), review=elsewhere)
    blocking = result.review.model_copy(
        update={
            "findings": (
                ReviewFinding(
                    id="F1",
                    kind="unsupported_requirement",
                    summary="Inference not supported",
                    blocking=True,
                    references=(spec.requirements[0].id,),
                ),
            )
        }
    )
    with pytest.raises(PolicyError, match="inferred"):
        proposal_ready(spec, ServerPolicy(), review=blocking)
    database.dispose()
