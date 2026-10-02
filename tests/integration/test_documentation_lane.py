import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from agentic_product_ops.adapters.linear.native_plan import (
    DELIVERY_READY_LABEL,
    LinearScope,
    ProviderBinding,
)
from agentic_product_ops.adapters.persistence.store import Missing, outbox
from agentic_product_ops.api.app import TestAuthenticator, create_app
from agentic_product_ops.api.local_console import BrowserSessions
from agentic_product_ops.domain.contracts import (
    WorkSpecification,
    canonical_digest,
    seal_specification,
    source_digest,
)
from agentic_product_ops.pilot.config import PilotSettings
from agentic_product_ops.pilot.runtime import PilotRuntime
from agentic_product_ops.policies.validation import DocumentationPolicy, PolicyError
from agentic_product_ops.services.documentation import (
    branch_head,
    requested_document,
    specification_policy,
)
from agentic_product_ops.services.durable_analysis import load_analysis
from tests.integration.test_risk_reassessment import Reviewer
from tests.integration.test_risk_reassessment import setup as setup

CONTENT = "# Filters\n\nMonth and currency examples for maintainer review.\n"
BASE = "c" * 40


def test_request_names_one_path_and_one_fenced_block():
    source = "Add docs/filters.md with this content:\n```markdown\n" + CONTENT + "```\n"
    assert requested_document(source) == ("docs/filters.md", CONTENT)
    with pytest.raises(PolicyError):
        requested_document(source + "\n```\nsecond\n```\n")
    with pytest.raises(PolicyError):
        requested_document("Add docs/filters.md and docs/other.md\n```\nx\n```\n")
    with pytest.raises(PolicyError):
        requested_document("Add docs/filters.md saying hello")


def test_branch_head_reads_git_files_without_running_git(tmp_path):
    with pytest.raises(PolicyError):
        branch_head(tmp_path)
    heads = tmp_path / ".git" / "refs" / "heads"
    heads.mkdir(parents=True)
    (tmp_path / ".git" / "packed-refs").write_text(
        "# pack-refs with: peeled\n" + "d" * 40 + " refs/heads/main\n", encoding="ascii"
    )
    assert branch_head(tmp_path) == "d" * 40
    (heads / "main").write_text("e" * 40 + "\n", encoding="ascii")
    assert branch_head(tmp_path) == "e" * 40
    (heads / "main").write_text("not-a-sha\n", encoding="ascii")
    with pytest.raises(PolicyError):
        branch_head(tmp_path)


@pytest.fixture
def lane(setup, tmp_path):
    store, authority, policy, actor, original, config = setup
    repository = tmp_path / "agentic-delivery-engineer"
    (repository / ".git" / "refs" / "heads").mkdir(parents=True)
    (repository / ".git" / "refs" / "heads" / "main").write_text(BASE + "\n", encoding="ascii")
    previous = load_analysis(store, policy.workspace_id, original, policy).model_dump(mode="json")
    body = original.model_dump(mode="json")
    body["source_statements"][0]["text"] += (
        "\nAdd docs/filters.md with this content:\n```\n" + CONTENT + "```\n"
    )
    body["source_digest"] = source_digest(body["source_statements"][0]["text"])
    body["revision"] = 2
    body["repository_context"] = {
        "repository_id": "sample-reporting",
        "snapshot_id": "test",
        "snapshot_digest": "1" * 64,
        "evidence": [],
        "relevant_tests": [],
        "unknown_edges": [],
        "confidence": "1",
    }
    body["work_items"][0]["repository_id"] = "sample-reporting"
    spec = seal_specification(body)
    previous["specification"] = spec.model_dump(mode="json")
    previous["review"]["specification_digest"] = spec.content_digest
    binding = canonical_digest(
        {"specification": spec.content_digest, "policy": policy.model_dump(mode="json")}
        | {"runner": "recorded-v1"}
    )
    with store.database.begin() as conn:
        store.put(conn, policy.workspace_id, "specification", str(spec.specification_id), 2, spec)
        store.put(conn, policy.workspace_id, "analysis_result", binding, 1, previous)
        store.put(
            conn,
            policy.workspace_id,
            "repository_selection",
            "sample-reporting",
            1,
            {"kind": "local", "location": str(repository)},
        )
    scope = LinearScope(
        organization_id=uuid4(),
        actor_id=uuid4(),
        teams=(ProviderBinding(local_id="product", provider_id=uuid4()),),
        labels=(ProviderBinding(local_id=DELIVERY_READY_LABEL, provider_id=uuid4()),),
    )
    reader = tmp_path / "handoff-reader.env"
    reader.write_text("HANDOFF_READER_TOKEN=reader-only\n", encoding="utf-8")
    runtime = PilotRuntime.__new__(PilotRuntime)
    runtime.store, runtime.authority, runtime.directory = store, authority, tmp_path
    runtime.base_policy = runtime.policy = policy
    runtime.configuration = config
    runtime.provider = lambda request=None: Reviewer()
    runtime.settings = PilotSettings(
        workspace=policy.workspace_id,
        subject="operator",
        database_url="postgresql+psycopg://postgres@127.0.0.1/product_ops_pilot",
        linear_scope=scope,
        linear_key_file=str(tmp_path / "linear.env"),
        anthropic_key_file=str(tmp_path / "anthropic.env"),
        spend_authorization="mock-only",
        maximum_spend="10",
        allow_paid_execution=True,
        allow_publication=True,
        handoff_reader_token_file=str(reader),
    )
    return runtime, actor, spec


def current(runtime, identifier):
    return WorkSpecification.model_validate_json(
        json.dumps(runtime.store.get(runtime.settings.workspace, "specification", identifier))
    )


def test_one_console_decision_moves_the_request_to_the_lane(lane):
    runtime, actor, spec = lane
    identifier = str(spec.specification_id)
    status = runtime.documentation_lane_status(identifier)
    assert status["eligible"] and status["path"] == "docs/filters.md"
    assert status["content"] == CONTENT and status["base_sha"] == BASE
    with pytest.raises(PolicyError, match="stale"):
        runtime.documentation_handoff(identifier, actor, 1, spec.content_digest, "lane")
    reviewer_only = actor.model_copy(update={"roles": ("product_approver",)})
    with pytest.raises(PolicyError, match="security approver"):
        runtime.documentation_handoff(
            identifier, reviewer_only, spec.revision, spec.content_digest, "lane"
        )
    receipt = runtime.documentation_handoff(
        identifier, actor, spec.revision, spec.content_digest, "lane"
    )
    promoted = current(runtime, identifier)
    assert receipt["revision"] == promoted.revision == 3 and promoted.risk.tier == 1
    governing = runtime.policy_for(promoted)
    assert isinstance(governing, DocumentationPolicy)
    assert governing.documentation_capability.base_sha == BASE
    assert runtime.policy_for(spec) is runtime.policy
    assert runtime.documentation_lane_status(identifier)["promoted"]


def test_lane_tickets_carry_the_contract_lines_and_approval_starts_no_workflow(lane):
    runtime, actor, spec = lane
    identifier = str(spec.specification_id)
    runtime.documentation_handoff(identifier, actor, spec.revision, spec.content_digest, "lane")
    promoted = current(runtime, identifier)
    store, policy = runtime.store, runtime.policy
    app = create_app(
        store,
        policy,
        TestAuthenticator({"token": actor}, testing=True),
        runtime.authority,
        runtime.settings.linear_scope,
        policy_for=lambda db, s: specification_policy(db, policy, s, policy),
        documentation_lane=runtime.documentation_lane_status,
    )
    headers = {"Authorization": "Bearer token"}
    expected = [
        "Repository: agentic-delivery-engineer",
        f"Handoff: sha256:{promoted.content_digest}",
    ]
    with TestClient(app) as client:
        tickets = client.get(f"/v1/specifications/{identifier}/tickets", headers=headers).json()
        assert all(t["description"].splitlines()[:2] == expected for t in tickets["tickets"])
        plan = client.get(f"/v1/specifications/{identifier}/plan", headers=headers).json()["plan"]
        descriptions = [
            json.loads(op["payload"])["description"]
            for op in plan["operations"]
            if op["kind"] == "issue_create"
        ]
        assert descriptions and all(d.splitlines()[:2] == expected for d in descriptions)
        approved = client.post(
            f"/v1/specifications/{identifier}/approve",
            headers={**headers, "Idempotency-Key": "exact-approval"},
            json={
                "revision": promoted.revision,
                "content_digest": promoted.content_digest,
                "plan_digest": plan["content_digest"],
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["approval"]["policy_version"] == promoted.risk.policy_version
    with store.database.connect() as conn:
        assert not conn.execute(select(outbox).where(outbox.c.workflow_id.like("decision-%"))).all()


def test_delivery_reads_the_capability_named_by_the_signed_approval(lane):
    runtime, actor, spec = lane
    identifier = str(spec.specification_id)
    runtime.documentation_handoff(identifier, actor, spec.revision, spec.content_digest, "lane")
    promoted = current(runtime, identifier)
    with runtime.store.database.begin() as conn:
        runtime.store.put(
            conn,
            runtime.settings.workspace,
            "handoff_index",
            promoted.content_digest,
            1,
            {"specification_id": identifier},
        )
    with pytest.raises(PolicyError):
        runtime.documentation_capability_for_digest("wrong", promoted.content_digest)
    capability = runtime.documentation_capability_for_digest(
        "reader-only", "sha256:" + promoted.content_digest
    )
    assert "doc-add-v1-" + canonical_digest(capability) == promoted.risk.policy_version
    with pytest.raises(Missing):
        runtime.documentation_capability_for_digest("reader-only", spec.content_digest)


def test_browser_may_choose_the_lane_only_when_publication_is_enabled():
    from starlette.requests import Request

    def request(method, path, publication):
        sessions = BrowserSessions(18013, publication=publication)
        token = sessions.exchange(sessions.launch("operator").split("#launch=")[1])
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [
                (b"origin", b"http://127.0.0.1:18013"),
                (b"x-product-ops-ui", b"1"),
                (b"cookie", f"apo_local_session={token}".encode()),
            ],
            "query_string": b"",
        }
        return sessions.credential(Request(scope))

    path = f"/v1/specifications/{uuid4()}/documentation-lane"
    assert request("GET", path, False) == "operator"
    assert request("POST", path, True) == "operator"
    with pytest.raises(Exception, match="cannot perform"):
        request("POST", path, False)
