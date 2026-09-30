"""Public listener with a single authenticated webhook route and no operator surface."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from agentic_product_ops.policies.validation import PolicyError
from agentic_product_ops.services.linear_events import LinearInbox, verify_event


def webhook_app(
    inbox: LinearInbox,
    secret: str,
    organization: UUID,
    teams: set[UUID],
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/webhooks/linear")
    async def receive(request: Request) -> dict[str, bool]:
        raw = bytearray()
        try:
            async with asyncio.timeout(3):
                async for chunk in request.stream():
                    raw.extend(chunk)
                    if len(raw) > 256000:
                        raise HTTPException(413, "payload too large")
            event = verify_event(
                bytes(raw),
                request.headers.get("linear-signature", ""),
                secret,
                organization,
                teams,
                clock(),
            )
        except PolicyError:
            raise HTTPException(401, "webhook rejected") from None
        except TimeoutError:
            raise HTTPException(408, "request timeout") from None
        try:
            await asyncio.wait_for(run_in_threadpool(inbox.receive, event), timeout=1.5)
        except Exception:
            raise HTTPException(503, "durable inbox unavailable") from None
        return {"accepted": True}

    return app
