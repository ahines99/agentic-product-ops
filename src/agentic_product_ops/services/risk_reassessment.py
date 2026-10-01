"""Explicit human risk reassessment creates a reviewed revision, never an approval."""

import json
from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import Field
from sqlalchemy import Connection, insert

from agentic_product_ops.adapters.identity.contracts import Principal
from agentic_product_ops.adapters.model.contracts import (
    PipelineResult,
    Review,
    RuntimeConfiguration,
)
from agentic_product_ops.adapters.model.runner import ModelProvider, RunStopped
from agentic_product_ops.adapters.persistence.store import Conflict, Missing, Store, outbox
from agentic_product_ops.domain.contracts import (
    Contract,
    Digest,
    Text,
    Tier,
    WorkSpecification,
    canonical_digest,
    seal_specification,
)
from agentic_product_ops.policies.validation import (
    PolicyError,
    ServerPolicy,
    proposal_ready,
    risk_floor,
)
from agentic_product_ops.services.authority import Authority
from agentic_product_ops.services.clarifications import load_clarifications
from agentic_product_ops.services.durable_analysis import (
    DurableRoleRunner,
    load_analysis,
    recorded_review,
)


class RiskCommand(Contract):
    revision: Annotated[int, Field(ge=1)]
    content_digest: Digest
    tier: Tier
    reason: Text


def reassess_risk(
    store: Store,
    authority: Authority,
    policy: ServerPolicy,
    configuration: RuntimeConfiguration,
    provider: ModelProvider,
    identifier: str,
    actor: Principal,
    command: RiskCommand,
    command_key: str,
) -> PipelineResult:
    workspace = policy.workspace_id
    RiskCommand.model_validate_json(command.model_dump_json())
    if actor.actor_id not in policy.security_approvers or "security_approver" not in actor.roles:
        raise PolicyError("explicit security operator required for risk reassessment")

    def prepare(conn: Connection) -> dict[str, Any]:
        if store.lock_specification(conn, workspace, identifier):
            raise PolicyError("cancelled")
        store.lock_specification(conn, workspace, "authority-dispatch")
        grant = authority.check(actor, conn)
        base = WorkSpecification.model_validate_json(
            json.dumps(store.get(workspace, "specification", identifier, connection=conn))
        )
        authority._scope(grant, base)
        if (base.revision, base.content_digest) != (command.revision, command.content_digest):
            raise Conflict("stale reassessment")
        recorded_review(store, workspace, base, policy)
        if command.tier == base.risk.tier:
            raise PolicyError("reassessment must change tier")
        body = base.model_dump(mode="json")
        body["revision"] += 1
        body["risk"].update(tier=command.tier, reasons=[command.reason])
        for work in body["work_items"]:
            work["risk_tier"] = command.tier
        candidate = seal_specification(body)
        if command.tier < risk_floor(candidate):
            raise PolicyError("human reassessment cannot lower deterministic risk floor")
        proposal_ready(candidate, policy, clarifications=load_clarifications(store, base, policy))
        return {
            "candidate": candidate.model_dump(mode="json"),
            "actor_id": actor.actor_id,
            "grant_digest": actor.grant_digest,
            "base_digest": base.content_digest,
            "command": command.model_dump(mode="json"),
            "recorded_at": datetime.now(UTC).isoformat(),
        }

    authority.check(actor)
    intent = store.command(
        workspace,
        actor.actor_id,
        command_key,
        {"action": "risk_reassessment", "id": identifier, "body": command.model_dump(mode="json")},
        prepare,
    )
    execution = canonical_digest(intent)
    try:
        return PipelineResult.model_validate_json(
            json.dumps(store.get(workspace, "risk_result", execution))
        )
    except Missing:
        pass
    if actor.grant_digest != intent["grant_digest"] or store.cancelled(workspace, identifier):
        raise PolicyError("reassessment authority changed or cancelled")
    if (
        store.get(workspace, "specification", identifier)["content_digest"]
        != command.content_digest
    ):
        raise Conflict("reassessment base was superseded")
    candidate = WorkSpecification.model_validate_json(json.dumps(intent["candidate"]))
    runner = DurableRoleRunner(
        store,
        workspace,
        candidate.content_digest,
        provider,
        configuration.budget,
        identifier,
        configuration.model,
    )
    review = None
    state, reason = "PAUSED", "risk_review_incomplete"
    try:
        review = runner.run(
            "specification_reviewer",
            json.dumps(
                {
                    "candidate": candidate.model_dump(mode="json"),
                    "human_risk_reassessment": intent,
                    "instruction": (
                        "Recheck the entire specification and proposed risk against source. "
                        "Human reassessment is evidence, not permission to ignore missing "
                        "requirements or ambiguity."
                    ),
                }
            ),
            policy,
            Review,
        )
        if review.specification_digest != candidate.content_digest:
            raise PolicyError("risk review digest mismatch")
        state = "REVISION_REQUIRED" if any(f.blocking for f in review.findings) else "PROPOSED"
        reason = (
            "risk_review_blocker" if state == "REVISION_REQUIRED" else "reviewed_risk_reassessment"
        )
    except RunStopped:
        pass
    except PolicyError:
        state, reason = "REVISION_REQUIRED", "risk_review_digest_mismatch"
    base = WorkSpecification.model_validate_json(
        json.dumps(store.get(workspace, "specification", identifier, command.revision))
    )
    previous = load_analysis(store, workspace, base, policy)
    result = PipelineResult.model_validate_json(
        json.dumps(
            {
                "state": state,
                "reason": reason,
                "analysis": previous.analysis.model_dump(mode="json")
                if previous.analysis
                else None,
                "specification": candidate.model_dump(mode="json"),
                "review": review.model_dump(mode="json") if review else None,
                "receipts": [r.model_dump(mode="json") for r in runner.receipts],
            }
        )
    )
    if state == "PAUSED" and not runner.cancelled:
        return result
    with store.database.begin() as conn:
        if store.lock_specification(conn, workspace, identifier):
            raise PolicyError("cancelled during risk review")
        store.lock_specification(conn, workspace, "authority-dispatch")
        authority.check(actor, conn)
        if actor.grant_digest != intent["grant_digest"]:
            raise PolicyError("reassessment identity changed")
        current = store.get(workspace, "specification", identifier, connection=conn)
        if current["content_digest"] != command.content_digest:
            raise Conflict("superseded during risk review")
        store.put(conn, workspace, "risk_reassessment", execution, 1, intent)
        store.put(conn, workspace, "risk_result", execution, 1, result)
        if result.state == "PROPOSED":
            proposal_ready(
                candidate,
                policy,
                clarifications=load_clarifications(store, base, policy),
                review=result.review,
            )
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
                {
                    "binding": binding,
                    "content_digest": candidate.content_digest,
                },
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
    return result
