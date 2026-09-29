"""Adjudicated semantic metrics; never infer correctness from prose."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import Field, model_validator

from agentic_product_ops.adapters.model.contracts import PipelineResult
from agentic_product_ops.domain.contracts import (
    ID,
    Contract,
    Digest,
    Text,
    Tier,
    canonical_digest,
    unique,
)

Category = Literal[
    "clear_feature",
    "ambiguous_request",
    "bug_report",
    "security",
    "data",
    "analytics",
    "multi_ticket",
    "research_request",
    "duplicate_rephrased",
    "prompt_injection",
]


class GoldRequirement(Contract):
    id: ID
    text: Text


class GoldAmbiguity(Contract):
    id: ID
    text: Text
    material: bool


class GoldCase(Contract):
    id: ID
    category: Category
    source: Text
    requirements: tuple[GoldRequirement, ...]
    ambiguities: tuple[GoldAmbiguity, ...]
    minimum_risk: Tier

    @model_validator(mode="after")
    def identities(self) -> Self:
        unique(tuple(r.id for r in self.requirements), "gold requirement")
        unique(tuple(a.id for a in self.ambiguities), "gold ambiguity")
        return self


class SemanticCorpus(Contract):
    schema_version: Literal["1"] = "1"
    authorship: Literal["same_context_template", "external_submission"]
    author_id: ID
    cases: Annotated[tuple[GoldCase, ...], Field(min_length=1)]
    corpus_digest: Digest

    @model_validator(mode="after")
    def integrity(self) -> Self:
        unique(tuple(c.id for c in self.cases), "semantic case")
        if self.corpus_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"corpus_digest"})
        ):
            raise ValueError("semantic corpus freeze mismatch")
        return self


class EvaluationAttempt(Contract):
    run_id: ID
    case_id: ID
    attempt: Annotated[int, Field(ge=1)]
    corpus_digest: Digest
    execution_mode: Literal["authored_recording", "reported_inference"]
    producer_id: ID
    result: PipelineResult


class RequirementJudgment(Contract):
    predicted_id: ID
    matched_gold_id: ID | None
    supported: bool


class CriterionJudgment(Contract):
    criterion_id: ID
    measurable: bool
    correct_traceability: bool
    correct_provenance: bool


class Adjudication(Contract):
    run_id: ID
    reviewer_id: ID
    corpus_digest: Digest
    result_digest: Digest
    requirements: tuple[RequirementJudgment, ...]
    detected_gold_ambiguities: tuple[ID, ...]
    falsely_resolved_gold_ambiguities: tuple[ID, ...]
    criteria: tuple[CriterionJudgment, ...]
    notes: Text
    independence_attested: bool


class SubmittedAdjudication(Contract):
    judgment: Adjudication
    signature: Annotated[str, Field(min_length=88, max_length=88)] | None = None


def ratio(numerator: int, denominator: int) -> dict[str, Any]:
    if not 0 <= numerator <= denominator:
        raise ValueError("invalid evaluation denominator")
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": str((Decimal(numerator) / denominator).quantize(Decimal("0.000001")))
        if denominator
        else None,
    }


def semantic_report(
    corpus: SemanticCorpus,
    attempts: tuple[EvaluationAttempt, ...],
    adjudications: tuple[SubmittedAdjudication, ...],
    trusted_reviewers: Mapping[str, Ed25519PublicKey] | None = None,
) -> dict[str, Any]:
    cases = {case.id: case for case in corpus.cases}
    trusted = dict(trusted_reviewers or {})
    unique(tuple(run.run_id for run in attempts), "evaluation run")
    unique(tuple(a.judgment.run_id for a in adjudications), "adjudication run")
    if len({(run.case_id, run.attempt) for run in attempts}) != len(attempts):
        raise ValueError("duplicate evaluation attempt")
    judgments = {a.judgment.run_id: a for a in adjudications}
    if set(judgments) != {a.run_id for a in attempts}:
        raise ValueError("every attempt requires explicit adjudication, including failures")
    if {run.case_id for run in attempts if run.attempt == 1} != set(cases):
        raise ValueError("each frozen case requires its original first attempt")
    rows: list[dict[str, Any]] = []
    for run in attempts:
        if run.case_id not in cases or run.corpus_digest != corpus.corpus_digest:
            raise ValueError("evaluation corpus mismatch")
        case, submitted = cases[run.case_id], judgments[run.run_id]
        judgment = submitted.judgment
        if (
            judgment.corpus_digest != corpus.corpus_digest
            or judgment.result_digest != canonical_digest(run.result.model_dump(mode="json"))
        ):
            raise ValueError("adjudication does not bind this frozen result")
        verified = False
        if submitted.signature is not None:
            if judgment.reviewer_id not in trusted:
                raise ValueError("adjudication reviewer key is not trusted")
            try:
                trusted[judgment.reviewer_id].verify(
                    base64.b64decode(submitted.signature, validate=True),
                    b"AgenticProductOps/Evaluation/v1\x00"
                    + canonical_digest(judgment.model_dump(mode="json")).encode(),
                )
                verified = True
            except Exception:
                raise ValueError("adjudication signature invalid") from None
        spec, analysis = run.result.specification, run.result.analysis
        predicted = spec.requirements if spec else (analysis.requirements if analysis else ())
        source = (
            spec.source_statements[0].text
            if spec
            else (analysis.source_statements[0].text if analysis else None)
        )
        if source is not None and source != case.source:
            raise ValueError("evaluated source differs from frozen case")
        unique(tuple(r.predicted_id for r in judgment.requirements), "requirement judgment")
        if {r.predicted_id for r in judgment.requirements} != {r.id for r in predicted}:
            raise ValueError("requirement judgments must cover every prediction")
        gold = {r.id for r in case.requirements}
        matched = {
            r.matched_gold_id
            for r in judgment.requirements
            if r.supported and r.matched_gold_id is not None
        }
        if any(
            r.matched_gold_id is not None and r.matched_gold_id not in gold
            for r in judgment.requirements
        ) or any(r.supported and r.matched_gold_id is None for r in judgment.requirements):
            raise ValueError("unsupported gold matching")
        ambiguities = {a.id for a in case.ambiguities if a.material}
        for values in (
            judgment.detected_gold_ambiguities,
            judgment.falsely_resolved_gold_ambiguities,
        ):
            unique(values, "ambiguity adjudication")
            if not set(values) <= ambiguities:
                raise ValueError("unknown material ambiguity judgment")
        criteria = {a.id for w in spec.work_items for a in w.acceptance_criteria} if spec else set()
        unique(tuple(a.criterion_id for a in judgment.criteria), "criterion judgment")
        if {a.criterion_id for a in judgment.criteria} != criteria:
            raise ValueError("criterion judgments must cover every prediction")
        correct_criteria = sum(
            a.measurable and a.correct_traceability and a.correct_provenance
            for a in judgment.criteria
        )
        rows.append(
            {
                "case_id": case.id,
                "category": case.category,
                "run_id": run.run_id,
                "attempt": run.attempt,
                "execution_mode": run.execution_mode,
                "state": run.result.state,
                "true_requirements": len(matched),
                "predicted_requirements": len(predicted),
                "gold_requirements": len(gold),
                "detected_material_ambiguities": len(judgment.detected_gold_ambiguities),
                "material_ambiguities": len(ambiguities),
                "false_resolutions": len(judgment.falsely_resolved_gold_ambiguities),
                "correct_criteria": correct_criteria,
                "criterion_count": len(criteria),
                "risk_underclassified": spec is not None and spec.risk.tier < case.minimum_risk,
                "provider_receipts": len(run.result.receipts),
                "elapsed_role_ms": sum(receipt.elapsed_ms for receipt in run.result.receipts),
                "attestation_signature_verified": verified,
                "independent_review_attested": verified
                and judgment.independence_attested
                and judgment.reviewer_id not in {run.producer_id, corpus.author_id}
                and corpus.authorship == "external_submission",
            }
        )
    first = [row for row in rows if row["attempt"] == 1]

    def aggregate(selected: list[dict[str, Any]]) -> dict[str, Any]:
        def measure(numerator: str, denominator: str) -> dict[str, Any]:
            return ratio(
                sum(row[numerator] for row in selected), sum(row[denominator] for row in selected)
            )

        return {
            "case_count": len(selected),
            "requirement_precision": measure("true_requirements", "predicted_requirements"),
            "requirement_recall": measure("true_requirements", "gold_requirements"),
            "material_ambiguity_recall": measure(
                "detected_material_ambiguities", "material_ambiguities"
            ),
            "false_resolution_rate": measure("false_resolutions", "material_ambiguities"),
            "criterion_quality": measure("correct_criteria", "criterion_count"),
            "risk_underclassified_cases": sum(row["risk_underclassified"] for row in selected),
        }

    return {
        "schema_version": "1",
        "mode": "adjudicated_semantic_report",
        "corpus_digest": corpus.corpus_digest,
        "corpus_authorship": corpus.authorship,
        "original_attempts": aggregate(first),
        "all_attempts": sorted(rows, key=lambda row: (row["case_id"], row["attempt"])),
        "retry_count": len(rows) - len(first),
        "by_category": {
            category: aggregate([row for row in first if row["category"] == category])
            for category in sorted({row["category"] for row in first})
        },
        "independent_review_attested_count": sum(
            row["independent_review_attested"] for row in first
        ),
        "mvp_completion": False,
        "unmeasured": [
            "Human usefulness/time savings",
            "Actual paid inference billing",
            "Live Linear reliability",
            "Deployed Delivery OS intake",
        ],
        "limitations": [
            "Scores depend on adjudication; signatures authenticate attestations, not truth.",
            "First attempts are scored separately; retries never replace original failures.",
            "Reported inference mode is not independent evidence of provider execution.",
        ],
    }
