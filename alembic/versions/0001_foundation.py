"""Immutable artifacts and receipts, transactional command/outbox/write-intent storage."""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "artifacts",
        sa.Column("workspace", sa.String(128), primary_key=True),
        sa.Column("kind", sa.String(64), primary_key=True),
        sa.Column("identity", sa.String(128), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "commands",
        sa.Column("workspace", sa.String(128), primary_key=True),
        sa.Column("actor", sa.String(128), primary_key=True),
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
    )
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(128), primary_key=True),
        sa.Column("workspace", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("subject", sa.String(128), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "workflow_outbox",
        sa.Column("workspace", sa.String(128), primary_key=True),
        sa.Column("workflow_id", sa.String(128), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("dispatched", sa.Integer(), nullable=False),
    )
    op.create_table(
        "publication_operations",
        sa.Column("workspace", sa.String(128), primary_key=True),
        sa.Column("operation_key", sa.String(64), primary_key=True),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("request", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.String(128)),
        sa.Column("provider_request_id", sa.String(128)),
        sa.Column("observed_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "publication_controls",
        sa.Column("workspace", sa.String(128), primary_key=True),
        sa.Column("specification_id", sa.String(128), primary_key=True),
        sa.Column("cancelled", sa.Integer(), nullable=False),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION product_ops_immutable() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'immutable Product Ops record'; END;
            $$ LANGUAGE plpgsql""")
        for table in ("artifacts", "commands", "audit_events"):
            op.execute(
                f"CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION product_ops_immutable()"
            )


def downgrade():
    for table in (
        "publication_controls",
        "publication_operations",
        "workflow_outbox",
        "audit_events",
        "commands",
        "artifacts",
    ):
        op.drop_table(table)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION product_ops_immutable()")
