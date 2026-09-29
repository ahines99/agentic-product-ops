from datetime import UTC, datetime

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from agentic_product_ops.adapters.identity.jwt import JWTAuthenticator
from agentic_product_ops.api.app import Principal, create_app


@pytest.fixture(scope="module")
def signing():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def claims(**changes):
    tick = int(datetime.now(UTC).timestamp())
    return {
        "iss": "https://identity.example",
        "aud": "product-ops",
        "sub": "human-1",
        "iat": tick,
        "nbf": tick,
        "exp": tick + 300,
        "jti": "session-1",
        **changes,
    }


def verifier(signing, revoked=lambda subject, token_id: False):
    actor = Principal(
        actor_id="offline-reviewer", workspace_id="offline-workspace", roles=("reader",)
    )
    return JWTAuthenticator(
        issuer="https://identity.example",
        audience="product-ops",
        keys={"key-1": signing.public_key()},
        subjects={"human-1": actor},
        revoked=revoked,
    )


def signed(signing, value, **headers):
    return jwt.encode(value, signing, algorithm="RS256", headers={"kid": "key-1", **headers})


def test_verified_claims_never_grant_roles(signing):
    auth = verifier(signing)
    token = signed(
        signing, claims(roles=["product_approver"], workspace_id="other", actor_id="admin")
    )
    principal = auth.authenticate(token)
    assert principal.roles == ("reader",)
    assert principal.workspace_id == "offline-workspace"
    with TestClient(create_app(authenticator=auth)) as client:
        # A signature authenticates the configured reader; bearer roles cannot grant approval.
        result = client.post(
            "/v1/specifications/00000000-0000-0000-0000-000000000000/publish",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "attempt"},
        )
        assert result.status_code == 403


@pytest.mark.parametrize(
    "change",
    [
        {"iss": "https://attacker.example"},
        {"aud": "different"},
        {"sub": "unknown"},
        {"exp": 1},
        {"nbf": 9999999999},
        {"iat": True},
        {"jti": ""},
        {"aud": ["product-ops", "other"]},
        {"exp": 9999999999},
    ],
)
def test_invalid_claims_denied(signing, change):
    assert verifier(signing).authenticate(signed(signing, claims(**change))) is None


@pytest.mark.parametrize(
    "header",
    [
        {"kid": "unknown"},
        {"jku": "https://attacker.example/keys"},
        {"crit": ["unknown"]},
        {"typ": "other"},
    ],
)
def test_untrusted_key_selection_denied(signing, header):
    assert verifier(signing).authenticate(signed(signing, claims(), **header)) is None


def test_signature_algorithm_missing_claims_and_revocation(signing):
    token = signed(signing, claims())
    assert verifier(signing, lambda subject, token_id: True).authenticate(token) is None

    def unavailable(subject, token_id):
        raise RuntimeError("backend private detail")

    assert verifier(signing, unavailable).authenticate(token) is None
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert verifier(signing).authenticate(signed(wrong_key, claims())) is None
    assert verifier(signing).authenticate(jwt.encode(claims(), key="", algorithm="none")) is None
    missing = claims()
    del missing["exp"]
    assert verifier(signing).authenticate(signed(signing, missing)) is None
    assert verifier(signing).authenticate("x" * 16001) is None
