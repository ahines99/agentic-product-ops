import json
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from agentic_product_ops.adapters.model.contracts import (
    Analysis,
    Decomposition,
    ModelBudget,
    Review,
    RuntimeConfiguration,
)
from agentic_product_ops.adapters.model.responses import ResponsesProvider
from agentic_product_ops.adapters.persistence.store import Store, artifacts, engine, metadata
from agentic_product_ops.domain.contracts import seal_specification
from agentic_product_ops.policies.validation import PolicyError, ServerPolicy, proposal_ready
from agentic_product_ops.services.drafting import draft
from agentic_product_ops.services.durable_analysis import analysis_mode
from agentic_product_ops.services.revisions import revise_specification
from agentic_product_ops.workflows.activities import GovernanceActivities
from agentic_product_ops.workflows.governance import GovernanceInput


@pytest.mark.parametrize("ambiguous", [False, True])
def test_transport_to_durable_proposal_or_clarification(tmp_path, valid, ambiguous):
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
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 20})
        wire = json.loads(request.content)
        role = wire["text"]["format"]["name"]
        roles.append(role)
        payload = json.loads(wire["input"][2]["content"])
        if role == "requirements_analyst":
            value = Analysis(
                source_digest=seed.source_digest,
                objective=valid.objective,
                source_statements=seed.source_statements,
                requirements=valid.requirements,
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
        return httpx.Response(
            200,
            json={
                "id": "resp-authored",
                "status": "completed",
                "error": None,
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": value.model_dump_json()},
                        ],
                    }
                ],
                "usage": {"input_tokens": 20, "output_tokens": 10},
            },
        )

    provider = ResponsesProvider(
        model="test-model",
        api_key=SecretStr("ephemeral-mock-only"),
        transport=httpx.MockTransport(handler),
    )
    config = RuntimeConfiguration(
        configuration_id="mock-responses-v1",
        provider_id="openai-mock",
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
