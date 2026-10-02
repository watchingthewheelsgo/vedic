"""Audit manual membership changes."""

from alembic import op
import sqlalchemy as sa

revision = "7d931ab82c40"
down_revision = "6cb271e90123"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "membership_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.String(160), nullable=False),
        sa.Column("actor_user_id", sa.String(160), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_membership_audit_owner_user_id", "membership_audit", ["owner_user_id"])


def downgrade():
    op.drop_table("membership_audit")
