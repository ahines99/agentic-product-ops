import io
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from agentic_product_ops.adapters.persistence.store import engine, metadata
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
