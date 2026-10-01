from agentic_product_ops.services.delivery_progress import delivery_progress, ticket_progress


def issue(kind, name="State", labels=()):
    return {
        "identifier": "PER-1",
        "state": {"type": kind, "name": name},
        "labels": {"nodes": [{"name": label} for label in labels]},
    }


def test_ticket_progress_from_status_and_blocked_label():
    assert ticket_progress(issue("backlog")) == "NOT_STARTED"
    assert ticket_progress(issue("started", "In Progress")) == "IN_DELIVERY"
    assert ticket_progress(issue("started", "In Review")) == "IN_REVIEW"
    assert ticket_progress(issue("completed")) == "DELIVERED"
    assert ticket_progress(issue("started", labels=("delivery-blocked",))) == "DELIVERY_BLOCKED"


def test_overall_progress_and_no_authority():
    blocked = delivery_progress(
        [issue("completed"), issue("backlog", labels=("delivery-blocked",))]
    )
    assert blocked["overall"] == "DELIVERY_BLOCKED" and blocked["grants_authority"] is False
    assert delivery_progress([issue("completed"), issue("canceled")])["overall"] == "DELIVERED"
    assert delivery_progress([issue("completed"), issue("backlog")])["overall"] == "NOT_STARTED"
    assert delivery_progress([])["overall"] == "NOT_STARTED"
