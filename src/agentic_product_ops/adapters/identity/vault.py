"""Authenticated encryption for operator/provider secrets; no ambient master-key discovery."""

import base64
import json
import secrets
from collections.abc import Mapping

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr
from sqlalchemy import Connection

from agentic_product_ops.adapters.persistence.store import Store
from agentic_product_ops.domain.contracts import canonical_digest


class SecretVault:
    def __init__(self, store: Store, keys: Mapping[str, bytes], active_key: str):
        if active_key not in keys or any(len(value) != 32 for value in keys.values()):
            raise ValueError("explicit AES-256 keys and active key required")
        self.store, self._keys, self.active_key = store, dict(keys), active_key

    def put(
        self,
        conn: Connection,
        workspace: str,
        identity: str,
        revision: int,
        value: SecretStr,
    ) -> None:
        plaintext = value.get_secret_value().encode()
        if not 0 < len(plaintext) <= 65536:
            raise ValueError("secret size outside bound")
        nonce = secrets.token_bytes(12)
        binding = {
            "workspace": workspace,
            "identity": identity,
            "revision": revision,
            "key": self.active_key,
        }
        ciphertext = AESGCM(self._keys[self.active_key]).encrypt(
            nonce,
            plaintext,
            canonical_digest(binding).encode(),
        )
        self.store.put(
            conn,
            workspace,
            "sealed_secret",
            identity,
            revision,
            {
                **binding,
                "nonce": base64.b64encode(nonce).decode(),
                "ciphertext": base64.b64encode(ciphertext).decode(),
            },
        )

    def get(self, workspace: str, identity: str, revision: int | None = None) -> SecretStr:
        try:
            record = self.store.get(workspace, "sealed_secret", identity, revision)
            binding = {name: record[name] for name in ("workspace", "identity", "revision", "key")}
            if binding["workspace"] != workspace or binding["identity"] != identity:
                raise ValueError("secret binding mismatch")
            if revision is not None and binding["revision"] != revision:
                raise ValueError("secret revision mismatch")
            plaintext = AESGCM(self._keys[record["key"]]).decrypt(
                base64.b64decode(record["nonce"], validate=True),
                base64.b64decode(record["ciphertext"], validate=True),
                canonical_digest(binding).encode(),
            )
            return SecretStr(plaintext.decode())
        except Exception:
            raise ValueError("secret unavailable or authentication failed") from None

    def rotate(self, workspace: str, identity: str) -> None:
        # Retain old ciphertext for audit/restore; operators retire old keys after retention review.
        with self.store.database.begin() as conn:
            self.store.lock_specification(conn, workspace, "secret:" + identity)
            record = self.store.get(workspace, "sealed_secret", identity, connection=conn)
            secret = self.get(workspace, identity, record["revision"])
            self.put(conn, workspace, identity, record["revision"] + 1, secret)


def secret_json(value: dict[str, object]) -> SecretStr:
    return SecretStr(json.dumps(value, separators=(",", ":")))
