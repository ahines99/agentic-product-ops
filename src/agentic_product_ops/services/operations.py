"""Bounded metadata-only retention manifests and redacted operational metric exports."""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select

from agentic_product_ops.adapters.model.contracts import RunReceipt
from agentic_product_ops.adapters.persistence.store import Store, artifacts
from agentic_product_ops.domain.contracts import canonical_digest


def artifact_manifest(store: Store, workspace: str, *, now: datetime) -> dict[str, Any]:
    with store.database.connect() as conn:
        rows = (
            conn.execute(
                select(
                    artifacts.c.kind,
                    artifacts.c.identity,
                    artifacts.c.revision,
                    artifacts.c.digest,
                    artifacts.c.created_at,
                )
                .where(artifacts.c.workspace == workspace)
                .limit(10_001)
            )
            .mappings()
            .all()
        )
    if len(rows) > 10_000:
        raise ValueError("manifest row bound exceeded; select a smaller retained workspace")
    entries = []
    for row in rows:
        ttl = store.retention.get(row["kind"])
        expired = (
            ttl is not None
            and (now - datetime.fromisoformat(row["created_at"])).total_seconds() >= ttl
        )
        entries.append({**row, "access": "expired" if expired else "retained"})
    entries.sort(key=lambda row: (row["kind"], row["identity"], row["revision"]))
    body = {
        "schema_version": "1",
        "workspace": workspace,
        "entries": entries,
        "policy": "Raw role read expiry retains immutable approved contracts and audit metadata.",
    }
    return {**body, "manifest_digest": canonical_digest(body)}


def operational_metrics(store: Store, workspace: str) -> dict[str, Any]:
    with store.database.connect() as conn:
        rows = (
            conn.execute(
                select(artifacts.c.kind, artifacts.c.identity, artifacts.c.revision)
                .where(
                    artifacts.c.workspace == workspace,
                    artifacts.c.kind.in_(
                        (
                            "role_result",
                            "native_dispatch_authority",
                            "native_publication_observation",
                        )
                    ),
                )
                .limit(10_001)
            )
            .mappings()
            .all()
        )
    if len(rows) > 10_000:
        raise ValueError("metric row bound exceeded")
    roles: list[dict[str, Any]] = []
    dispatches: dict[str, dict[str, Any]] = {}
    observations = []
    for row in rows:
        value = store.get(workspace, row["kind"], row["identity"], row["revision"])
        if row["kind"] == "role_result" and value.get("receipt"):
            receipt = RunReceipt.model_validate_json(json.dumps(value["receipt"]))
            roles.append(
                {
                    "run_id": str(receipt.run_id),
                    "context_id": str(receipt.context_id),
                    "role": receipt.role,
                    "status": receipt.status,
                    "elapsed_ms": receipt.elapsed_ms,
                    "input_tokens": receipt.usage.input_tokens if receipt.usage else None,
                    "output_tokens": receipt.usage.output_tokens if receipt.usage else None,
                    "estimated_cost": str(receipt.estimated_cost)
                    if receipt.estimated_cost is not None
                    else None,
                }
            )
        elif row["kind"] == "native_dispatch_authority":
            dispatches[row["identity"]] = value
        elif row["kind"] == "native_publication_observation":
            observations.append(value)
    publication = []
    for observed in observations:
        receipt = observed["evidence"]
        dispatch = dispatches.get(receipt["operation_key"])
        elapsed = (
            (
                datetime.fromisoformat(receipt["observed_at"])
                - datetime.fromisoformat(dispatch["dispatch_at"])
            ).total_seconds()
            * 1000
            if dispatch
            else None
        )
        publication.append(
            {
                "operation_key": receipt["operation_key"],
                "mode": observed["mode"],
                "status": receipt["status"],
                "dispatch_to_observation_ms": int(elapsed) if elapsed is not None else None,
            }
        )
    return {
        "schema_version": "1",
        "workspace": workspace,
        "role_run_count": len(roles),
        "role_runs_with_usage": sum(r["input_tokens"] is not None for r in roles),
        "role_runs": roles,
        "publication_observation_count": len(publication),
        "publication_observations": publication,
        "limitations": [
            "Role duration excludes human approval wait; publication observations are separate.",
            "Usage is provider-reported; configured-rate cost estimates are not billing evidence.",
            "Repeated reconciliation observations are not additional mutations.",
            "No prompt, response, credential, issue title or free-form error is exported.",
        ],
    }
