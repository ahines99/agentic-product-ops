import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import TypeAdapter

from agentic_product_ops.domain.contracts import canonical_digest
from agentic_product_ops.evaluation.semantic import (
    EvaluationAttempt,
    SemanticCorpus,
    SubmittedAdjudication,
    ratio,
    semantic_report,
)

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "semantic"


@pytest.fixture
def inputs():
    return (
        SemanticCorpus.model_validate_json((EXAMPLES / "corpus.json").read_bytes()),
        TypeAdapter(tuple[EvaluationAttempt, ...]).validate_json(
            (EXAMPLES / "attempts.json").read_bytes()
        ),
        TypeAdapter(tuple[SubmittedAdjudication, ...]).validate_json(
            (EXAMPLES / "adjudications.json").read_bytes()
        ),
    )


def test_first_failure_retained_with_honest_denominators(inputs):
    report = semantic_report(*inputs)
    assert report["retry_count"] == 1
    recall = report["by_category"]["clear_feature"]["requirement_recall"]
    assert recall["numerator"] < recall["denominator"]
    assert report["all_attempts"][-1]["attempt"] == 2
    assert report["independent_review_attested_count"] == 0
    assert report["mvp_completion"] is False
    assert ratio(0, 0)["value"] is None
    with pytest.raises(ValueError):
        ratio(1, 0)


def test_missing_first_attempt_or_adjudication_denied(inputs):
    corpus, attempts, judgments = inputs
    with pytest.raises(ValueError, match="first attempt"):
        semantic_report(corpus, attempts[1:], judgments[1:])
    with pytest.raises(ValueError, match="every attempt"):
        semantic_report(corpus, attempts, judgments[1:])
    with pytest.raises(ValueError, match="duplicate"):
        semantic_report(corpus, attempts + (attempts[0],), judgments)


def test_frozen_corpus_and_result_binding(inputs):
    corpus, attempts, judgments = inputs
    raw = corpus.model_dump(mode="json")
    raw["cases"][0]["source"] = "changed"
    with pytest.raises(ValueError, match="freeze mismatch"):
        SemanticCorpus.model_validate_json(json.dumps(raw))
    changed = judgments[0].judgment.model_copy(update={"result_digest": "0" * 64})
    with pytest.raises(ValueError, match="frozen result"):
        semantic_report(
            corpus,
            attempts,
            (judgments[0].model_copy(update={"judgment": changed}), *judgments[1:]),
        )


def test_missing_and_unknown_annotations_denied(inputs):
    corpus, attempts, judgments = inputs
    for fields in (
        {"requirements": ()},
        {
            "requirements": (
                judgments[0]
                .judgment.requirements[0]
                .model_copy(update={"matched_gold_id": "unknown", "supported": False}),
            )
        },
        {"detected_gold_ambiguities": ("invented",)},
    ):
        changed = judgments[0].judgment.model_copy(update=fields)
        with pytest.raises(ValueError):
            semantic_report(
                corpus,
                attempts,
                (judgments[0].model_copy(update={"judgment": changed}), *judgments[1:]),
            )


def test_duplicate_matches_cannot_inflate_precision(inputs):
    corpus, attempts, judgments = inputs
    changed = judgments[1].judgment.model_copy(
        update={
            "requirements": tuple(
                r.model_copy(update={"matched_gold_id": corpus.cases[0].requirements[0].id})
                for r in judgments[1].judgment.requirements
            )
        }
    )
    report = semantic_report(
        corpus,
        attempts,
        (judgments[0], judgments[1].model_copy(update={"judgment": changed}), judgments[2]),
    )
    retry = report["all_attempts"][-1]
    assert retry["true_requirements"] == 1
    assert retry["predicted_requirements"] > 1


def test_independence_requires_trusted_signature_and_external_corpus(inputs):
    corpus, attempts, judgments = inputs
    raw = corpus.model_dump(mode="json", exclude={"corpus_digest"})
    raw.update(authorship="external_submission", author_id="external-author")
    corpus = SemanticCorpus.model_validate_json(
        json.dumps({**raw, "corpus_digest": canonical_digest(raw)})
    )
    attempts = tuple(a.model_copy(update={"corpus_digest": corpus.corpus_digest}) for a in attempts)
    key = Ed25519PrivateKey.generate()
    submissions = []
    for entry in judgments:
        judgment = entry.judgment.model_copy(
            update={
                "corpus_digest": corpus.corpus_digest,
                "reviewer_id": "reviewer",
                "independence_attested": True,
            }
        )
        signature = key.sign(
            b"AgenticProductOps/Evaluation/v1\x00"
            + canonical_digest(judgment.model_dump(mode="json")).encode()
        )
        submissions.append(
            SubmittedAdjudication(judgment=judgment, signature=base64.b64encode(signature).decode())
        )
    report = semantic_report(corpus, attempts, tuple(submissions), {"reviewer": key.public_key()})
    assert report["independent_review_attested_count"] == 2
    with pytest.raises(ValueError, match="not trusted"):
        semantic_report(corpus, attempts, tuple(submissions))
    with pytest.raises(ValueError, match="signature invalid"):
        semantic_report(
            corpus,
            attempts,
            tuple(submissions),
            {"reviewer": Ed25519PrivateKey.generate().public_key()},
        )


def test_false_resolution_denominator(inputs):
    corpus, attempts, judgments = inputs
    material = tuple(a.id for a in corpus.cases[1].ambiguities if a.material)
    assert material
    changed = judgments[2].judgment.model_copy(
        update={"falsely_resolved_gold_ambiguities": material}
    )
    report = semantic_report(
        corpus, attempts, (*judgments[:2], judgments[2].model_copy(update={"judgment": changed}))
    )
    assert report["original_attempts"]["false_resolution_rate"]["value"] == "1.000000"
