"""Bounded, durable clarification-driven proposal generation; only code may promote revisions."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import insert

from agentic_product_ops.adapters.model.contracts import (
    Analysis,
    Decomposition,
    PipelineResult,
    Review,
    RuntimeConfiguration,
)
from agentic_product_ops.adapters.model.runner import ModelProvider, RunStopped
from agentic_product_ops.adapters.persistence.store import Conflict, Missing, Store, outbox
from agentic_product_ops.domain.contracts import (
    WorkSpecification,
    canonical_digest,
    seal_specification,
)
from agentic_product_ops.policies.revisions import validate_revision
from agentic_product_ops.policies.validation import (
    PolicyError,
    ServerPolicy,
    proposal_ready,
    risk_floor,
    validate_scope,
)
from agentic_product_ops.services.clarifications import load_clarifications
from agentic_product_ops.services.drafting import draft
from agentic_product_ops.services.durable_analysis import DurableRoleRunner


def title_from(objective: str, limit: int = 240) -> str:
    """Titles derive from the objective and are cut at a word boundary, never mid-word."""
    if len(objective) <= limit:
        return objective
    cut = objective[: limit - 3].rsplit(" ", 1)[0].rstrip(" ,;:.-")
    return (cut or objective[: limit - 3]) + "..."


def revise_specification(
    store: Store,
    identifier: str,
    expected_digest: str,
    policy: ServerPolicy,
    configuration: RuntimeConfiguration,
    provider: ModelProvider,
    *,
    initial: bool = False,
) -> PipelineResult:
    workspace = policy.workspace_id
    execution = canonical_digest(
        {
            "base": expected_digest,
            "policy": policy.model_dump(mode="json"),
            "runtime": configuration.model_dump(mode="json"),
            "initial": initial,
        }
    )
    with store.database.begin() as conn:
        if store.lock_specification(conn, workspace, identifier):
            raise PolicyError("cancelled")
        try:
            completed = store.get(workspace, "revision_result", execution, connection=conn)
        except Missing:
            completed = None
        if completed is not None:
            return PipelineResult.model_validate_json(json.dumps(completed))
        base = WorkSpecification.model_validate_json(
            json.dumps(store.get(workspace, "specification", identifier, connection=conn))
        )
        if base.content_digest != expected_digest:
            raise Conflict("superseded revision request")
        if initial:
            template, _ = draft(base.source_statements[0].text, use_fixtures=False)
            expected = template.model_dump(mode="json")
            expected["specification_id"] = str(base.specification_id)
            expected["approval_policy"].update(
                workspace_id=policy.workspace_id,
                policy_version=policy.version,
                max_age_seconds=policy.max_approval_seconds,
            )
            expected["risk"]["policy_version"] = policy.version
            expected["provenance"]["created_at"] = base.provenance.created_at.isoformat()
            expected["repository_context"] = (
                base.repository_context.model_dump(mode="json") if base.repository_context else None
            )
            if template.provenance.mode != "unrecognized_input" or base != seal_specification(
                expected
            ):
                raise PolicyError("initial generation requires an unchanged intake seed")
        elif not base.provenance.clarification_refs:
            raise PolicyError("clarification revision requires recorded answers")
        try:
            intent = store.get(workspace, "revision_intent", execution, connection=conn)
        except Missing:
            intent = {
                "base_digest": expected_digest,
                "created_at": datetime.now(UTC).isoformat(),
                "configuration": configuration.model_dump(mode="json"),
            }
            store.put(conn, workspace, "revision_intent", execution, 1, intent)
    answers = load_clarifications(store, base, policy)
    runner = DurableRoleRunner(
        store,
        workspace,
        expected_digest,
        provider,
        configuration.budget,
        identifier,
        configuration.model,
    )
    review: Review | None = None
    analysis: Analysis | None = None
    candidate: WorkSpecification | None = None
    state, reason = "REVISION_REQUIRED", "review_attempts_exhausted"
    for attempt in range(1, configuration.max_review_attempts + 1):
        payload = {
            "initial_intake": initial,
            "instructions": (
                "On initial intake, the empty seed's Q1 is a routing placeholder, not an "
                "established product ambiguity. Extract actual requirements and actual unknowns. "
                "Preserve S0 exactly. Return exact source excerpts with unique IDs and cite them. "
                "On a clarification revision preserve every original requirement and answer, "
                "and return the objective and unresolved_questions exactly as given, including "
                "affected_requirement_ids; link new requirements to an answer only through "
                "their source_refs. Once every blocking question affecting a requirement has an "
                "authenticated answer, set that requirement's needs_human_decision to false. "
                "Use only the configured team/project/label scope and supplied repository ID. "
                "Do not fabricate approvals or answers. Decomposer must include every requirement "
                "in work item requirement_ids and every criterion must cite real requirements."
                " Each requirement has exactly one provenance class: explicit_source and "
                "safe_inference references must use only source statement IDs; "
                "repository_evidence must use only supplied evidence IDs; policy must use "
                "only supplied policy_refs; human_clarification must use only saved answer IDs. "
                "Split requirements if provenance differs. Never mix S and E references on "
                "an explicit_source requirement."
            ),
            "base_specification": base.model_dump(mode="json"),
            "authenticated_answers": [answer.model_dump(mode="json") for answer in answers],
            "attempt": attempt,
            "previous_review": review.model_dump(mode="json") if review else None,
        }
        try:
            analysis = runner.run("requirements_analyst", json.dumps(payload), policy, Analysis)
            if (
                analysis.source_digest != base.source_digest
                or analysis.source_statements[0] != base.source_statements[0]
                or (
                    not initial
                    and (
                        analysis.source_statements != base.source_statements
                        or analysis.unresolved_questions != base.unresolved_questions
                        or analysis.objective != base.objective
                    )
                )
                or (
                    initial and any(q.resolution is not None for q in analysis.unresolved_questions)
                )
            ):
                raise PolicyError(
                    "analyst changed original source, questions, answers or objective"
                )
            if any(
                q.blocking and q.resolution is None for q in analysis.unresolved_questions
            ) or any(r.needs_human_decision for r in analysis.requirements):
                state, reason = "AWAITING_CLARIFICATION", "material_unknown"
                if initial:
                    body = base.model_dump(mode="json")
                    body.update(
                        revision=base.revision + 1,
                        objective=analysis.objective,
                        title=title_from(analysis.objective),
                        source_statements=[
                            s.model_dump(mode="json") for s in analysis.source_statements
                        ],
                        requirements=[r.model_dump(mode="json") for r in analysis.requirements],
                        unresolved_questions=[
                            q.model_dump(mode="json") for q in analysis.unresolved_questions
                        ],
                    )
                    body["provenance"].update(
                        mode="model_proposal",
                        producer="proposal-engine-v1",
                        created_at=intent["created_at"],
                    )
                    candidate = seal_specification(body)
                    validate_scope(candidate, policy)
                break
            decomposition = runner.run(
                "work_decomposer",
                json.dumps({**payload, "analysis": analysis.model_dump(mode="json")}),
                policy,
                Decomposition,
            )
            body = base.model_dump(mode="json")
            body.update(
                revision=base.revision + 1,
                requirements=[r.model_dump(mode="json") for r in analysis.requirements],
                work_items=[w.model_dump(mode="json") for w in decomposition.work_items],
                dependencies=[d.model_dump(mode="json") for d in decomposition.dependencies],
                assumptions=[a.model_dump(mode="json") for a in decomposition.assumptions],
            )
            if initial:
                body.update(
                    objective=analysis.objective,
                    title=title_from(analysis.objective),
                    source_statements=[
                        s.model_dump(mode="json") for s in analysis.source_statements
                    ],
                    unresolved_questions=[
                        q.model_dump(mode="json") for q in analysis.unresolved_questions
                    ],
                )
            body["risk"]["tier"] = max(base.risk.tier, decomposition.risk_tier)
            body["risk"]["reasons"] = list(
                dict.fromkeys((*base.risk.reasons, *decomposition.risk_reasons))
            )
            body["provenance"].update(
                mode="model_proposal",
                producer="revision-engine-v1",
                created_at=intent["created_at"],
            )
            for work in body["work_items"]:
                work["risk_tier"] = max(work["risk_tier"], body["risk"]["tier"])
            candidate = seal_specification(body)
            # Lexical policy may raise, but never lower, the proposed risk.
            body["risk"]["tier"] = max(body["risk"]["tier"], risk_floor(candidate))
            for work in body["work_items"]:
                work["risk_tier"] = max(work["risk_tier"], body["risk"]["tier"])
            candidate = seal_specification(body)
            if initial:
                validate_scope(candidate, policy)
            else:
                validate_revision(base, candidate, answers, policy)
            review = runner.run(
                "specification_reviewer",
                json.dumps(
                    {
                        **payload,
                        "candidate": candidate.model_dump(mode="json"),
                        "review_target_digest": candidate.content_digest,
                        "output_instructions": (
                            "Echo review_target_digest exactly as the 64-character "
                            "specification_digest. Do not recompute it or put prose in that field. "
                            "Place every concern in findings. You cannot approve or lower risk."
                        ),
                    }
                ),
                policy,
                Review,
            )
            if review.specification_digest != candidate.content_digest:
                raise PolicyError("review digest mismatch")
            if any(f.blocking for f in review.findings):
                state, reason = "REVISION_REQUIRED", "review_blocker"
            else:
                proposal_ready(candidate, policy, clarifications=answers, review=review)
                state, reason = "PROPOSED", "reviewed_revision"
        except RunStopped:
            state, reason = "PAUSED", "provider_or_schema_hold"
        except ValidationError:
            # Completed provider outputs that fail composition are definite failures, not
            # concurrent unfinished role calls. Persist them without laundering a retry.
            state, reason = "REVISION_REQUIRED", "composed_schema_gate"
        except PolicyError:
            state, reason = "REVISION_REQUIRED", "deterministic_revision_gate"
        snapshot = PipelineResult.model_validate_json(
            json.dumps(
                {
                    "state": state,
                    "reason": reason,
                    "analysis": analysis.model_dump(mode="json") if analysis else None,
                    "specification": candidate.model_dump(mode="json") if candidate else None,
                    "review": review.model_dump(mode="json") if review else None,
                    "receipts": [receipt.model_dump(mode="json") for receipt in runner.receipts],
                }
            )
        )
        if state == "PAUSED" and not runner.cancelled:
            # Another activity owns an unfinished role intent. Never write a competing result.
            return snapshot
        with store.database.begin() as conn:
            store.put(conn, workspace, "revision_attempt", execution, attempt, snapshot)
        if state in {"PROPOSED", "PAUSED"} or reason in {
            "deterministic_revision_gate",
            "composed_schema_gate",
        }:
            break
    result = PipelineResult.model_validate_json(
        json.dumps(
            {
                "state": state,
                "reason": reason,
                "analysis": analysis.model_dump(mode="json") if analysis else None,
                "specification": candidate.model_dump(mode="json") if candidate else None,
                "review": review.model_dump(mode="json") if review else None,
                "receipts": [receipt.model_dump(mode="json") for receipt in runner.receipts],
            }
        )
    )
    with store.database.begin() as conn:
        if store.lock_specification(conn, workspace, identifier):
            raise PolicyError("cancelled before revision promotion")
        current = store.get(workspace, "specification", identifier, connection=conn)
        if current["content_digest"] != base.content_digest:
            raise Conflict("superseded during revision review")
        if candidate is not None and (
            result.state == "PROPOSED" or (initial and result.state == "AWAITING_CLARIFICATION")
        ):
            if initial:
                validate_scope(candidate, policy)
            else:
                validate_revision(base, candidate, load_clarifications(store, base, policy), policy)
            store.put(conn, workspace, "specification", identifier, candidate.revision, candidate)
            binding = canonical_digest(
                {
                    "specification": candidate.content_digest,
                    "policy": policy.model_dump(mode="json"),
                    "runner": "recorded-v1",
                }
            )
            store.put(conn, workspace, "analysis_result", binding, 1, result)
            store.put(conn, workspace, "analysis_runtime", binding, 1, configuration)
            store.put(
                conn,
                workspace,
                "analysis_index",
                identifier,
                candidate.revision,
                {"binding": binding, "content_digest": candidate.content_digest},
            )
            conn.execute(
                insert(outbox).values(
                    workspace=workspace,
                    dispatched=0,
                    workflow_id=f"product-ops-{identifier}-r{candidate.revision}",
                    payload=json.dumps(
                        {
                            "workspace": workspace,
                            "specification_id": identifier,
                            "content_digest": candidate.content_digest,
                        }
                    ),
                )
            )
        store.put(conn, workspace, "revision_result", execution, 1, result)
    return result
