"""Read-only, fixed-query Linear source intake; issue text grants no authority."""

import json
import re
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field

from agentic_product_ops.adapters.linear.native_graphql import NativeGraphQLAdapter
from agentic_product_ops.domain.contracts import Contract, Timestamp, canonical_digest
from agentic_product_ops.policies.validation import PolicyError


def issue_reference(value: str) -> str:
    if value.startswith("https://"):
        url = urlsplit(value)
        if url.netloc != "linear.app" or url.query or url.fragment:
            raise ValueError("expected a Linear issue URL")
        match = re.fullmatch(
            r"/[^/]+/issue/([A-Za-z][A-Za-z0-9]*-[1-9][0-9]*)(?:/[^/]+)?", url.path
        )
        if match is None:
            raise ValueError("expected a Linear issue URL")
        value = match[1]
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*-[1-9][0-9]*", value):
        return value.upper()
    try:
        return str(UUID(value))
    except ValueError:
        raise ValueError("expected a Linear issue identifier, UUID or URL") from None


class LinearSource(Contract):
    issue_id: UUID
    identifier: Annotated[str, Field(max_length=128, pattern=r"^[A-Z][A-Z0-9]*-[1-9][0-9]*$")]
    team_id: UUID
    organization_id: UUID
    title: Annotated[str, Field(min_length=1, max_length=1024)]
    description: Annotated[str, Field(max_length=14000)]
    updated_at: Timestamp

    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))

    def text(self) -> str:
        return f"Linear issue {self.identifier}\n{self.title}\n\n{self.description}"


class LinearIssueReader:
    def __init__(self, adapter: NativeGraphQLAdapter):
        self.adapter = adapter

    def read(self, reference: str) -> LinearSource:
        reference = issue_reference(reference)
        data = self.adapter._query(
            "query ProductOpsSource($id: String!) { organization { id } viewer { id } "
            "issue(id: $id) { id identifier title description updatedAt "
            "team { id organization { id } } } }",
            {"id": reference},
        )
        try:
            issue = data["issue"]
            scope = self.adapter.scope
            if (
                data["organization"]["id"] != str(scope.organization_id)
                or data["viewer"]["id"] != str(scope.actor_id)
                or issue["team"]["organization"]["id"] != str(scope.organization_id)
                or issue["team"]["id"] not in {str(t.provider_id) for t in scope.teams}
                or reference not in {issue["id"], issue["identifier"]}
            ):
                raise ValueError("source scope mismatch")
            return LinearSource.model_validate_json(
                json.dumps(
                    {
                        "issue_id": issue["id"],
                        "identifier": issue["identifier"],
                        "team_id": issue["team"]["id"],
                        "organization_id": data["organization"]["id"],
                        "title": issue["title"],
                        "description": "" if issue["description"] is None else issue["description"],
                        "updated_at": issue["updatedAt"],
                    }
                )
            )
        except (ValueError, KeyError, TypeError):
            raise PolicyError("Linear source is unavailable, malformed or outside scope") from None


def repository_name(source: LinearSource, explicit: str | None) -> str:
    declared: list[str] = re.findall(
        r"^[ \t]*(?:Repository|Repo):[ \t]*(.*?)[ \t]*$", source.description, re.M | re.I
    )
    values = ([explicit] if explicit is not None else []) + declared
    if not values or len(set(values)) != 1:
        raise PolicyError("one unambiguous repository name required")
    name = values[0]
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", name) or name.endswith("."):
        raise PolicyError("repository name must be a single directory name")
    return name
