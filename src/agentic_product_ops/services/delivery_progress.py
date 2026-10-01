"""Delivery progress read back from Linear; informational only, it never grants authority.

Delivery OS reports progress as ticket comments carrying a hidden marker,
``<!-- delivery-progress:<key>:<status> -->`` with status ``in_progress``, ``done`` or
``blocked`` (its ADR-037). Product Ops reads the newest marker, falling back to the ticket's
status type, to show where published work stands.
"""

import re
from typing import Any

MARKER = re.compile(r"<!--\s*delivery-progress:[^\s>]*:(in_progress|done|blocked)\s*-->")
FROM_MARKER = {"in_progress": "IN_DELIVERY", "done": "DELIVERED", "blocked": "DELIVERY_BLOCKED"}


def ticket_progress(issue: dict[str, Any]) -> tuple[str, str | None]:
    """Return the ticket's progress and, when blocked, Delivery OS's recorded reason."""
    reports = []
    for comment in (issue.get("comments") or {}).get("nodes", []):
        body = str(comment.get("body") or "")
        match = MARKER.search(body)
        if match:
            reports.append((str(comment.get("createdAt") or ""), match[1], body[match.end() :]))
    if reports:
        _, status, rest = max(reports)
        reason = rest.strip()[:300] or None if status == "blocked" else None
        return FROM_MARKER[status], reason
    state = issue.get("state") or {}
    kind, name = state.get("type"), str(state.get("name", "")).casefold()
    if kind == "completed":
        return "DELIVERED", None
    if kind == "canceled":
        return "CANCELED", None
    if kind == "started":
        return ("IN_REVIEW" if "review" in name else "IN_DELIVERY"), None
    return "NOT_STARTED", None


def delivery_progress(issues: list[dict[str, Any]]) -> dict[str, Any]:
    tickets = []
    for issue in issues:
        progress, reason = ticket_progress(issue)
        tickets.append(
            {"identifier": issue.get("identifier"), "progress": progress, "reason": reason}
        )
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
