import json
import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from agentic_product_ops.adapters.persistence.encryption import StorageEncryption
from agentic_product_ops.adapters.persistence.store import (
    Missing,
    Store,
    artifacts,
    engine,
    metadata,
)
from agentic_product_ops.policies.validation import ServerPolicy
from agentic_product_ops.services.durable_analysis import analyze_specification
from agentic_product_ops.services.operations import artifact_manifest, operational_metrics


def test_encrypted_artifacts_retain_integrity_and_retention_metadata(tmp_path, valid):
    db = engine(f"sqlite:///{tmp_path / 'encrypted.db'}", testing=True)
    metadata.create_all(db)
    tick = [datetime.now(UTC)]
    keyring = StorageEncryption({"key-1": secrets.token_bytes(32)}, "key-1")
    store = Store(
        db,
        encryption=keyring,
        retention_seconds={"role_request": 60, "role_response": 60},
        clock=lambda: tick[0],
    )
    identity = str(valid.specification_id)
    with db.begin() as conn:
        store.put(conn, "offline-workspace", "specification", identity, 1, valid)
    result = analyze_specification(
        store, "offline-workspace", identity, valid.content_digest, ServerPolicy()
    )
    assert result.state == "PROPOSED"
    with db.connect() as conn:
        serialized = "\n".join(conn.execute(select(artifacts.c.payload)).scalars())
        role_id = conn.execute(
            select(artifacts.c.identity).where(artifacts.c.kind == "role_request")
        ).scalar()
    assert valid.source_statements[0].text not in serialized
    assert '"storage_version": 1' in serialized
    assert store.get("offline-workspace", "specification", identity) == valid.model_dump(
        mode="json"
    )
    metrics = operational_metrics(store, "offline-workspace")
    assert metrics["role_run_count"] == 3 and metrics["role_runs_with_usage"] == 3
    assert valid.title not in json.dumps(metrics)
    tick[0] += timedelta(seconds=61)
    with pytest.raises(Missing, match="retention"):
        store.get("offline-workspace", "role_request", role_id)
    assert store.get("offline-workspace", "specification", identity)
    manifest = artifact_manifest(store, "offline-workspace", now=tick[0])
    assert any(row["access"] == "expired" for row in manifest["entries"])
    assert valid.title not in json.dumps(manifest)
    wrong = Store(db, encryption=StorageEncryption({"other": secrets.token_bytes(32)}, "other"))
    with pytest.raises(ValueError, match="authentication"):
        wrong.get("offline-workspace", "specification", identity)
    with pytest.raises(ValueError, match="only raw"):
        Store(db, retention_seconds={"approval": 1})
    db.dispose()


def test_ciphertext_cannot_move_across_tenant_or_purpose():
    encryption = StorageEncryption({"key": secrets.token_bytes(32)}, "key")
    original = ("workspace", "specification", "id", 1)
    encoded = encryption.encode(original, {"private": "source text"})
    for other in (
        ("other", "specification", "id", 1),
        ("workspace", "approval", "id", 1),
        ("workspace", "specification", "id", 2),
    ):
        with pytest.raises(ValueError, match="authentication"):
            encryption.decode(other, encoded)
