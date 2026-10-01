from agentic_product_ops.services.delivery_progress import delivery_progress, ticket_progress


def issue(kind="backlog", name="State", comments=()):
    return {
        "identifier": "PER-1",
        "state": {"type": kind, "name": name},
        "comments": {
            "nodes": [{"body": body, "createdAt": at} for at, body in comments],
        },
    }


def marker(status, rest=""):
    return f"<!-- delivery-progress:wf-1:{status} -->\n" + rest


def test_newest_delivery_marker_wins_and_carries_the_blocked_reason():
    assert ticket_progress(issue()) == ("NOT_STARTED", None)
    started = issue(comments=[("2026-10-01T01:00:00Z", marker("in_progress"))])
    assert ticket_progress(started) == ("IN_DELIVERY", None)
    blocked = issue(
        comments=[
            ("2026-10-01T01:00:00Z", marker("in_progress")),
            ("2026-10-01T02:00:00Z", marker("blocked", "Delivery OS: blocked. Reason: tier 3")),
            ("2026-10-01T03:00:00Z", "an unrelated human comment"),
        ]
    )
    progress, reason = ticket_progress(blocked)
    assert progress == "DELIVERY_BLOCKED" and "tier 3" in reason
    done = issue(comments=[("2026-10-01T04:00:00Z", marker("done"))])
    assert ticket_progress(done)[0] == "DELIVERED"
    # Without markers, the status type is used.
    assert ticket_progress(issue("started", "In Review"))[0] == "IN_REVIEW"
    assert ticket_progress(issue("completed"))[0] == "DELIVERED"


def test_overall_progress_and_no_authority():
    blocked = issue(comments=[("t", marker("blocked", "Reason: x"))])
    result = delivery_progress([issue("completed"), blocked])
    assert result["overall"] == "DELIVERY_BLOCKED" and result["grants_authority"] is False
    assert delivery_progress([issue("completed"), issue("canceled")])["overall"] == "DELIVERED"
    assert delivery_progress([])["overall"] == "NOT_STARTED"
