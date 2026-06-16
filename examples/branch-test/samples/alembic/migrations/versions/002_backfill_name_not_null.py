"""Backfill name and enforce NOT NULL.

This is the kind of migration that can lock a real table and fail loudly
on rows whose name was never set. Exactly what you want to dry-run on a
branch first.

Revision ID: 002
Revises: 001
Create Date: 2026-05-13 00:00:01.000000

"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill any NULL names with a deterministic placeholder.
    op.execute("UPDATE users SET name = COALESCE(name, 'unknown') WHERE name IS NULL")
    op.alter_column("users", "name", nullable=False)


def downgrade() -> None:
    op.alter_column("users", "name", nullable=True)
