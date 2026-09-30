"""Native Linear wire adapter; fixed queries, exact-ID reconciliation, no automatic writes."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any, Literal

import httpx
from pydantic import SecretStr

from agentic_product_ops.adapters.linear.graphql import UnknownOutcome
from agentic_product_ops.adapters.linear.native_plan import LinearScope, NativeOperation
from product_ops_handoff.linear_markdown import descriptions_match

ISSUE_FIELDS = """id title description team { id } project { id }
labels(first: 100) { nodes { id } pageInfo { hasNextPage } }"""
RELATION_FIELDS = "id type issue { id } relatedIssue { id }"


class NativeGraphQLAdapter:
    def __init__(
        self,
        scope: LinearScope,
        *,
        token: SecretStr,
        token_kind: Literal["oauth", "api_key"],
        scopes: tuple[str, ...],
        transport: httpx.MockTransport | None = None,
        allow_network: bool = False,
        allow_mutations: bool = False,
    ) -> None:
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise ValueError("mock transport required")
        if transport is None and not allow_network:
            raise ValueError("Linear network disabled")
        if (
            not token.get_secret_value()
            or token_kind not in {"oauth", "api_key"}
            or "read" not in scopes
        ):
            raise ValueError("explicit credential type and read scope required")
        self.scope, self.scopes = scope, scopes
        self.mode = "mock_transport" if transport else "live_provider"
        self.allow_mutations = allow_mutations or transport is not None
        self.last_request_id: str | None = None
        self.client = httpx.Client(
            base_url="https://api.linear.app",
            transport=transport,
            timeout=10,
            follow_redirects=False,
            trust_env=False,
            headers={
                "Authorization": ("Bearer " if token_kind == "oauth" else "")  # noqa: S105
                + token.get_secret_value(),
                "Accept-Encoding": "identity",
            },
        )

    def close(self) -> None:
        self.client.close()

    def _query(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        self.last_request_id = None
        deadline = time.monotonic() + 10
        try:
            body = json.dumps(
                {"query": query, "variables": variables}, separators=(",", ":")
            ).encode()
            if len(body) > 100_000:
                raise ValueError("request bound")
            with self.client.stream(
                "POST", "/graphql", content=body, headers={"Content-Type": "application/json"}
            ) as response:
                if response.status_code != 200 or response.headers.get("content-encoding"):
                    raise ValueError("provider unavailable")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    if len(raw) + len(chunk) > 256_000 or time.monotonic() >= deadline:
                        raise ValueError("response bound")
                    raw.extend(chunk)
                document = json.loads(raw)
                if document.get("errors") or not isinstance(document.get("data"), dict):
                    raise ValueError("provider errors")
                request_id = response.headers.get("x-request-id")
                if request_id is not None and (len(request_id) > 128 or not request_id.isascii()):
                    raise ValueError("invalid request ID")
                self.last_request_id = request_id
                result: dict[str, Any] = document["data"]
                return result
        except Exception:
            raise UnknownOutcome(
                "Linear outcome held; reconcile or obtain operator resolution"
            ) from None

    def preflight(self, operation: NativeOperation) -> None:
        identity = self._query("query ProductOpsIdentity { organization { id } viewer { id } }", {})
        if identity["organization"]["id"] != str(self.scope.organization_id) or identity["viewer"][
            "id"
        ] != str(self.scope.actor_id):
            raise UnknownOutcome("Linear tenant or actor mismatch")
        payload = json.loads(operation.payload)
        if operation.kind == "relation_create":
            if "write" not in self.scopes:
                raise UnknownOutcome("native relations require explicitly authorized write scope")
            # Both issue IDs are prerequisites verified by the governed publisher.
            return
        if not {"write", "issues:create"} & set(self.scopes):
            raise UnknownOutcome("issue-create capability missing")
        team = self._query(
            "query ProductOpsTeam($id: String!) { team(id: $id) { id organization { id } } }",
            {"id": payload["teamId"]},
        )["team"]
        expected = {b.local_id: str(b.provider_id) for b in self.scope.teams}
        if (
            payload["teamId"] != expected.get(operation.team_id)
            or team["id"] != payload["teamId"]
            or team["organization"]["id"] != str(self.scope.organization_id)
        ):
            raise UnknownOutcome("team metadata outside approved tenant")
        if payload.get("projectId"):
            project = self._query(
                "query ProductOpsProject($id: String!) { project(id: $id) { "
                "id teams(first: 100) { nodes { id } pageInfo { hasNextPage } } } }",
                {"id": payload["projectId"]},
            )["project"]
            if (
                project["id"] != payload["projectId"]
                or project["teams"]["pageInfo"]["hasNextPage"] is not False
                or payload["teamId"] not in {t["id"] for t in project["teams"]["nodes"]}
            ):
                raise UnknownOutcome("project metadata incomplete or outside approved team")
        for label_id in payload.get("labelIds", []):
            label = self._query(
                "query ProductOpsLabel($id: String!) { issueLabel(id: $id) { "
                "id organization { id } team { id } } }",
                {"id": label_id},
            )["issueLabel"]
            if (
                label["id"] != label_id
                or label["organization"]["id"] != str(self.scope.organization_id)
                or (label["team"] is not None and label["team"]["id"] != payload["teamId"])
            ):
                raise UnknownOutcome("label metadata outside approved scope")

    def _matches(self, operation: NativeOperation, observed: dict[str, Any]) -> bool:
        payload = json.loads(operation.payload)
        if observed.get("id") != str(operation.target_id):
            return False
        if operation.kind == "relation_create":
            return bool(
                observed["type"] == payload["type"]
                and observed["issue"]["id"] == payload["issueId"]
                and observed["relatedIssue"]["id"] == payload["relatedIssueId"]
            )
        return bool(
            observed["title"] == payload["title"]
            and descriptions_match(payload["description"], observed["description"])
            and observed["team"]["id"] == payload["teamId"]
            and (observed["project"]["id"] if observed["project"] else None)
            == payload.get("projectId")
            and observed["labels"]["pageInfo"]["hasNextPage"] is False
            and sorted(label["id"] for label in observed["labels"]["nodes"])
            == sorted(payload["labelIds"])
        )

    def create(self, operation: NativeOperation, before_dispatch: Callable[[], None]) -> str:
        if not self.allow_mutations:
            raise UnknownOutcome("Linear writes disabled")
        try:
            self.preflight(operation)
            if operation.kind == "issue_create":
                field, typename, object_field, fields = (
                    "issueCreate",
                    "IssueCreateInput",
                    "issue",
                    ISSUE_FIELDS,
                )
            else:
                field, typename, object_field, fields = (
                    "issueRelationCreate",
                    "IssueRelationCreateInput",
                    "issueRelation",
                    RELATION_FIELDS,
                )
            query = (
                f"mutation ProductOpsWrite($input: {typename}!) {{ "
                f"{field}(input: $input) {{ success {object_field} {{ {fields} }} }} }}"
            )
            before_dispatch()  # Recheck authority and time after metadata reads.
            value = self._query(query, {"input": json.loads(operation.payload)})[field]
            if value["success"] is not True or not self._matches(operation, value[object_field]):
                raise ValueError("mutation response mismatch")
            return str(operation.target_id)
        except Exception:
            raise UnknownOutcome("Linear write uncertain; do not repeat") from None

    def reconcile(self, operation: NativeOperation) -> str | None:
        try:
            self.preflight(operation)
            field, fields = (
                ("issue", ISSUE_FIELDS)
                if operation.kind == "issue_create"
                else ("issueRelation", RELATION_FIELDS)
            )
            value = self._query(
                f"query ProductOpsReconcile($id: String!) {{ {field}(id: $id) {{ {fields} }} }}",
                {"id": str(operation.target_id)},
            )[field]
            return (
                str(operation.target_id)
                if value is not None and self._matches(operation, value)
                else None
            )
        except Exception:
            return (
                None  # Absence, failed lookup, normalization or conflict never proves safe retry.
            )
