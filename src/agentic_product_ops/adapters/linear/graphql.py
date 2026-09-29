"""Bounded GraphQL request/response codec, exercised with httpx mock transport only."""

from __future__ import annotations

import json

import httpx

from agentic_product_ops.adapters.linear.offline import LinearOperation

MUTATION = """mutation ProductOpsCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) { success issue { id identifier title team { id } description } }
}"""


class UnknownOutcome(ValueError):
    """The caller must reconcile; never blindly repeat a mutation."""


class MockGraphQLAdapter:
    """Only accepts MockTransport; OAuth/network dispatch is deliberately not enabled."""

    def __init__(self, transport: httpx.MockTransport):
        if not isinstance(transport, httpx.MockTransport):
            raise ValueError("live transport disabled")
        self.client = httpx.Client(
            transport=transport,
            timeout=5,
            follow_redirects=False,
            base_url="https://api.linear.app",
        )

    def close(self) -> None:
        self.client.close()

    def create(self, operation: LinearOperation) -> str:
        # Variables serialize untrusted title/body as data, never as GraphQL query text.
        payload: dict[str, object] = {
            "title": operation.title,
            "description": operation.description,
            "teamId": operation.team_id,
        }
        if operation.project_id:
            payload["projectId"] = operation.project_id
        if operation.labels:
            payload["labelIds"] = operation.labels
        try:
            with self.client.stream(
                "POST", "/graphql", json={"query": MUTATION, "variables": {"input": payload}}
            ) as response:
                if response.status_code != 200:
                    raise UnknownOutcome("provider response uncertain")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 100_000:
                        raise UnknownOutcome("provider response exceeds bound")
            document = json.loads(raw)
            if document.get("errors"):
                raise UnknownOutcome("GraphQL error")
            result = document["data"]["issueCreate"]
            issue = result["issue"]
            if result["success"] is not True or (
                issue["title"],
                issue["team"]["id"],
                issue["description"],
            ) != (operation.title, operation.team_id, operation.description):
                raise UnknownOutcome("provider content mismatch")
            if not isinstance(issue["id"], str) or not 1 <= len(issue["id"]) <= 128:
                raise UnknownOutcome("provider identity malformed")
            return str(issue["id"])
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise UnknownOutcome("reconciliation required") from error
