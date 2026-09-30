import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from agentic_product_ops.domain.contracts import (
    IntakeRequest,
    WorkSpecification,
    canonical_digest,
    seal_specification,
)


def test_json_roundtrip_and_immutable(valid):
    assert WorkSpecification.model_validate_json(valid.model_dump_json()) == valid
    with pytest.raises(ValidationError):
        valid.title = "tamper"
    with pytest.raises(ValidationError):
        valid.requirements[0].text = "tamper"
    assert isinstance(valid.requirements, tuple)
    assert isinstance(valid.requirements[0].confidence, Decimal)


@pytest.mark.parametrize("tier", [True, False, "1", 1.0])
def test_risk_tier_rejects_coercion(low_risk, tier):
    payload = low_risk.model_dump(mode="json")
    payload["risk"]["tier"] = tier
    with pytest.raises(ValueError, match="integer"):
        seal_specification(payload)


@pytest.mark.parametrize("value", [1, "true", False])
def test_assumption_requires_literal_boolean(low_risk, value):
    payload = low_risk.model_dump(mode="json")
    payload["assumptions"][0]["non_behavioral"] = value
    with pytest.raises(ValueError, match="literal boolean"):
        seal_specification(payload)


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(extra_authority="approve"),
        lambda p: p.update(revision="1"),
        lambda p: p.update(revision=True),
        lambda p: p.update(schema_version="2"),
        lambda p: p.update(title=""),
        lambda p: p.update(title="   "),
        lambda p: p.update(content_digest="a" * 64),
        lambda p: p["requirements"][0].update(confidence="1.1"),
        lambda p: p["requirements"][0].update(confidence="NaN"),
        lambda p: p["provenance"].update(created_at="2026-09-28T00:00:00"),
    ],
)
def test_strict_invalid_contracts(valid, change):
    payload = valid.model_dump(mode="json")
    change(payload)
    with pytest.raises(ValidationError):
        WorkSpecification.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "change,match",
    [
        (lambda p: p["requirements"][0].update(source_refs=["invented"]), "provenance"),
        (lambda p: p["requirements"][0].update(id="R2"), "duplicate"),
        (
            lambda p: p["work_items"][0]["acceptance_criteria"][0].update(
                requirement_ids=["absent"]
            ),
            "traceable",
        ),
        (lambda p: p["work_items"][0].update(dependencies=["W404"]), "dependency"),
        (
            lambda p: p["dependencies"].append({"work_item_id": "W1", "depends_on": "W5"}),
            "dependency",
        ),
        (lambda p: p["work_items"][0].update(risk_tier=0), "risk"),
        (lambda p: p["work_items"][0].update(repository_id="invented"), "repository"),
        (
            lambda p: p["source_statements"].append({"id": "S1", "text": "Fabricated quotation"}),
            "excerpt",
        ),
    ],
)
def test_cross_references(valid, change, match):
    payload = valid.model_dump(mode="json")
    change(payload)
    with pytest.raises(ValueError, match=match):
        seal_specification(payload)


def test_cycle(valid):
    payload = valid.model_dump(mode="json")
    payload["work_items"][0]["dependencies"] = ["W5"]
    payload["dependencies"].append({"work_item_id": "W1", "depends_on": "W5"})
    with pytest.raises(ValueError, match="cyclic"):
        seal_specification(payload)


def test_source_digest_and_intake(valid):
    payload = valid.model_dump(mode="json")
    payload["source_statements"][0]["text"] += " changed"
    with pytest.raises(ValueError, match="source digest"):
        seal_specification(payload)
    with pytest.raises(ValueError, match="source digest"):
        IntakeRequest.model_validate_json(
            json.dumps(
                {
                    "intake_id": str(valid.specification_id),
                    "source_text": "tampered",
                    "source_digest": valid.source_digest,
                    "received_at": "2026-09-28T00:00:00Z",
                    "source_kind": "prompt",
                }
            )
        )


def test_canonicalization_and_revision_history(valid):
    assert canonical_digest({"a": 1, "b": 2}) == canonical_digest({"b": 2, "a": 1})
    assert canonical_digest([1, 2]) != canonical_digest([2, 1])
    original_bytes = valid.model_dump_json()
    payload = valid.model_dump(mode="json")
    payload["revision"] += 1
    revised = seal_specification(payload)
    assert revised.content_digest != valid.content_digest
    assert valid.model_dump_json() == original_bytes


def test_generated_titles_are_cut_at_a_word_boundary():
    from agentic_product_ops.services.revisions import title_from

    objective = "Replace re-displayable encrypted API keys with salted hashes " * 8
    title = title_from(objective)
    assert len(title) <= 240 and title.endswith("...")
    assert objective.startswith(title[:-3]) and objective[len(title) - 3] == " "
    assert title_from("Short objective") == "Short objective"
