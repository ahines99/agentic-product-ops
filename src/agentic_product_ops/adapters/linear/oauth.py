"""PKCE authorization and encrypted token rotation; every uncertain exchange holds."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx

from agentic_product_ops.adapters.identity.vault import SecretVault, secret_json
from agentic_product_ops.adapters.persistence.store import Missing, Store
from agentic_product_ops.domain.contracts import canonical_digest
from agentic_product_ops.policies.validation import PolicyError


class LinearOAuth:
    def __init__(
        self,
        store: Store,
        vault: SecretVault,
        *,
        workspace: str,
        client_id: str,
        redirect_uri: str,
        administrators: tuple[str, ...],
        scopes: tuple[str, ...] = ("read", "issues:create"),
        transport: httpx.MockTransport | None = None,
        allow_network: bool = False,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        uri = urlsplit(redirect_uri)
        if uri.scheme != "https" or not uri.netloc or uri.fragment or uri.username or uri.password:
            raise ValueError("fixed HTTPS callback required")
        if (
            not client_id
            or not administrators
            or "read" not in scopes
            or not set(scopes) <= {"read", "issues:create", "write"}
        ):
            raise ValueError("explicit client, administrator and scopes required")
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise ValueError("in-memory mock required")
        if transport is None and not allow_network:
            raise ValueError("OAuth network disabled")
        self.store, self.vault, self.workspace = store, vault, workspace
        self.client_id, self.redirect_uri, self.scopes = client_id, redirect_uri, scopes
        self.administrators, self.transport, self.clock = administrators, transport, clock

    def _admin(self, administrator: str) -> None:
        if administrator not in self.administrators:
            raise PolicyError("OAuth administrator required")

    def begin(self, *, administrator: str, session_id: str) -> str:
        self._admin(administrator)
        if not session_id or len(session_id) > 256:
            raise ValueError("authenticated session binding required")
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        key = canonical_digest({"state": state})
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        with self.store.database.begin() as conn:
            self.vault.put(
                conn, self.workspace, "oauth-" + key, 1, secret_json({"verifier": verifier})
            )
            self.store.put(
                conn,
                self.workspace,
                "oauth_state",
                key,
                1,
                {
                    "administrator": administrator,
                    "session_digest": canonical_digest(session_id),
                    "expires_at": (self.clock() + timedelta(minutes=10)).isoformat(),
                    "client_id": self.client_id,
                    "redirect_uri": self.redirect_uri,
                    "scopes": self.scopes,
                },
            )
        return "https://linear.app/oauth/authorize?" + urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "state": state,
                "scope": ",".join(self.scopes),
                "actor": "app",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )

    def _request(self, values: dict[str, str]) -> dict[str, Any]:
        try:
            with httpx.Client(
                transport=self.transport,
                trust_env=False,
                timeout=10,
                follow_redirects=False,
                headers={"Accept-Encoding": "identity"},
            ) as client:
                with client.stream(
                    "POST", "https://api.linear.app/oauth/token", data=values
                ) as response:
                    if response.status_code != 200 or response.headers.get("content-encoding"):
                        raise ValueError("token response held")
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        if len(content) + len(chunk) > 65536:
                            raise ValueError("token response exceeds bound")
                        content.extend(chunk)
                    value = json.loads(content)
            if not isinstance(value, dict) or value.get("token_type") != "Bearer":
                raise ValueError("token type invalid")
            if type(value.get("expires_in")) is not int or not 0 < value["expires_in"] <= 86400:
                raise ValueError("token lifetime invalid")
            for field in ("access_token", "refresh_token"):
                if not isinstance(value.get(field), str) or not 1 <= len(value[field]) <= 16000:
                    raise ValueError("missing token")
            scopes = value.get("scope")
            if isinstance(scopes, str):
                scopes = scopes.split()
            if not isinstance(scopes, list) or set(scopes) != set(self.scopes):
                raise ValueError("token scope differs from authorized request")
            return {
                "access_token": value["access_token"],
                "refresh_token": value["refresh_token"],
                "expires_at": (self.clock() + timedelta(seconds=value["expires_in"])).isoformat(),
                "scopes": sorted(scopes),
            }
        except Exception:
            raise PolicyError(
                "OAuth exchange held; reauthorization required after uncertainty"
            ) from None

    def exchange(self, *, administrator: str, session_id: str, state: str, code: str) -> str:
        self._admin(administrator)
        if not 1 <= len(state) <= 256 or not 1 <= len(code) <= 4096:
            raise PolicyError("OAuth callback invalid")
        key = canonical_digest({"state": state})
        with self.store.database.begin() as conn:
            self.store.lock_specification(conn, self.workspace, "oauth:" + key)
            record = self.store.get(self.workspace, "oauth_state", key, connection=conn)
            if (
                record["administrator"] != administrator
                or record["session_digest"] != canonical_digest(session_id)
                or self.clock() >= datetime.fromisoformat(record["expires_at"])
                or record["client_id"] != self.client_id
                or record["redirect_uri"] != self.redirect_uri
                or set(record["scopes"]) != set(self.scopes)
            ):
                raise PolicyError("OAuth state/session/configuration mismatch")
            try:
                self.store.get(self.workspace, "oauth_consumed", key, connection=conn)
                raise PolicyError("OAuth state already consumed or uncertain")
            except Missing:
                pass
            self.store.put(
                conn, self.workspace, "oauth_consumed", key, 1, {"at": self.clock().isoformat()}
            )
        secret = json.loads(self.vault.get(self.workspace, "oauth-" + key).get_secret_value())
        token = self._request(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "code": code,
                "code_verifier": secret["verifier"],
                "grant_type": "authorization_code",
            }
        )
        identity = "linear-" + key
        with self.store.database.begin() as conn:
            self.vault.put(conn, self.workspace, identity, 1, secret_json(token))
        return identity  # Opaque secret reference, never a token or workspace identity claim.

    def refresh(self, identity: str, *, administrator: str) -> None:
        self._admin(administrator)
        with self.store.database.begin() as conn:
            self.store.lock_specification(conn, self.workspace, "refresh:" + identity)
            record = self.store.get(self.workspace, "sealed_secret", identity, connection=conn)
            attempt = canonical_digest({"identity": identity, "revision": record["revision"]})
            try:
                self.store.get(self.workspace, "oauth_refresh_intent", attempt, connection=conn)
                raise PolicyError("refresh already attempted; hold for operator")
            except Missing:
                pass
            self.store.put(
                conn,
                self.workspace,
                "oauth_refresh_intent",
                attempt,
                1,
                {"at": self.clock().isoformat()},
            )
        old = json.loads(
            self.vault.get(self.workspace, identity, record["revision"]).get_secret_value()
        )
        token = self._request(
            {
                "client_id": self.client_id,
                "grant_type": "refresh_token",
                "refresh_token": old["refresh_token"],
            }
        )
        with self.store.database.begin() as conn:
            self.vault.put(
                conn, self.workspace, identity, record["revision"] + 1, secret_json(token)
            )
