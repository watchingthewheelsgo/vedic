"""Feedback inbox and durable submission throttling."""

from alembic import op
import sqlalchemy as sa

revision = "6cb271e90123"
down_revision = "57d430a92b10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "feedback",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("owner_user_id", sa.String(160), nullable=True),
        sa.Column("sender_key", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("contact", sa.String(320), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "feedback_rate_limits",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("feedback_rate_limits")
    op.drop_table("feedback")
