"""Version 2 plan: exact issue and blocking-relation writes approved as one bounded batch."""

import json
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from agentic_product_ops.adapters.linear.offline import description
from agentic_product_ops.adapters.model.contracts import Review
from agentic_product_ops.domain.clarifications import ClarificationReceipt
from agentic_product_ops.domain.contracts import (
    ID,
    Contract,
    Digest,
    WorkSpecification,
    canonical_digest,
    unique,
)
from agentic_product_ops.policies.validation import (
    DocumentationPolicy,
    PolicyError,
    ServerPolicy,
    proposal_ready,
)
from agentic_product_ops.services.ticket_readiness import EXECUTION_POLICIES, EXECUTION_POLICY_V2

DELIVERY_READY_LABEL = "delivery-ready"


class ProviderBinding(Contract):
    local_id: ID
    provider_id: UUID


class LinearScope(Contract):
    organization_id: UUID
    actor_id: UUID
    teams: Annotated[tuple[ProviderBinding, ...], Field(min_length=1, max_length=20)]
    projects: Annotated[tuple[ProviderBinding, ...], Field(max_length=100)] = ()
    labels: Annotated[tuple[ProviderBinding, ...], Field(max_length=100)] = ()

    @model_validator(mode="after")
    def identifiers(self) -> Self:
        for bindings in (self.teams, self.projects, self.labels):
            unique(tuple(b.local_id for b in bindings), "local scope binding")
            unique(tuple(str(b.provider_id) for b in bindings), "provider scope binding")
        return self


class NativeOperation(Contract):
    kind: Literal["issue_create", "relation_create"]
    operation_key: Digest
    target_id: UUID
    work_item_id: ID
    team_id: ID
    payload: Annotated[str, Field(min_length=1, max_length=65000)]
    prerequisite_keys: tuple[Digest, ...]
    request_digest: Digest

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.request_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"request_digest"})
        ):
            raise ValueError("native operation digest mismatch")
        if self.target_id.version != 4:
            raise ValueError("provider target requires UUID v4 format")
        return self


class NativePlan(Contract):
    schema_version: Literal["2"] = "2"
    specification_digest: Digest
    workspace_id: ID
    scope: LinearScope
    publication_generation: Literal[1] = 1
    operations: Annotated[tuple[NativeOperation, ...], Field(min_length=1, max_length=20)]
    content_digest: Digest

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.content_digest != canonical_digest(
            self.model_dump(mode="json", exclude={"content_digest"})
        ):
            raise ValueError("native plan digest mismatch")
        seen: set[str] = set()
        unique(tuple(str(o.target_id) for o in self.operations), "provider target")
        for operation in self.operations:
            if operation.operation_key in seen or not set(operation.prerequisite_keys) <= seen:
                raise ValueError("duplicate or unordered native operation")
            seen.add(operation.operation_key)
        return self


def ticket_rendering(
    spec: WorkSpecification, policy: ServerPolicy, scope: LinearScope
) -> tuple[str, bool, str | None]:
    """Ticket format, execution details and the delivery label ID, if this work is handed off.

    Delivery OS picks up only tickets carrying the label (pickup contract v1). It is applied
    only when this policy allows handoff for the specification's risk tier, and only if the
    trusted scope binds it, so it is part of the exact plan a person approves.
    """
    label = next(
        (str(b.provider_id) for b in scope.labels if b.local_id == DELIVERY_READY_LABEL), None
    )
    delivery_label = label if spec.risk.tier in policy.handoff_tiers else None
    # A documentation-lane handoff needs the lines Delivery OS's pull intake reads. Its policy
    # version is the capability digest, so format v2 follows the label instead. PER-7's plan
    # bound no label and keeps its v1 bytes.
    ticket_format = (
        "v2"
        if policy.version == EXECUTION_POLICY_V2
        or (isinstance(policy, DocumentationPolicy) and delivery_label)
        else "v1"
    )
    return ticket_format, policy.version in EXECUTION_POLICIES, delivery_label


def build_native_plan(
    spec: WorkSpecification,
    policy: ServerPolicy,
    scope: LinearScope,
    *,
    clarifications: tuple[ClarificationReceipt, ...] = (),
    review: Review | None = None,
    repository_label: str | None = None,
) -> NativePlan:
    proposal_ready(spec, policy, clarifications=clarifications, review=review)
    ticket_format, execution_details, delivery_label = ticket_rendering(spec, policy, scope)
    teams = {b.local_id: str(b.provider_id) for b in scope.teams}
    projects = {b.local_id: str(b.provider_id) for b in scope.projects}
    labels = {b.local_id: str(b.provider_id) for b in scope.labels}
    operations: list[NativeOperation] = []

    def key(kind: str, identity: str) -> str:
        return canonical_digest(
            [policy.workspace_id, str(spec.specification_id), spec.revision, kind, identity, 1]
        )

    def target(operation_key: str) -> str:
        # Stable digest-derived identifier with provider-required UUID v4 version/variant bits.
        # This is an identity, not a random secret or an exactly-once guarantee.
        return str(UUID(bytes=bytes.fromhex(operation_key[:32]), version=4))

    def append(
        kind: str,
        identity: str,
        work: str,
        team: str,
        payload: dict[str, object],
        prerequisites: tuple[str, ...],
    ) -> NativeOperation:
        operation_key = key(kind, identity)
        body = {
            "kind": kind,
            "operation_key": operation_key,
            "target_id": target(operation_key),
            "work_item_id": work,
            "team_id": team,
            "payload": json.dumps(
                {**payload, "id": target(operation_key)}, sort_keys=True, separators=(",", ":")
            ),
            "prerequisite_keys": list(prerequisites),
        }
        operation = NativeOperation.model_validate_json(
            json.dumps({**body, "request_digest": canonical_digest(body)})
        )
        operations.append(operation)
        return operation

    issues: dict[str, NativeOperation] = {}
    for work in spec.work_items:
        if work.type == "epic":
            raise PolicyError(
                "epic-to-project mapping requires a separate approved product decision"
            )
        if (
            work.proposed_team_id not in teams
            or (work.proposed_project_id is not None and work.proposed_project_id not in projects)
            or not set(work.proposed_labels) <= labels.keys()
            or len(work.proposed_labels) > 10
        ):
            raise PolicyError("native provider scope incomplete")
        payload: dict[str, object] = {
            "teamId": teams[work.proposed_team_id],
            "title": work.title,
            "description": description(
                spec,
                work,
                key("issue_create", work.local_id),
                execution_details=execution_details,
                ticket_format=ticket_format,
                repository_label=repository_label,
                handoff=delivery_label is not None,
            ).replace(
                "Generated by Agentic Product Ops (offline)", "Generated by Agentic Product Ops"
            ),
            "labelIds": [labels[label] for label in work.proposed_labels]
            + ([delivery_label] if delivery_label else []),
            "useDefaultTemplate": False,
        }
        if work.proposed_project_id:
            payload["projectId"] = projects[work.proposed_project_id]
        issues[work.local_id] = append(
            "issue_create", work.local_id, work.local_id, work.proposed_team_id, payload, ()
        )
    for dependency in spec.dependencies:
        before, after = issues[dependency.depends_on], issues[dependency.work_item_id]
        append(
            "relation_create",
            json.dumps([dependency.depends_on, dependency.work_item_id]),
            dependency.work_item_id,
            after.team_id,
            {
                "type": "blocks",
                "issueId": str(before.target_id),
                "relatedIssueId": str(after.target_id),
            },
            (before.operation_key, after.operation_key),
        )
    if len(operations) > policy.max_mutations:
        raise PolicyError("issues and relations exceed approved mutation budget")
    body = {
        "schema_version": "2",
        "specification_digest": spec.content_digest,
        "workspace_id": policy.workspace_id,
        "scope": scope.model_dump(mode="json"),
        "publication_generation": 1,
        "operations": [operation.model_dump(mode="json") for operation in operations],
    }
    return NativePlan.model_validate_json(
        json.dumps({**body, "content_digest": canonical_digest(body)})
    )
