"""Strict, deeply immutable contracts. JSON is the public interchange format."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=16000, pattern=r"\S")]
ID = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


def strict_integer(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("integer required; booleans are not numeric authority")
    return value


Tier = Annotated[Literal[0, 1, 2, 3], BeforeValidator(strict_integer)]


def strict_true(value: Any) -> bool:
    if value is not True:
        raise ValueError("literal boolean true required")
    return True


TrueOnly = Annotated[Literal[True], BeforeValidator(strict_true)]
Confidence = Annotated[Decimal, Field(ge=0, le=1, allow_inf_nan=False)]


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return value.astimezone(UTC)


Timestamp = Annotated[datetime, AfterValidator(utc)]


def canonical_digest(value: Any) -> str:
    """APO JSON v1: UTF-8, sorted keys, compact JSON; ordered arrays, no NaN."""
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def source_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, str_strip_whitespace=False, validate_default=True
    )


class IntakeRequest(Contract):
    schema_version: Literal["1"] = "1"
    intake_id: UUID
    source_text: Text
    source_digest: Digest
    received_at: Timestamp
    source_kind: Literal["prompt", "structured_notes"]

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if source_digest(self.source_text) != self.source_digest:
            raise ValueError("source digest mismatch")
        return self


class SourceStatement(Contract):
    id: ID
    text: Text


class Evidence(Contract):
    id: ID
    path: Text
    excerpt: Text
    blob_digest: Digest
    advisory: TrueOnly = True


class RepositoryContext(Contract):
    repository_id: ID
    snapshot_id: Text
    snapshot_digest: Digest
    evidence: tuple[Evidence, ...]
    relevant_tests: tuple[Text, ...]
    unknown_edges: tuple[Text, ...]
    confidence: Confidence


class Requirement(Contract):
    id: ID
    text: Text
    kind: Literal[
        "functional", "non_functional", "security", "analytics", "data", "operational", "compliance"
    ]
    provenance: Literal[
        "explicit_source", "repository_evidence", "policy", "safe_inference", "human_clarification"
    ]
    source_refs: Annotated[tuple[ID, ...], Field(min_length=1)]
    confidence: Confidence
    needs_human_decision: bool


class AcceptanceCriterion(Contract):
    id: ID
    text: Text
    requirement_ids: Annotated[tuple[ID, ...], Field(min_length=1)]
    provenance: Literal[
        "directly_stated", "repository_or_policy", "safe_inference", "requires_human_decision"
    ]
    verification_kind: Literal[
        "automated_test",
        "manual_behavior",
        "telemetry",
        "security_check",
        "data_reconciliation",
        "documentation",
    ]
    evidence_required: Text
    blocking: bool


class WorkItem(Contract):
    local_id: ID
    title: Annotated[str, Field(min_length=1, max_length=240, pattern=r"\S")]
    description: Text
    type: Literal["epic", "feature", "task", "bug", "research"]
    requirement_ids: Annotated[tuple[ID, ...], Field(min_length=1)]
    acceptance_criteria: Annotated[tuple[AcceptanceCriterion, ...], Field(min_length=1)]
    dependencies: tuple[ID, ...]
    risk_tier: Tier
    repository_id: ID | None
    proposed_team_id: ID
    proposed_project_id: ID | None
    proposed_labels: tuple[ID, ...]


class UnresolvedQuestion(Contract):
    id: ID
    question: Text
    why_it_matters: Text
    affected_requirement_ids: tuple[ID, ...]
    blocking: bool
    resolution: Text | None
    resolved_by: ID | None
    resolved_at: Timestamp | None

    @model_validator(mode="after")
    def complete_resolution(self) -> Self:
        fields = (self.resolution, self.resolved_by, self.resolved_at)
        if any(x is not None for x in fields) and not all(x is not None for x in fields):
            raise ValueError("resolution requires answer, actor, and timestamp")
        return self


class Assumption(Contract):
    id: ID
    text: Text
    non_behavioral: TrueOnly


class Dependency(Contract):
    work_item_id: ID
    depends_on: ID


class RiskAssessment(Contract):
    tier: Tier
    reasons: Annotated[tuple[Text, ...], Field(min_length=1)]
    policy_version: ID


class ApprovalPolicy(Contract):
    policy_version: ID
    workspace_id: ID
    max_age_seconds: Annotated[int, Field(gt=0, le=86400)]
    required_role: ID


class SpecificationProvenance(Contract):
    mode: Literal["authored_fixture", "unrecognized_input", "model_proposal"]
    created_at: Timestamp
    producer: ID
    source_kind: Literal["prompt", "structured_notes"]
    policy_refs: tuple[ID, ...]
    clarification_refs: tuple[ID, ...]


def unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")


class WorkSpecification(Contract):
    schema_version: Literal["1"]
    specification_id: UUID
    revision: Annotated[int, Field(ge=1)]
    source_digest: Digest
    title: Text
    objective: Text
    source_statements: Annotated[tuple[SourceStatement, ...], Field(min_length=1)]
    requirements: tuple[Requirement, ...]
    unresolved_questions: tuple[UnresolvedQuestion, ...]
    assumptions: tuple[Assumption, ...]
    repository_context: RepositoryContext | None
    risk: RiskAssessment
    dependencies: tuple[Dependency, ...]
    work_items: tuple[WorkItem, ...]
    approval_policy: ApprovalPolicy
    provenance: SpecificationProvenance
    content_digest: Digest

    @model_validator(mode="after")
    def integrity(self) -> Self:
        # SourceStatement S0 is the exact complete intake; others are cited excerpts.
        if self.source_statements[0].id != "S0":
            raise ValueError("first source statement must be complete intake S0")
        original = self.source_statements[0].text
        if source_digest(original) != self.source_digest:
            raise ValueError("source digest mismatch")
        if any(s.text not in original for s in self.source_statements[1:]):
            raise ValueError("source statement is not an exact intake excerpt")
        groups = (
            tuple(s.id for s in self.source_statements),
            tuple(r.id for r in self.requirements),
            tuple(q.id for q in self.unresolved_questions),
            tuple(a.id for a in self.assumptions),
            tuple(w.local_id for w in self.work_items),
            tuple(a.id for w in self.work_items for a in w.acceptance_criteria),
            tuple(e.id for e in self.repository_context.evidence)
            if self.repository_context
            else (),
            self.provenance.policy_refs,
            self.provenance.clarification_refs,
        )
        unique(tuple(x for group in groups for x in group), "contract identifier")
        reqs, items = set(groups[1]), set(groups[4])
        refs = {
            "explicit_source": set(groups[0]),
            "repository_evidence": set(groups[6]),
            "policy": set(self.provenance.policy_refs),
            "safe_inference": set(groups[0]) | set(groups[6]),
            "human_clarification": set(self.provenance.clarification_refs),
        }
        for req in self.requirements:
            unique(req.source_refs, "source reference")
            if not set(req.source_refs) <= refs[req.provenance]:
                raise ValueError("invalid requirement provenance reference")
        for question in self.unresolved_questions:
            if not set(question.affected_requirement_ids) <= reqs:
                raise ValueError("unknown question requirement")
        graph = {w.local_id: w.dependencies for w in self.work_items}
        edges = {(d.work_item_id, d.depends_on) for d in self.dependencies}
        if len(edges) != len(self.dependencies) or edges != {
            (w.local_id, dep) for w in self.work_items for dep in w.dependencies
        }:
            raise ValueError("dependency representations disagree")
        covered: set[str] = set()
        for work in self.work_items:
            unique(work.dependencies, "dependency")
            unique(work.requirement_ids, "work requirement")
            if not set(work.requirement_ids) <= reqs:
                raise ValueError("unknown work requirement")
            if not set(work.dependencies) <= items or work.local_id in work.dependencies:
                raise ValueError("invalid dependency")
            if work.risk_tier < self.risk.tier:
                raise ValueError("work risk cannot be lower than specification risk")
            if work.repository_id is not None and (
                self.repository_context is None
                or work.repository_id != self.repository_context.repository_id
            ):
                raise ValueError("work repository lacks matching context")
            for criterion in work.acceptance_criteria:
                if not set(criterion.requirement_ids) <= set(work.requirement_ids):
                    raise ValueError("criterion is not traceable to its work item")
                covered.update(criterion.requirement_ids)
        if self.work_items and covered != reqs:
            raise ValueError("requirements lack acceptance coverage")
        pending = dict(graph)
        while pending:
            ready = {key for key, deps in pending.items() if not set(deps) & pending.keys()}
            if not ready:
                raise ValueError("cyclic dependency graph")
            pending = {key: deps for key, deps in pending.items() if key not in ready}
        if canonical_digest(self.model_dump(mode="json", exclude={"content_digest"})) != (
            self.content_digest
        ):
            raise ValueError("content digest mismatch")
        return self


def seal_specification(payload: dict[str, Any]) -> WorkSpecification:
    """Trusted authoring helper, never a way to grant approval or authenticate content."""
    candidate = {**payload, "content_digest": "0" * 64}
    # Canonicalize typed scalar representations before hashing, without bypassing final validation.
    fields = WorkSpecification.model_fields
    from pydantic import TypeAdapter

    normalized = {
        key: TypeAdapter(fields[key].rebuild_annotation()).validate_json(json.dumps(value))
        for key, value in candidate.items()
        if key in fields
    }
    temporary = WorkSpecification.model_construct(**normalized)
    candidate["content_digest"] = canonical_digest(
        temporary.model_dump(mode="json", exclude={"content_digest"})
    )
    return WorkSpecification.model_validate_json(json.dumps(candidate))


class ApprovalScope(Contract):
    workspace_id: ID
    team_ids: tuple[ID, ...]
    repository_ids: tuple[ID, ...]
    plan_digest: Digest
    operation_keys: Annotated[tuple[Digest, ...], Field(min_length=1)]
    allowed_mutation_count: Annotated[int, Field(gt=0, le=100)]


class SpecificationApproval(Contract):
    approval_id: UUID
    specification_id: UUID
    revision: Annotated[int, Field(ge=1)]
    content_digest: Digest
    actor_id: ID
    decision: Literal["approve", "reject"]
    scope: ApprovalScope
    issued_at: Timestamp
    expires_at: Timestamp
    policy_version: ID

    @model_validator(mode="after")
    def interval(self) -> Self:
        if self.expires_at <= self.issued_at:
            raise ValueError("invalid approval interval")
        unique(self.scope.operation_keys, "approved operation")
        unique(self.scope.team_ids, "approved team")
        unique(self.scope.repository_ids, "approved repository")
        return self


class AuditEvent(Contract):
    event_id: UUID
    trace_id: UUID
    intake_id: UUID
    specification_id: UUID
    revision: Annotated[int, Field(ge=1)]
    workflow_id: ID
    agent_run_id: ID | None
    operation_key: Digest | None
    provider_request_id: ID | None
    occurred_at: Timestamp
    event_type: ID
    actor_id: ID
    content_digest: Digest
    # No free-form source text, credentials, model reasoning, or provider response bodies.
