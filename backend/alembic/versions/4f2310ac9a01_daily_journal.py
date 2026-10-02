"""Private daily observations, additive migration."""

from alembic import op
import sqlalchemy as sa

revision = "4f2310ac9a01"
down_revision = "73b62eebd34b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.String(160), nullable=False),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("mood", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(32), nullable=False),
        sa.Column("calendar", sa.JSON(), nullable=False),
        sa.Column("reflections", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", "day", name="uq_journal_owner_day"),
    )
    op.create_index("ix_journal_entries_owner_user_id", "journal_entries", ["owner_user_id"])


def downgrade():
    op.drop_table("journal_entries")
