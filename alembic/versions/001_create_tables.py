"""create tables

Revision ID: 001_create_tables
Revises: 
Create Date: 2025-02-22

"""

from alembic import op
import sqlalchemy as sa

revision = "001_create_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
    )
    op.create_table(
        "subtopics",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("media", sa.String, nullable=True),
    )
    op.create_table(
        "feedbacks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.String, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.String, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("logs")
    op.drop_table("feedbacks")
    op.drop_table("subtopics")
    op.drop_table("categories")
