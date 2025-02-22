"""add users table and ordering for categories and subtopics

Revision ID: 002_add_users_and_ordering
Revises: 001_create_tables
Create Date: 2025-02-22
"""

from alembic import op
import sqlalchemy as sa

revision = "002_add_users_and_ordering"
down_revision = "001_create_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tg_id", sa.String, unique=True, nullable=False),
        sa.Column("full_name", sa.String, nullable=False),
        sa.Column("phone", sa.String, nullable=True),
        sa.Column("username", sa.String, nullable=True),
    )
    op.add_column("categories", sa.Column("display_order", sa.Integer, nullable=False, server_default="0"))
    op.add_column("subtopics", sa.Column("display_order", sa.Integer, nullable=False, server_default="0"))


def downgrade():
    op.drop_column("subtopics", "display_order")
    op.drop_column("categories", "display_order")
    op.drop_table("users")
