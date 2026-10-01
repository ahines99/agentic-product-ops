"""Delivery progress read back from Linear; informational only, it never grants authority.

Delivery OS reports progress through ticket status and, when it stops, a ``delivery-blocked``
label (roadmap DO-4). Product Ops reads both, read-only, to show where published work stands.
"""

from typing import Any

DELIVERY_BLOCKED_LABEL = "delivery-blocked"


def ticket_progress(issue: dict[str, Any]) -> str:
    labels = {node["name"] for node in (issue.get("labels") or {}).get("nodes", [])}
    state = issue.get("state") or {}
    kind, name = state.get("type"), str(state.get("name", "")).casefold()
    if DELIVERY_BLOCKED_LABEL in labels:
        return "DELIVERY_BLOCKED"
    if kind == "completed":
        return "DELIVERED"
    if kind == "canceled":
        return "CANCELED"
    if kind == "started":
        return "IN_REVIEW" if "review" in name else "IN_DELIVERY"
    return "NOT_STARTED"


def delivery_progress(issues: list[dict[str, Any]]) -> dict[str, Any]:
    tickets = [
        {"identifier": issue.get("identifier"), "progress": ticket_progress(issue)}
        for issue in issues
    ]
    states = {ticket["progress"] for ticket in tickets}
    for overall in ("DELIVERY_BLOCKED", "IN_DELIVERY", "IN_REVIEW"):
        if overall in states:
            break
    else:
        overall = (
            "DELIVERED"
            if states and states <= {"DELIVERED", "CANCELED"} and "DELIVERED" in states
            else "NOT_STARTED"
        )
    return {
        "overall": overall,
        "tickets": tickets,
        "source": "linear_read_only",
        "grants_authority": False,
    }
