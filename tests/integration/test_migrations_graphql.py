import io
import json
from pathlib import Path

import httpx
import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from agentic_product_ops.adapters.linear.graphql import MockGraphQLAdapter, UnknownOutcome
from agentic_product_ops.adapters.linear.offline import build_plan
from agentic_product_ops.adapters.persistence.store import engine, metadata
from agentic_product_ops.policies.validation import ServerPolicy
from alembic import command

ROOT = Path(__file__).resolve().parents[2]


def test_migration_roundtrip_and_metadata(tmp_path):
    database = engine(f"sqlite:///{tmp_path / 'migration.db'}", testing=True)
    cfg = Config(str(ROOT / "alembic.ini"))
    with database.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
        assert compare_metadata(MigrationContext.configure(connection), metadata) == []
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
    database.dispose()
    output = io.StringIO()
    cfg = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    command.upgrade(cfg, "head", sql=True)
    assert "CREATE TRIGGER immutable_record" in output.getvalue()


def test_graphql_variables_exact_content(valid):
    operation = build_plan(valid, ServerPolicy()).operations[0]

    def handler(request):
        body = json.loads(request.content)
        assert body["variables"]["input"]["title"] == operation.title
        assert operation.description not in body["query"]
        return httpx.Response(
            200,
            json={
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "id": "provider-1",
                            "identifier": "P-1",
                            "title": operation.title,
                            "team": {"id": operation.team_id},
                            "description": operation.description,
                        },
                    }
                }
            },
        )

    adapter = MockGraphQLAdapter(httpx.MockTransport(handler))
    assert adapter.create(operation) == "provider-1"
    adapter.close()


@pytest.mark.parametrize(
    "status,body", [(200, {"errors": [{"message": "private"}]}), (429, {}), (200, {"data": {}})]
)
def test_graphql_uncertainty_never_retries(valid, status, body):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=body)

    adapter = MockGraphQLAdapter(httpx.MockTransport(handler))
    with pytest.raises(UnknownOutcome, match="reconciliation"):
        adapter.create(build_plan(valid, ServerPolicy()).operations[0])
    assert len(calls) == 1
    adapter.close()
