"""Find or create one team label by name, idempotently, through the single Linear write gate."""

from typing import Any
from uuid import UUID

from agentic_product_ops.adapters.linear.native_graphql import NativeGraphQLAdapter
from agentic_product_ops.domain.contracts import canonical_digest
from agentic_product_ops.policies.validation import PolicyError

LABEL_QUERY = (
    "query ProductOpsLabel($team: ID!, $name: String!) { issueLabels(first: 10, filter: "
    "{ name: { eq: $name }, team: { id: { eq: $team } } }) { nodes { id name team { id } } } }"
)


def label_identity(team_id: UUID, name: str) -> UUID:
    """Deterministic UUID v4-format identity, so an uncertain create can be retried safely."""
    digest = canonical_digest({"team": str(team_id), "label": name})
    return UUID(bytes=bytes.fromhex(digest[:32]), version=4)


def _find(adapter: NativeGraphQLAdapter, team_id: UUID, name: str) -> UUID | None:
    nodes: list[dict[str, Any]] = adapter._query(LABEL_QUERY, {"team": str(team_id), "name": name})[
        "issueLabels"
    ]["nodes"]
    matches = [
        n for n in nodes if n["name"] == name and (n["team"] or {}).get("id") == str(team_id)
    ]
    if len(matches) > 1:
        raise PolicyError("label name is ambiguous in this team")
    return UUID(matches[0]["id"]) if matches else None


def ensure_team_label(adapter: NativeGraphQLAdapter, team_id: UUID, name: str) -> UUID:
    if team_id not in {binding.provider_id for binding in adapter.scope.teams}:
        raise PolicyError("label team outside configured scope")
    existing = _find(adapter, team_id, name)
    if existing is not None:
        return existing
    identity = label_identity(team_id, name)
    try:
        result = adapter._query(
            "mutation ProductOpsLabelCreate($input: IssueLabelCreateInput!) { "
            "issueLabelCreate(input: $input) { success issueLabel { id name } } }",
            {"input": {"id": str(identity), "name": name, "teamId": str(team_id)}},
            write=True,
        )["issueLabelCreate"]
        if result["success"] is True and result["issueLabel"]["id"] == str(identity):
            return identity
    except Exception:  # noqa: S110 -- an uncertain create is settled by reading, below.
        pass
    confirmed = _find(adapter, team_id, name)
    if confirmed is None:
        raise PolicyError("label creation outcome requires reconciliation")
    return confirmed
