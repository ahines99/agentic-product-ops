"""Fail-closed gates for proposed specifications and offline approval validation."""

from __future__ import annotations

import re
from datetime import datetime

from agentic_product_ops.domain.clarifications import ClarificationReceipt
from agentic_product_ops.domain.contracts import (
    ID,
    Contract,
    SpecificationApproval,
    Tier,
    WorkSpecification,
)


class PolicyError(ValueError):
    """A deterministic gate denied an action."""


class ServerPolicy(Contract):
    version: ID = "m0-v1"
    workspace_id: ID = "offline-workspace"
    teams: tuple[ID, ...] = ("product",)
    projects: tuple[ID, ...] = ()
    repositories: tuple[ID, ...] = ("sample-reporting",)
    labels: tuple[ID, ...] = ()
    approvers: tuple[ID, ...] = ("offline-reviewer",)
    security_approvers: tuple[ID, ...] = ("offline-reviewer",)
    handoff_tiers: tuple[Tier, ...] = (0, 1)
    max_mutations: int = 20
    max_approval_seconds: int = 3600


def risk_floor(spec: WorkSpecification) -> Tier:
    """Conservative lexical floor, NOT a semantic risk classifier (ADR-003)."""
    text = " ".join(
        [
            spec.title,
            spec.objective,
            *(s.text for s in spec.source_statements),
            *(r.text for r in spec.requirements),
            *(q.question + " " + (q.resolution or "") for q in spec.unresolved_questions),
            *(a.text for a in spec.assumptions),
            *(w.title + " " + w.description for w in spec.work_items),
            *(a.text for w in spec.work_items for a in w.acceptance_criteria),
            *(
                (e.excerpt for e in spec.repository_context.evidence)
                if spec.repository_context
                else ()
            ),
        ]
    ).casefold()
    if any(
        term in text
        for term in (
            "destruct",
            "delete",
            "drop table",
            "irreversible",
            "credential",
            "secret",
            "compliance",
            "security policy",
            "security-policy",
            "production token",
        )
    ):
        return 3
    if any(
        term in text
        for term in (
            "auth",
            "admin",
            "payment",
            "sensitive",
            "financial",
            "revenue",
            "migration",
            "permission",
            "infrastructure",
            "external side effect",
            "customer data",
        )
    ):
        return 2
    if spec.provenance.mode != "authored_fixture":
        return 2
    return 1


def validate_scope(spec: WorkSpecification, policy: ServerPolicy) -> None:
    if spec.approval_policy.policy_version != policy.version or spec.risk.policy_version != (
        policy.version
    ):
        raise PolicyError("policy version mismatch")
    if spec.approval_policy.workspace_id != policy.workspace_id:
        raise PolicyError("workspace not allowed")
    if spec.approval_policy.required_role != "product_approver":
        raise PolicyError("unsupported approval role")
    if spec.risk.tier < risk_floor(spec):
        raise PolicyError("risk understated")
    if spec.repository_context and spec.repository_context.repository_id not in policy.repositories:
        raise PolicyError("repository not allowed")
    for work in spec.work_items:
        if work.proposed_team_id not in policy.teams:
            raise PolicyError("team not allowed")
        if work.proposed_project_id is not None and work.proposed_project_id not in policy.projects:
            raise PolicyError("project not allowed")
        if not set(work.proposed_labels) <= set(policy.labels):
            raise PolicyError("labels not allowed")
        if work.repository_id is not None and work.repository_id not in policy.repositories:
            raise PolicyError("repository not allowed")


def blocking_findings(
    spec: WorkSpecification, *, clarifications: tuple[ClarificationReceipt, ...] = ()
) -> tuple[str, ...]:
    """Objective checks only; does not impersonate an independent semantic reviewer."""
    findings: list[str] = []
    if not spec.requirements or not spec.work_items:
        findings.append("missing requirements or work decomposition")
    if any(q.blocking and q.resolution is None for q in spec.unresolved_questions):
        findings.append("material ambiguity unresolved")
    # Receipt arguments come from trusted persistence, never from proposed model output.
    expected = {r.id: r for r in clarifications}
    resolved = [q for q in spec.unresolved_questions if q.resolution is not None]
    if len(expected) != len(clarifications) or set(expected) != set(
        spec.provenance.clarification_refs
    ):
        findings.append("clarification authentication failed: receipts missing or invalid")
    for question in resolved:
        matches = [r for r in clarifications if r.question_id == question.id]
        if len(matches) != 1 or (
            matches[0].specification_id,
            matches[0].workspace_id,
            matches[0].question_text,
            matches[0].answer,
            matches[0].actor_id,
            matches[0].resolved_at,
        ) != (
            spec.specification_id,
            spec.approval_policy.workspace_id,
            question.question,
            question.resolution,
            question.resolved_by,
            question.resolved_at,
        ):
            findings.append("clarification authentication failed: receipts missing or invalid")
        elif matches[0].base_revision >= spec.revision:
            findings.append("clarification receipt revision invalid")
    if {r.question_id for r in clarifications} != {q.id for q in resolved}:
        findings.append("clarification authentication failed: receipts missing or invalid")
    if any(r.needs_human_decision for r in spec.requirements):
        findings.append("requirement needs human decision")
    if any(r.provenance == "safe_inference" for r in spec.requirements):
        findings.append("inferred behavior needs independent review")
    if any(
        a.provenance == "requires_human_decision"
        for w in spec.work_items
        for a in w.acceptance_criteria
    ):
        findings.append("acceptance criterion needs human decision")
    titles = [re.sub(r"\W+", " ", w.title.casefold()).strip() for w in spec.work_items]
    if len(titles) != len(set(titles)):
        findings.append("duplicate work item titles")
    return tuple(dict.fromkeys(findings))


def proposal_ready(
    spec: WorkSpecification,
    policy: ServerPolicy,
    *,
    clarifications: tuple[ClarificationReceipt, ...] = (),
) -> None:
    # Revalidate at each authority boundary, including objects made via model_construct/copy.
    WorkSpecification.model_validate_json(spec.model_dump_json())
    validate_scope(spec, policy)
    if any(r.actor_id not in policy.approvers for r in clarifications):
        raise PolicyError("clarification actor not authorized")
    if findings := blocking_findings(spec, clarifications=clarifications):
        raise PolicyError("; ".join(findings))


def validate_approval(
    spec: WorkSpecification,
    approval: SpecificationApproval,
    policy: ServerPolicy,
    *,
    authenticated_actor: str,
    plan_digest: str,
    operation_keys: tuple[str, ...],
    now: datetime,
    clarifications: tuple[ClarificationReceipt, ...] = (),
) -> None:
    """Caller-supplied identity is simulation-only until authenticated ingress exists."""
    proposal_ready(spec, policy, clarifications=clarifications)
    SpecificationApproval.model_validate_json(approval.model_dump_json())
    if now.tzinfo is None:
        raise PolicyError("aware clock required")
    if approval.actor_id != authenticated_actor or approval.actor_id not in policy.approvers:
        raise PolicyError("actor not authorized")
    if spec.risk.tier >= 2 and approval.actor_id not in policy.security_approvers:
        raise PolicyError("security approver required")
    if approval.decision != "approve":
        raise PolicyError("approval rejected")
    if (approval.specification_id, approval.revision, approval.content_digest) != (
        spec.specification_id,
        spec.revision,
        spec.content_digest,
    ):
        raise PolicyError("stale approval")
    if approval.policy_version != policy.version:
        raise PolicyError("stale approval policy")
    max_age = min(policy.max_approval_seconds, spec.approval_policy.max_age_seconds)
    if (
        not approval.issued_at <= now < approval.expires_at
        or (approval.expires_at - approval.issued_at).total_seconds() > max_age
    ):
        raise PolicyError("approval expired, future-dated, or overlong")
    scope = approval.scope
    if scope.workspace_id != policy.workspace_id or scope.plan_digest != plan_digest:
        raise PolicyError("approval scope or plan mismatch")
    if set(scope.team_ids) != {w.proposed_team_id for w in spec.work_items}:
        raise PolicyError("approval teams mismatch")
    if set(scope.repository_ids) != {
        w.repository_id for w in spec.work_items if w.repository_id is not None
    }:
        raise PolicyError("approval repositories mismatch")
    if scope.operation_keys != operation_keys or len(set(operation_keys)) != len(operation_keys):
        raise PolicyError("approval operations mismatch")
    if scope.allowed_mutation_count != len(operation_keys) or not (
        0 < len(operation_keys) <= policy.max_mutations
    ):
        raise PolicyError("mutation budget mismatch")
