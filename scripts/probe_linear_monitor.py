"""Explicit local acceptance: signed synthetic delivery, no real tickets or model calls."""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

from agentic_product_ops.pilot.monitor import LinearMonitor
from agentic_product_ops.pilot.runtime import PilotRuntime
from agentic_product_ops.services.spending import spending_summary


def main() -> None:
    directory = Path(".local/pilot")
    runtime = PilotRuntime(directory)
    try:
        settings = runtime.settings
        if settings.allow_paid_execution or settings.allow_publication:
            raise ValueError("acceptance requires paid execution and publication disabled")
        monitor = LinearMonitor(runtime)
        status = json.loads((directory / "monitor-health.json").read_text(encoding="utf-8"))
        if status.get("webhook_registered") is not True:
            raise ValueError("live webhook registration required")
        url = status["public_url"]
        if not url.startswith("https://") or not url.endswith(".trycloudflare.com/webhooks/linear"):
            raise ValueError("expected configured temporary tunnel")
        before = spending_summary(runtime.store, settings.workspace, settings.spend_authorization)
        now = datetime.now(UTC)
        enrolled = settings.linear_monitor_enrolled_at
        if enrolled is None:
            raise ValueError("enrollment required")
        # Pre-enrollment exercises persistence/exclusion without fetching a fake issue.
        identifier = str(uuid4())
        body = {
            "type": "Issue",
            "action": "create",
            "organizationId": str(settings.linear_scope.organization_id),
            "webhookTimestamp": int(now.timestamp() * 1000),
            "data": {
                "id": identifier,
                "teamId": str(settings.linear_scope.teams[0].provider_id),
                "createdAt": (enrolled - timedelta(days=1)).isoformat(),
                "updatedAt": now.isoformat(),
            },
        }
        raw = json.dumps(body).encode()
        signature = hmac.new(
            monitor.secrets["webhook_secret"].encode(), raw, hashlib.sha256
        ).hexdigest()
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=20) as client:
            results = [
                client.post(url, content=raw, headers={"linear-signature": signature}).status_code
                for _ in range(2)
            ]
            invalid = client.post(
                url, content=raw, headers={"linear-signature": "0" * 64}
            ).status_code
            hidden = {
                route: client.get(url.removesuffix("/webhooks/linear") + route).status_code
                for route in ("/v1/intakes", "/health", "/docs", "/openapi.json")
            }
        if results != [200, 200] or invalid != 401 or set(hidden.values()) != {404}:
            raise ValueError("public acceptance failed")
        after = spending_summary(runtime.store, settings.workspace, settings.spend_authorization)
        if before != after:
            raise ValueError("spending changed during no-execution probe")
        report = {
            "synthetic_signed_deliveries": results,
            "bad_signature": invalid,
            "operator_routes": hidden,
            "spending_unchanged": True,
            "synthetic_issue_id": identifier,
            "actual_linear_origin_event": False,
        }
        (directory / "monitor-probe.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report))
    finally:
        runtime.store.database.dispose()


if __name__ == "__main__":
    main()
