"""Pinned issuer/key verification; token claims never grant application roles or scope."""

from collections.abc import Callable, Mapping

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from agentic_product_ops.adapters.identity.contracts import Principal


class JWTAuthenticator:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        keys: Mapping[str, RSAPublicKey],
        subjects: Mapping[str, Principal] | None = None,
        resolve_subject: Callable[[str], Principal | None] | None = None,
        revoked: Callable[[str, str], bool],
        maximum_lifetime_seconds: int = 3600,
    ):
        if not issuer.startswith("https://") or not audience or not keys:
            raise ValueError("explicit issuer/audience/pinned keys required")
        if not 1 <= maximum_lifetime_seconds <= 3600:
            raise ValueError("token lifetime bound required")
        if any(not isinstance(key, RSAPublicKey) or key.key_size < 2048 for key in keys.values()):
            raise ValueError("RSA public keys of at least 2048 bits required")
        self.issuer, self.audience = issuer, audience
        if (subjects is None) == (resolve_subject is None):
            raise ValueError("exactly one server-side subject authority required")
        self.keys, self.subjects = dict(keys), dict(subjects or {})
        self.resolve_subject = resolve_subject or self.subjects.get
        self.revoked, self.maximum_lifetime = revoked, maximum_lifetime_seconds
        for principal in self.subjects.values():
            Principal.model_validate_json(principal.model_dump_json())

    def authenticate(self, bearer: str) -> Principal | None:
        if not 1 <= len(bearer) <= 16000:
            return None
        try:
            header = jwt.get_unverified_header(bearer)
            if set(header) - {"alg", "kid", "typ"} or header.get("alg") != "RS256":
                return None
            if header.get("typ") not in {"JWT", "at+jwt"}:
                return None
            kid = header.get("kid")
            if not isinstance(kid, str) or kid not in self.keys:
                return None
            claims = jwt.decode(
                bearer,
                self.keys[kid],
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={
                    "require": ["iss", "aud", "sub", "iat", "nbf", "exp", "jti"],
                    "strict_aud": True,
                },
            )
            if any(type(claims[name]) is not int for name in ("iat", "nbf", "exp")):
                return None
            if not 0 < claims["exp"] - claims["iat"] <= self.maximum_lifetime:
                return None
            if claims["nbf"] < claims["iat"] or claims["nbf"] >= claims["exp"]:
                return None
            subject, token_id = claims["sub"], claims["jti"]
            if not all(
                isinstance(value, str) and 0 < len(value) <= 256 for value in (subject, token_id)
            ):
                return None
            if self.revoked(subject, token_id):
                return None
            return self.resolve_subject(subject)
        except Exception:
            # Includes unavailable revocation backend: deny without logging bearer or provider text.
            return None
