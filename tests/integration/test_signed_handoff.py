import base64
import json
import secrets
import sqlite3
import subprocess
import sys
from datetime import timedelta
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from agentic_product_ops.adapters.linear.native_plan import NativePlan
from agentic_product_ops.api.app import TestAuthenticator, create_app
from agentic_product_ops.domain.contracts import SpecificationApproval, seal_specification
from agentic_product_ops.policies.validation import ServerPolicy
from agentic_product_ops.services.durable_analysis import analyze_specification
from agentic_product_ops.services.native_publication import NativePublisher
from agentic_product_ops.services.signed_handoff import export_signed_handoff
from product_ops_handoff.consumer import ReferenceConsumer, digest
from tests.integration.test_native_publication import LinearRecording, adapter
from tests.integration.test_native_publication import reviewed as reviewed


def consumer(path, signing, allow_mock=True):
    return ReferenceConsumer(
        path,
        keys={("product-ops-test", "key-1"): signing.public_key()},
        workspace="offline-workspace",
        teams=("product",),
        repositories=("sample-reporting",),
        policy_versions=("m0-v1",),
        allow_mock_transport=allow_mock,
    )


def published(reviewed):
    store, authority, spec, plan, approval, tick = reviewed
    recording = LinearRecording(plan, authority, tick)
    provider = adapter(plan, recording)
    try:
        NativePublisher(store, provider, authority, lambda: tick[0]).publish(
            spec, plan, approval, ServerPolicy()
        )
    finally:
        provider.close()
    signing = Ed25519PrivateKey.generate()
    envelope = export_signed_handoff(
        store,
        authority,
        ServerPolicy(),
        specification_id=str(spec.specification_id),
        approval_id=str(approval.approval_id),
        issuer="product-ops-test",
        key_id="key-1",
        signing_key=signing,
        now=tick[0] + timedelta(seconds=1),
    )
    return signing, envelope


@pytest.mark.parametrize("reviewed", ["handoff"], indirect=True)
def test_signed_publication_consumed_in_independent_store(reviewed, tmp_path):
    signing, envelope = published(reviewed)
    raw = envelope.model_dump_json().encode()
    contract = consumer(tmp_path / "delivery.db", signing)
    try:
        result = contract.consume(
            raw,
            expected_digest=envelope.payload.specification.content_digest,
            now=envelope.payload.issued_at,
        )
        assert result["state"] == "ACCEPTED"
        assert (
            contract.consume(
                raw, expected_digest=result["approved_digest"], now=envelope.payload.issued_at
            )["state"]
            == "ALREADY_ACCEPTED"
        )
        original = contract.database.execute(
            "SELECT original_bytes FROM delivery_intakes"
        ).fetchone()[0]
        assert original == raw
        assert {
            row[0] for row in contract.database.execute("SELECT status FROM delivery_work_items")
        } == {"APPROVED_PENDING_EXECUTION"}
        with pytest.raises(sqlite3.IntegrityError):
            contract.database.execute("UPDATE delivery_intakes SET revision=99")
    finally:
        contract.close()
    # The public consumer imports no Product Ops implementation, even in an isolated interpreter.
    check = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; import product_ops_handoff.consumer; "
            "assert not any(k.startswith('agentic_product_ops') for k in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )  # noqa: S603
    assert check.returncode == 0, check.stderr


@pytest.mark.parametrize("reviewed", ["handoff"], indirect=True)
@pytest.mark.parametrize(
    "fault",
    [
        "signature",
        "expected_digest",
        "issuer",
        "expiry",
        "mock",
        "ambiguity",
        "tier",
        "unknown_publication",
        "source",
        "scope",
    ],
)
def test_consumer_rejects_tampering_and_even_signed_unsafe_payload(reviewed, tmp_path, fault):
    signing, envelope = published(reviewed)
    document = envelope.model_dump(mode="json")
    expected = envelope.payload.specification.content_digest
    now = envelope.payload.issued_at
    if fault == "signature":
        document["signature"] = base64.b64encode(b"x" * 64).decode()
    elif fault == "expected_digest":
        expected = "0" * 64
    elif fault == "issuer":
        document["payload"]["issuer"] = "untrusted"
    elif fault == "expiry":
        now = envelope.payload.expires_at
    elif fault == "ambiguity":
        document["payload"]["specification"]["requirements"][0]["needs_human_decision"] = True
    elif fault == "tier":
        document["payload"]["specification"]["risk"]["tier"] = 3
    elif fault == "unknown_publication":
        document["payload"]["publications"][0]["status"] = "UNKNOWN"
    elif fault == "source":
        document["payload"]["specification"]["source_statements"][0]["text"] = "tampered source"
    elif fault == "scope":
        document["payload"]["plan"]["workspace_id"] = "untrusted-workspace"
    if fault not in {"signature", "expected_digest", "expiry", "mock"}:
        spec = document["payload"]["specification"]
        spec["content_digest"] = digest({k: v for k, v in spec.items() if k != "content_digest"})
        expected = spec["content_digest"]
        plan = document["payload"]["plan"]
        plan["specification_digest"] = expected
        for operation, receipt, dispatch in zip(
            plan["operations"],
            document["payload"]["publications"],
            document["payload"]["dispatches"],
            strict=True,
        ):
            wire = json.loads(operation["payload"])
            if "description" in wire:
                wire["description"] = wire["description"].replace(
                    envelope.payload.specification.content_digest, expected
                )
            operation["payload"] = json.dumps(wire, sort_keys=True, separators=(",", ":"))
            operation["request_digest"] = digest(
                {k: v for k, v in operation.items() if k != "request_digest"}
            )
            receipt["request_digest"] = dispatch["request_digest"] = operation["request_digest"]
        plan["content_digest"] = digest({k: v for k, v in plan.items() if k != "content_digest"})
        document["payload"]["approval"]["content_digest"] = expected
        document["payload"]["approval"]["scope"]["plan_digest"] = plan["content_digest"]
        for dispatch in document["payload"]["dispatches"]:
            dispatch["specification_digest"] = expected
            dispatch["plan_digest"] = plan["content_digest"]
        document["payload_digest"] = digest(document["payload"])
        document["signature"] = base64.b64encode(
            signing.sign(b"AgenticProductOps/Handoff/v2\x00" + document["payload_digest"].encode())
        ).decode()
    contract = consumer(tmp_path / "delivery.db", signing, allow_mock=fault != "mock")
    try:
        with pytest.raises(ValueError, match="rejected"):
            contract.consume(json.dumps(document).encode(), expected_digest=expected, now=now)
        assert contract.database.execute("SELECT count(*) FROM delivery_intakes").fetchone()[0] == 0
    finally:
        contract.close()


@pytest.mark.parametrize("reviewed", ["handoff"], indirect=True)
def test_new_approved_revision_supersedes_consumer_work_and_rejects_old(reviewed, tmp_path):
    store, authority, spec, plan, _, tick = reviewed
    signing, first = published(reviewed)
    contract = consumer(tmp_path / "delivery.db", signing)
    try:
        contract.consume(
            first.model_dump_json().encode(),
            expected_digest=spec.content_digest,
            now=first.payload.issued_at,
        )
        body = spec.model_dump(mode="json")
        body["revision"] = 2
        next_spec = seal_specification(body)
        with store.database.begin() as conn:
            store.put(
                conn, "offline-workspace", "specification", str(spec.specification_id), 2, next_spec
            )
        analyze_specification(
            store,
            "offline-workspace",
            str(spec.specification_id),
            next_spec.content_digest,
            ServerPolicy(),
        )
        token = secrets.token_urlsafe(32)
        app = create_app(
            store,
            authenticator=TestAuthenticator(
                {token: authority.resolve_subject("person")}, testing=True
            ),
            authority=authority,
            linear_scope=plan.scope,
        )
        with TestClient(app) as http:
            http.headers["Authorization"] = f"Bearer {token}"
            url = f"/v1/specifications/{spec.specification_id}"
            next_plan = NativePlan.model_validate_json(
                json.dumps(http.get(url + "/plan").json()["plan"])
            )
            response = http.post(
                url + "/approve",
                headers={"Idempotency-Key": str(uuid4())},
                json={
                    "revision": 2,
                    "content_digest": next_spec.content_digest,
                    "plan_digest": next_plan.content_digest,
                },
            )
            assert response.status_code == 200
            approval = SpecificationApproval.model_validate_json(
                json.dumps(response.json()["approval"])
            )
        tick[0] = approval.issued_at
        provider = adapter(next_plan, LinearRecording(next_plan, authority, tick))
        try:
            NativePublisher(store, provider, authority, lambda: tick[0]).publish(
                next_spec, next_plan, approval, ServerPolicy()
            )
        finally:
            provider.close()
        second = export_signed_handoff(
            store,
            authority,
            ServerPolicy(),
            specification_id=str(spec.specification_id),
            approval_id=str(approval.approval_id),
            issuer="product-ops-test",
            key_id="key-1",
            signing_key=signing,
            now=tick[0] + timedelta(seconds=1),
        )
        result = contract.consume(
            second.model_dump_json().encode(),
            expected_digest=next_spec.content_digest,
            now=second.payload.issued_at,
        )
        assert result["revision"] == 2
        assert (
            contract.database.execute(
                "SELECT status FROM delivery_work_items WHERE revision=1"
            ).fetchone()[0]
            == "SUPERSEDED"
        )
        with pytest.raises(ValueError, match="superseded"):
            contract.consume(
                first.model_dump_json().encode(),
                expected_digest=spec.content_digest,
                now=second.payload.issued_at,
            )
        assert contract.database.execute("SELECT count(*) FROM delivery_intakes").fetchone()[0] == 2
        with pytest.raises(ValueError, match="own database"):
            consumer(tmp_path / "native.db", signing)
    finally:
        contract.close()
