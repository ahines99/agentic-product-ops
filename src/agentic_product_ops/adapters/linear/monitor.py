"""Scoped bounded reconciliation and management of one explicitly owned webhook."""

import json
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from agentic_product_ops.adapters.linear.native_graphql import NativeGraphQLAdapter
from agentic_product_ops.policies.validation import PolicyError
from agentic_product_ops.services.linear_events import LinearEvent


def poll_events(
    adapter: NativeGraphQLAdapter, since: datetime, until: datetime, enrolled: datetime
) -> list[LinearEvent]:
    events: list[LinearEvent] = []
    cursor = None
    seen = set()
    for _ in range(20):
        result = adapter._query(
            "query ProductOpsReconcile($filter: IssueFilter!, $after: String) { "
            "organization { id } viewer { id } issues(first: 50, after: $after, "
            "filter: $filter, orderBy: updatedAt) { nodes { id createdAt updatedAt team { id } } "
            "pageInfo { hasNextPage endCursor } } }",
            {
                "after": cursor,
                "filter": {
                    "team": {"id": {"in": [str(t.provider_id) for t in adapter.scope.teams]}},
                    "createdAt": {"gte": enrolled.isoformat()},
                    "updatedAt": {"gte": since.isoformat(), "lte": until.isoformat()},
                },
            },
        )
        if result["organization"]["id"] != str(adapter.scope.organization_id) or result["viewer"][
            "id"
        ] != str(adapter.scope.actor_id):
            raise PolicyError("poll identity changed")
        for node in result["issues"]["nodes"]:
            event = LinearEvent.model_validate_json(
                json.dumps(
                    {
                        "issue_id": node["id"],
                        "organization_id": str(adapter.scope.organization_id),
                        "team_id": node["team"]["id"],
                        "action": "sync",
                        "created_at": node["createdAt"],
                        "updated_at": node["updatedAt"],
                    }
                )
            )
            if (
                event.team_id not in {t.provider_id for t in adapter.scope.teams}
                or not enrolled <= event.created_at <= until
                or not since <= event.updated_at <= until
            ):
                raise PolicyError("poll bounds violated")
            events.append(event)
        page = result["issues"]["pageInfo"]
        if page["hasNextPage"] is False:
            return events
        cursor = page["endCursor"]
        if not isinstance(cursor, str) or not cursor or len(cursor) > 512 or cursor in seen:
            raise PolicyError("poll cursor invalid")
        seen.add(cursor)
    raise PolicyError("poll page budget exhausted; cursor retained")


def configure_webhook(
    adapter: NativeGraphQLAdapter, identifier: UUID, url: str, secret: str
) -> dict[str, Any]:
    """Retry by owned deterministic ID after uncertainty, never create unrelated webhooks."""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc.endswith(".trycloudflare.com")
        or parsed.path != "/webhooks/linear"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or parsed.port
        or len(secret) < 32
    ):
        raise PolicyError("only the owned pilot tunnel route may be registered")
    if not adapter.allow_mutations or len(adapter.scope.teams) != 1:
        raise PolicyError("explicit single-team webhook management required")
    identity = adapter._query("query { organization { id } viewer { id admin } }", {})
    if (
        identity["organization"]["id"] != str(adapter.scope.organization_id)
        or identity["viewer"]["id"] != str(adapter.scope.actor_id)
        or identity["viewer"]["admin"] is not True
    ):
        raise PolicyError("webhook administrator scope mismatch")
    existing = adapter._query(
        "query { webhooks(first: 100) { nodes { id url enabled team { id } resourceTypes } "
        "pageInfo { hasNextPage } } }",
        {},
    )["webhooks"]
    if existing["pageInfo"]["hasNextPage"]:
        raise PolicyError("webhook inventory bound exceeded")
    owned = next((w for w in existing["nodes"] if w["id"] == str(identifier)), None)
    team = str(adapter.scope.teams[0].provider_id)
    if owned and (owned["team"]["id"] != team or owned["resourceTypes"] != ["Issue"]):
        raise PolicyError("owned webhook scope changed")
    if owned and owned["url"] == url and owned["enabled"]:
        return {"id": str(identifier), "enabled": True}
    if owned:
        result = adapter._query(
            "mutation ProductOpsWebhookUpdate($id: String!, $input: WebhookUpdateInput!) { "
            "webhookUpdate(id: $id, input: $input) { success webhook { id enabled } } }",
            {"id": str(identifier), "input": {"url": url, "enabled": True, "secret": secret}},
        )["webhookUpdate"]
    else:
        result = adapter._query(
            "mutation ProductOpsWebhookCreate($input: WebhookCreateInput!) { "
            "webhookCreate(input: $input) { success webhook { id enabled } } }",
            {
                "input": {
                    "id": str(identifier),
                    "label": "Agentic Product Ops local pilot",
                    "url": url,
                    "teamId": team,
                    "resourceTypes": ["Issue"],
                    "secret": secret,
                    "enabled": True,
                }
            },
        )["webhookCreate"]
    if result["success"] is not True or result["webhook"]["id"] != str(identifier):
        raise PolicyError("webhook management outcome requires reconciliation")
    return {"id": str(identifier), "enabled": result["webhook"]["enabled"]}
