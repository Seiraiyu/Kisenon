"""Create users table (baseline).

Revision ID: 001
Revises:
Create Date: 2026-05-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        # `name` is intentionally nullable at this revision -- 002 backfills + enforces.
        sa.Column("name", sa.String(120), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("users")
