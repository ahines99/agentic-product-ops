"""Independent reference persistence; real delivery uses the stateless public verifier."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from product_ops_handoff.verifier import HandoffVerifier
from product_ops_handoff.verifier import digest as digest


class ReferenceConsumer(HandoffVerifier):
    def __init__(
        self,
        database_path: Path,
        *,
        keys: Mapping[tuple[str, str], Ed25519PublicKey],
        workspace: str,
        teams: tuple[str, ...],
        repositories: tuple[str, ...],
        policy_versions: tuple[str, ...],
        allow_mock_transport: bool = False,
    ) -> None:
        super().__init__(
            keys=keys,
            workspace=workspace,
            teams=teams,
            repositories=repositories,
            policy_versions=policy_versions,
            allow_mock_transport=allow_mock_transport,
        )
        if database_path.is_symlink():
            raise ValueError("consumer database cannot be a link")
        self.database = sqlite3.connect(database_path)
        existing = {
            row[0]
            for row in self.database.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if existing - {"delivery_intakes", "delivery_heads", "delivery_work_items"}:
            self.database.close()
            raise ValueError("reference consumer requires its own database")
        self.database.executescript("""
            CREATE TABLE IF NOT EXISTS delivery_intakes (
              issuer TEXT NOT NULL, specification_id TEXT NOT NULL, revision INTEGER NOT NULL,
              specification_digest TEXT NOT NULL, envelope_digest TEXT NOT NULL,
              original_bytes BLOB NOT NULL,
              PRIMARY KEY (issuer, specification_id, revision));
            CREATE TABLE IF NOT EXISTS delivery_heads (
              issuer TEXT NOT NULL, specification_id TEXT NOT NULL, revision INTEGER NOT NULL,
              specification_digest TEXT NOT NULL, PRIMARY KEY (issuer, specification_id));
            CREATE TABLE IF NOT EXISTS delivery_work_items (
              issuer TEXT NOT NULL, specification_id TEXT NOT NULL, revision INTEGER NOT NULL,
              local_id TEXT NOT NULL, provider_id TEXT NOT NULL, approved_digest TEXT NOT NULL,
              status TEXT NOT NULL,
              PRIMARY KEY (issuer, specification_id, revision, local_id));
            CREATE TRIGGER IF NOT EXISTS delivery_intakes_no_update
              BEFORE UPDATE ON delivery_intakes
              BEGIN SELECT RAISE(ABORT, 'immutable intake'); END;
            CREATE TRIGGER IF NOT EXISTS delivery_intakes_no_delete
              BEFORE DELETE ON delivery_intakes
              BEGIN SELECT RAISE(ABORT, 'immutable intake'); END;
        """)

    def close(self) -> None:
        self.database.close()

    def consume(self, raw: bytes, *, expected_digest: str, now: datetime) -> dict[str, Any]:
        payload = self.verify(raw, expected_digest=expected_digest, now=now)
        spec = payload["specification"]
        issuer, identity, revision = payload["issuer"], spec["specification_id"], spec["revision"]
        raw_digest = hashlib.sha256(raw).hexdigest()
        with self.database:
            self.database.execute("BEGIN IMMEDIATE")
            head = self.database.execute(
                "SELECT revision, specification_digest FROM delivery_heads "
                "WHERE issuer=? AND specification_id=?",
                (issuer, identity),
            ).fetchone()
            if head and (
                revision < head[0] or (revision == head[0] and expected_digest != head[1])
            ):
                raise ValueError("superseded or conflicting approved revision")
            existing = self.database.execute(
                "SELECT envelope_digest FROM delivery_intakes "
                "WHERE issuer=? AND specification_id=? AND revision=?",
                (issuer, identity, revision),
            ).fetchone()
            if existing:
                if existing[0] != raw_digest:
                    raise ValueError("immutable intake revision conflict")
                return {
                    "state": "ALREADY_ACCEPTED",
                    "approved_digest": expected_digest,
                    "revision": revision,
                }
            self.database.execute(
                "INSERT INTO delivery_intakes VALUES (?, ?, ?, ?, ?, ?)",
                (issuer, identity, revision, expected_digest, raw_digest, raw),
            )
            self.database.execute(
                "INSERT INTO delivery_heads VALUES (?, ?, ?, ?) "
                "ON CONFLICT(issuer, specification_id) "
                "DO UPDATE SET revision=excluded.revision, "
                "specification_digest=excluded.specification_digest",
                (issuer, identity, revision, expected_digest),
            )
            self.database.execute(
                "UPDATE delivery_work_items SET status='SUPERSEDED' "
                "WHERE issuer=? AND specification_id=? AND revision<?",
                (issuer, identity, revision),
            )
            for operation in payload["plan"]["operations"]:
                if operation["kind"] == "issue_create":
                    self.database.execute(
                        "INSERT INTO delivery_work_items VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            issuer,
                            identity,
                            revision,
                            operation["work_item_id"],
                            operation["target_id"],
                            expected_digest,
                            "APPROVED_PENDING_EXECUTION",
                        ),
                    )
        return {"state": "ACCEPTED", "approved_digest": expected_digest, "revision": revision}
