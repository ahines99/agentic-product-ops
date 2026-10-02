"""Opt-in loopback console with expiring, one-use browser bootstrap and scoped sessions."""

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from importlib.resources import files
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import Field, SecretStr

from agentic_product_ops.domain.contracts import Contract

COOKIE = "apo_local_session"
SAFE_READS = {"review", "plan", "tickets", "state", "documentation-lane"}
SAFE_WRITES = {"approve", "reject", "clarifications"}
# Publishing from the browser is allowed only when the profile enables publication. The server
# still rechecks the exact approval, grant, scope, source and budget at every write. The
# documentation-lane decision rides with publication (ADR-029); other risk changes stay out.
PUBLICATION_WRITES = {"publish", "reconcile", "documentation-lane"}


class Exchange(Contract):
    code: Annotated[str, Field(min_length=40, max_length=128)]


@dataclass
class Session:
    credential: SecretStr
    expires: float


class BrowserSessions:
    """Memory-only browser authority; service restart intentionally signs browsers out."""

    def __init__(self, port: int, *, publication: bool = False):
        self.origin = f"http://127.0.0.1:{port}"
        self.writes = SAFE_WRITES | (PUBLICATION_WRITES if publication else set())
        self.pending: dict[str, Session] = {}
        self.sessions: dict[str, Session] = {}
        self.lock = threading.Lock()

    @staticmethod
    def digest(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def _prune(self) -> None:
        now = time.monotonic()
        for records in (self.pending, self.sessions):
            for key in list(records):
                if records[key].expires <= now:
                    records.pop(key)

    def launch(self, credential: str) -> str:
        with self.lock:
            self._prune()
            if len(self.pending) >= 8 or len(self.sessions) >= 16:
                raise HTTPException(429, "close an existing local session first")
            code = secrets.token_urlsafe(32)
            self.pending[self.digest(code)] = Session(SecretStr(credential), time.monotonic() + 60)
            return self.origin + "/#launch=" + code

    def exchange(self, code: str) -> str:
        with self.lock:
            self._prune()
            record = self.pending.pop(self.digest(code), None)
            if record is None or len(self.sessions) >= 16:
                raise HTTPException(401, "local launch link expired or already used")
            token = secrets.token_urlsafe(32)
            self.sessions[self.digest(token)] = Session(record.credential, time.monotonic() + 3600)
            return token

    def same_origin(self, request: Request) -> None:
        if (
            request.headers.get("origin") != self.origin
            or request.headers.get("x-product-ops-ui") != "1"
        ):
            raise HTTPException(403, "same-origin local console request required")

    def credential(self, request: Request) -> str:
        # Origin is required for writes. Fetch supplies a custom header for every read too.
        if request.method != "GET":
            self.same_origin(request)
        if request.headers.get("x-product-ops-ui") != "1":
            raise HTTPException(403, "local console request required")
        if request.headers.get("sec-fetch-site") not in (None, "same-origin"):
            raise HTTPException(403, "cross-site console request denied")
        path = request.url.path.strip("/").split("/")
        allowed = (
            (request.method == "POST" and path == ["v1", "intakes", "prompts"])
            or (request.method == "GET" and path == ["v1", "local", "status"])
            or (
                len(path) in (3, 4)
                and path[:2] == ["v1", "specifications"]
                and (
                    (request.method == "GET" and (len(path) == 3 or path[3] in SAFE_READS))
                    or (request.method == "POST" and len(path) == 4 and path[3] in self.writes)
                )
            )
        )
        if not allowed:
            raise HTTPException(403, "browser session cannot perform this operation")
        with self.lock:
            self._prune()
            record = self.sessions.get(self.digest(request.cookies.get(COOKIE, "")))
            if record is None:
                raise HTTPException(401, "open a new local operator session")
            return record.credential.get_secret_value()


def mount_console(app: FastAPI, sessions: BrowserSessions) -> None:
    @app.middleware("http")
    async def browser_boundary(request: Request, call_next: object) -> Response:
        from collections.abc import Awaitable, Callable
        from typing import cast

        if request.headers.get("host") != sessions.origin.removeprefix("http://"):
            return Response("Local host denied", status_code=403)
        response = await cast(Callable[[Request], Awaitable[Response]], call_next)(request)
        response.headers.update(
            {
                "Content-Security-Policy": "default-src 'none'; script-src 'self'; "
                "style-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'self'",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            }
        )
        return response

    @app.get("/", include_in_schema=False)
    def page() -> Response:
        return asset("index.html", "text/html")

    def asset(name: str, media_type: str) -> Response:
        return Response(
            files("agentic_product_ops.api").joinpath("console", name).read_bytes(),
            media_type=media_type,
        )

    @app.get("/console.js", include_in_schema=False)
    def javascript() -> Response:
        return asset("console.js", "text/javascript")

    @app.get("/console.css", include_in_schema=False)
    def stylesheet() -> Response:
        return asset("console.css", "text/css")

    @app.post("/v1/local/session", include_in_schema=False)
    def exchange(body: Exchange, request: Request, response: Response) -> dict[str, bool]:
        sessions.same_origin(request)
        response.set_cookie(
            COOKIE,
            sessions.exchange(body.code),
            httponly=True,
            samesite="strict",
            max_age=3600,
            path="/",
        )
        return {"connected": True}

    @app.post("/v1/local/logout", include_in_schema=False)
    def logout(request: Request, response: Response) -> dict[str, bool]:
        sessions.same_origin(request)
        with sessions.lock:
            sessions.sessions.pop(sessions.digest(request.cookies.get(COOKIE, "")), None)
        response.delete_cookie(COOKIE, path="/")
        return {"connected": False}
