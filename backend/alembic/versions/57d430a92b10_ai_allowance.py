"""Monthly AI allowance and manually approved memberships."""

from alembic import op
import sqlalchemy as sa

revision = "57d430a92b10"
down_revision = "4f2310ac9a01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_allowances",
        sa.Column("owner_user_id", sa.String(160), primary_key=True),
        sa.Column("period", sa.String(7), primary_key=True),
        sa.Column("used", sa.Integer(), nullable=False),
    )
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("owner_user_id", sa.String(160), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("job_id", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_usage_owner_user_id", "ai_usage", ["owner_user_id"])
    op.create_table(
        "manual_memberships",
        sa.Column("owner_user_id", sa.String(160), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("monthly_limit", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("manual_memberships")
    op.drop_table("ai_usage")
    op.drop_table("ai_allowances")
