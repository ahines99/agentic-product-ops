"""Explicit single-operator bearer authentication, resolved against durable grants each use."""

import hashlib
import hmac

from pydantic import SecretStr

from agentic_product_ops.adapters.identity.contracts import Principal
from agentic_product_ops.services.authority import Authority


class LocalOperatorAuthenticator:
    def __init__(self, authority: Authority, *, token: SecretStr, subject: str):
        if len(token.get_secret_value()) < 40 or not subject:
            raise ValueError("explicit high-entropy operator credential and subject required")
        self.digest = hashlib.sha256(token.get_secret_value().encode()).hexdigest()
        self.authority, self.subject = authority, subject

    def authenticate(self, bearer: str) -> Principal | None:
        if not hmac.compare_digest(self.digest, hashlib.sha256(bearer.encode()).hexdigest()):
            return None
        if self.authority.token_revoked(self.subject, self.digest):
            return None
        return self.authority.resolve_subject(self.subject)
