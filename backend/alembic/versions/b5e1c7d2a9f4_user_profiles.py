"""Store the account owner's birth profile."""

from alembic import op
import sqlalchemy as sa

revision = "b5e1c7d2a9f4"
down_revision = "7d931ab82c40"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_profiles",
        sa.Column("owner_user_id", sa.String(160), primary_key=True),
        sa.Column("birth_date", sa.String(10), nullable=False),
        sa.Column("birth_time", sa.String(5), nullable=True),
        sa.Column("birth_place", sa.Text(), nullable=False),
        sa.Column("place_label", sa.String(200), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("gender", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("user_profiles")
