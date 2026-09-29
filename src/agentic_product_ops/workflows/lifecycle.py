"""Explicit transition graph and guarded commands, with terminal cancellation."""

from enum import StrEnum

from pydantic import Field

from agentic_product_ops.domain.contracts import Contract, Digest, WorkSpecification
from agentic_product_ops.policies.validation import (
    PolicyError,
    ServerPolicy,
    blocking_findings,
    proposal_ready,
)


class State(StrEnum):
    RECEIVED = "RECEIVED"
    NORMALIZED = "NORMALIZED"
    REQUIREMENTS_DRAFTED = "REQUIREMENTS_DRAFTED"
    AWAITING_CLARIFICATION = "AWAITING_CLARIFICATION"
    CONTEXT_GATHERED = "CONTEXT_GATHERED"
    WORK_DECOMPOSED = "WORK_DECOMPOSED"
    INDEPENDENT_SPEC_REVIEW = "INDEPENDENT_SPEC_REVIEW"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    PROPOSED = "PROPOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    LINEAR_PUBLISHING = "LINEAR_PUBLISHING"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    PUBLISHED = "PUBLISHED"
    HANDOFF_READY = "HANDOFF_READY"
    CANCELLED = "CANCELLED"


EDGES: dict[State, frozenset[State]] = {
    State.RECEIVED: frozenset({State.NORMALIZED}),
    State.NORMALIZED: frozenset({State.REQUIREMENTS_DRAFTED}),
    State.REQUIREMENTS_DRAFTED: frozenset({State.AWAITING_CLARIFICATION, State.CONTEXT_GATHERED}),
    State.AWAITING_CLARIFICATION: frozenset({State.CONTEXT_GATHERED}),
    State.CONTEXT_GATHERED: frozenset({State.WORK_DECOMPOSED}),
    State.WORK_DECOMPOSED: frozenset({State.INDEPENDENT_SPEC_REVIEW}),
    State.INDEPENDENT_SPEC_REVIEW: frozenset({State.REVISION_REQUIRED, State.PROPOSED}),
    State.REVISION_REQUIRED: frozenset({State.INDEPENDENT_SPEC_REVIEW}),
    State.PROPOSED: frozenset({State.AWAITING_APPROVAL}),
    State.AWAITING_APPROVAL: frozenset({State.APPROVED, State.REJECTED, State.EXPIRED}),
    State.APPROVED: frozenset({State.LINEAR_PUBLISHING, State.EXPIRED}),
    State.LINEAR_PUBLISHING: frozenset({State.RECONCILIATION_REQUIRED, State.PUBLISHED}),
    State.RECONCILIATION_REQUIRED: frozenset({State.LINEAR_PUBLISHING, State.PUBLISHED}),
    State.PUBLISHED: frozenset({State.HANDOFF_READY}),
}


class Lifecycle(Contract):
    state: State
    content_digest: Digest
    revision_loops: int = Field(default=0, ge=0, le=2)


def transition(
    current: Lifecycle, target: State, spec: WorkSpecification, policy: ServerPolicy
) -> Lifecycle:
    """Foundation transitions only. Publication states require a future durable service."""
    WorkSpecification.model_validate_json(spec.model_dump_json())
    if current.content_digest != spec.content_digest:
        raise PolicyError("lifecycle bound to different content")
    terminal = {State.REJECTED, State.EXPIRED, State.HANDOFF_READY, State.CANCELLED}
    if current.state in terminal:
        raise PolicyError("terminal state")
    if target == State.CANCELLED:
        return Lifecycle(state=target, content_digest=spec.content_digest)
    if target not in EDGES.get(current.state, frozenset()):
        raise PolicyError("illegal transition")
    if target in {State.APPROVED, State.LINEAR_PUBLISHING, State.PUBLISHED, State.HANDOFF_READY}:
        raise PolicyError("durable authenticated transition service is not implemented")
    if current.state == State.AWAITING_CLARIFICATION:
        raise PolicyError("authenticated clarification service is not implemented")
    if target in {
        State.CONTEXT_GATHERED,
        State.WORK_DECOMPOSED,
        State.PROPOSED,
        State.AWAITING_APPROVAL,
    }:
        proposal_ready(spec, policy)
    if target == State.AWAITING_CLARIFICATION and not blocking_findings(spec):
        raise PolicyError("no clarification required")
    loops = current.revision_loops + (current.state == State.REVISION_REQUIRED)
    if loops > 2:
        raise PolicyError("revision budget exhausted")
    return Lifecycle(state=target, content_digest=spec.content_digest, revision_loops=loops)
