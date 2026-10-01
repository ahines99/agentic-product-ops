"""Durable aggregate spending reservations; ambiguous attempts never release their reservation.

A call with recorded provider usage counts at that usage priced at the authorization's
conservative rates, which are at or above real prices, so the cap still bounds actual spend from
above. A call without recorded usage keeps its full reservation (ADR-024).
"""

from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, select

from agentic_product_ops.adapters.model.contracts import ModelRequest, ModelResponse
from agentic_product_ops.adapters.model.runner import ModelProvider, RunStopped
from agentic_product_ops.adapters.persistence.store import Missing, Store, artifacts
from agentic_product_ops.domain.contracts import canonical_digest


def committed(
    store: Store,
    workspace: str,
    key: str,
    entry: dict[str, Any],
    terms: dict[str, Any] | None,
    connection: Connection | None = None,
) -> Decimal:
    """What one reservation counts against the cap: observed usage, or the whole reservation."""
    reserved = Decimal(entry["reserved"])
    if terms is None:
        return reserved
    try:
        usage = store.get(workspace, "spend_observation", key, connection=connection)
    except Missing:
        return reserved
    observed = (
        Decimal(usage["input_tokens"]) * Decimal(terms["input_rate"])
        + Decimal(usage["output_tokens"]) * Decimal(terms["output_rate"])
    ) / Decimal(1_000_000)
    return min(reserved, observed)


def spending_summary(store: Store, workspace: str, authorization: str) -> dict[str, Any]:
    with store.database.connect() as conn:
        keys: list[str] = list(
            conn.execute(
                select(artifacts.c.identity)
                .where(artifacts.c.workspace == workspace, artifacts.c.kind == "spend_reservation")
                .limit(10001)
            ).scalars()
        )
    if len(keys) > 10000:
        raise RunStopped("spending ledger bound")
    try:
        terms: dict[str, Any] | None = store.get(workspace, "spend_authorization", authorization)
    except Missing:
        terms = None
    reserved, settled, calls, observed, input_tokens, output_tokens = (
        Decimal(0),
        Decimal(0),
        0,
        0,
        0,
        0,
    )
    for key in keys:
        entry = store.get(workspace, "spend_reservation", key)
        if entry["authorization"] != authorization:
            continue
        calls += 1
        reserved += Decimal(entry["reserved"])
        settled += committed(store, workspace, key, entry, terms)
        try:
            usage = store.get(workspace, "spend_observation", key)
        except Missing:
            continue
        observed += 1
        input_tokens += usage["input_tokens"]
        output_tokens += usage["output_tokens"]
    return {
        "authorization": authorization,
        "reserved_usd": str(reserved),
        "committed_usd": str(settled),
        "reserved_calls": calls,
        "observed_calls": observed,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "actual_billing_verified": False,
    }


class SpendingProvider:
    def __init__(
        self,
        store: Store,
        workspace: str,
        authorization: str,
        provider: ModelProvider,
        *,
        model: str,
        maximum: Decimal,
        input_rate: Decimal,
        output_rate: Decimal,
        request_scope: str | None = None,
        request_maximum: Decimal | None = None,
    ) -> None:
        if any(not value.is_finite() or value <= 0 for value in (maximum, input_rate, output_rate)):
            raise ValueError("positive explicit spending authorization and rates required")
        if (request_scope is None) != (request_maximum is None) or (
            request_maximum is not None
            and (not request_maximum.is_finite() or not 0 < request_maximum <= maximum)
        ):
            raise ValueError(
                "a request allowance needs a scope and a positive limit within the cap"
            )
        # One request's allowance; exhausting it holds that request only (roadmap PO-8).
        self.request_scope, self.request_maximum = request_scope, request_maximum
        self.store, self.workspace, self.authorization = store, workspace, authorization
        self.provider, self.model = provider, model
        self.maximum, self.input_rate, self.output_rate = maximum, input_rate, output_rate
        self.terms = {
            "model": model,
            "maximum": str(maximum),
            "input_rate": str(input_rate),
            "output_rate": str(output_rate),
        }

    def complete(self, request: ModelRequest) -> ModelResponse:
        if request.model != self.model:
            raise RunStopped("spending authorization model mismatch")
        key = canonical_digest({"authorization": self.authorization, "run": str(request.run_id)})
        reserve = (
            Decimal(request.max_input_tokens) * self.input_rate
            + Decimal(request.max_output_tokens) * self.output_rate
        ) / Decimal(1_000_000)
        with self.store.database.begin() as conn:
            self.store.lock_specification(conn, self.workspace, "spend:" + self.authorization)
            try:
                terms = self.store.get(
                    self.workspace, "spend_authorization", self.authorization, connection=conn
                )
                if terms != self.terms:
                    raise RunStopped("spending authorization terms changed")
            except Missing:
                self.store.put(
                    conn, self.workspace, "spend_authorization", self.authorization, 1, self.terms
                )
                terms = self.terms
            rows: list[str] = list(
                conn.execute(
                    select(artifacts.c.identity)
                    .where(
                        artifacts.c.workspace == self.workspace,
                        artifacts.c.kind == "spend_reservation",
                    )
                    .limit(10001)
                )
                .scalars()
                .all()
            )
            if len(rows) > 10000:
                raise RunStopped("spending ledger bound")
            total, scoped = Decimal(0), Decimal(0)
            for identity in rows:
                entry = self.store.get(
                    self.workspace, "spend_reservation", identity, connection=conn
                )
                if entry["authorization"] == self.authorization:
                    if identity == key:
                        raise RunStopped("previously reserved inference cannot be repeated")
                    amount = committed(self.store, self.workspace, identity, entry, terms, conn)
                    total += amount
                    if self.request_scope is not None and entry.get("scope") == self.request_scope:
                        scoped += amount
            if total + reserve > self.maximum:
                raise RunStopped("aggregate authorized spending limit reached")
            if self.request_maximum is not None and scoped + reserve > self.request_maximum:
                raise RunStopped("request spending allowance reached")
            self.store.put(
                conn,
                self.workspace,
                "spend_reservation",
                key,
                1,
                {
                    "authorization": self.authorization,
                    "run_id": str(request.run_id),
                    "reserved": str(reserve),
                    "input_digest": request.input_digest,
                    **({"scope": self.request_scope} if self.request_scope else {}),
                },
            )
        response = self.provider.complete(request)
        with self.store.database.begin() as conn:
            self.store.put(
                conn,
                self.workspace,
                "spend_observation",
                key,
                1,
                {
                    "provider_request_id": response.usage.provider_request_id,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "reserved": str(reserve),
                    "actual_billing_verified": False,
                },
            )
        return response
