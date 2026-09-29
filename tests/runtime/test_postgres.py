"""Real PostgreSQL checks restricted to explicitly named disposable loopback databases."""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import select, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from agentic_product_ops.adapters.linear.offline import FakeLinear, build_plan
from agentic_product_ops.adapters.persistence.store import (
    Store,
    artifacts,
    commands,
    engine,
    metadata,
)
from agentic_product_ops.cli import simulated_approval
from agentic_product_ops.policies.validation import ServerPolicy
from agentic_product_ops.services.publication import DurableSimulationPublisher
from alembic import command

pytestmark = pytest.mark.skipif(
    not os.getenv("PRODUCT_OPS_TEST_DATABASE_URL"),
    reason="explicit disposable PostgreSQL test database required",
)


def test_real_migrations_immutability_and_concurrent_commands(valid, now):
    url = os.environ["PRODUCT_OPS_TEST_DATABASE_URL"]
    parsed = make_url(url)
    assert parsed.host in {"127.0.0.1", "localhost"}
    assert parsed.database and parsed.database.startswith("product_ops_test")
    database = engine(url)
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    with database.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        assert compare_metadata(MigrationContext.configure(conn), metadata) == []
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
    store = Store(database)

    def execute(conn):
        store.put(conn, "workspace", "intake", "intake-1", 1, {"source": "request"})
        return {"id": "intake-1"}

    def submit(_):
        return store.command("workspace", "actor", "concurrent-key", {"command": "intake"}, execute)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(submit, range(8)))
    assert results == [{"id": "intake-1"}] * 8
    with database.connect() as conn:
        assert len(conn.execute(select(commands)).all()) == 1
    with pytest.raises(DBAPIError, match="immutable"):
        with database.begin() as conn:
            conn.execute(update(artifacts).values(payload="tampered"))
    with pytest.raises(DBAPIError, match="immutable"):
        with database.begin() as conn:
            conn.execute(artifacts.delete())
    provider = FakeLinear()
    policy = ServerPolicy()
    plan, approval = build_plan(valid, policy), simulated_approval(valid, now)

    def publish(_):
        return DurableSimulationPublisher(Store(database), provider, lambda: now).publish(
            valid, plan, approval, policy, "offline-reviewer"
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(publish, range(8)))
    assert all(receipt.status == "SUCCEEDED" for receipt in publish(0))
    assert provider.calls == len(valid.work_items)
    with database.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "base")
    database.dispose()
