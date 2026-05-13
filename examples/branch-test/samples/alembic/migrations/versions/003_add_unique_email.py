"""Add UNIQUE constraint on users.email.

Fails if duplicate emails exist. Exactly the kind of migration where
"works on the branch but not on prod" is a $$$ surprise. branch-test
catches it before main does.

Revision ID: 003
Revises: 002
Create Date: 2026-05-13 00:00:02.000000

"""
from alembic import op


revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("users_email_key", "users", ["email"])


def downgrade() -> None:
    op.drop_constraint("users_email_key", "users", type_="unique")
