"""Injected encryption-at-rest keyring; purpose and immutable row identity are authenticated."""

import base64
import json
import secrets
from collections.abc import Mapping
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from agentic_product_ops.domain.contracts import canonical_digest


class StorageEncryption:
    def __init__(self, keys: Mapping[str, bytes], active_key: str):
        if active_key not in keys or any(len(value) != 32 for value in keys.values()):
            raise ValueError("explicit AES-256 storage keyring required")
        self._keys, self.active_key = dict(keys), active_key

    def encode(self, identity: tuple[str | int, ...], value: dict[str, Any]) -> str:
        nonce = secrets.token_bytes(12)
        aad = canonical_digest({"identity": identity, "key_id": self.active_key}).encode()
        plaintext = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        if len(plaintext) > 2_000_000:
            raise ValueError("artifact plaintext exceeds storage bound")
        encrypted = AESGCM(self._keys[self.active_key]).encrypt(nonce, plaintext, aad)
        return json.dumps(
            {
                "storage_version": 1,
                "key_id": self.active_key,
                "nonce": base64.b64encode(nonce).decode(),
                "ciphertext": base64.b64encode(encrypted).decode(),
            }
        )

    def decode(self, identity: tuple[str | int, ...], encoded: str) -> dict[str, Any]:
        try:
            record = json.loads(encoded)
            if record["storage_version"] != 1:
                raise ValueError("unknown storage encryption version")
            aad = canonical_digest({"identity": identity, "key_id": record["key_id"]}).encode()
            plaintext = AESGCM(self._keys[record["key_id"]]).decrypt(
                base64.b64decode(record["nonce"], validate=True),
                base64.b64decode(record["ciphertext"], validate=True),
                aad,
            )
            value: dict[str, Any] = json.loads(plaintext)
            if not isinstance(value, dict):
                raise ValueError("invalid artifact")
            return value
        except Exception:
            raise ValueError("artifact decryption/authentication failed") from None
