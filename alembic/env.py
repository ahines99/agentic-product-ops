"""Explicit engine injection or environment DSN; no default or logged credentials."""

import os

from sqlalchemy import create_engine

from agentic_product_ops.adapters.persistence.store import metadata
from alembic import context


def migrate(connection):
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url="postgresql+psycopg://",
        target_metadata=metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
elif context.config.attributes.get("connection") is not None:
    migrate(context.config.attributes["connection"])
else:
    url = os.environ["PRODUCT_OPS_DATABASE_URL"]
    if not url.startswith("postgresql+psycopg://"):
        raise ValueError("PostgreSQL required")
    with create_engine(url, hide_parameters=True).connect() as connection:
        migrate(connection)
