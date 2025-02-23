"""Add LLM functionality tables

Revision ID: 005_llm_functionality
Revises: 004_link_feedback_logs_to_users
Create Date: 2025-02-22
"""

from alembic import op
import sqlalchemy as sa

revision = "005_llm_functionality"
down_revision = "004_link_feedback_logs_to_users"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "llm_usage",
        sa.Column("user_id", sa.String, sa.ForeignKey("users.tg_id"), primary_key=True, nullable=False),
        sa.Column("used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("limit", sa.Integer, nullable=False, server_default="10"),
    )
    op.create_table(
        "llm_requests",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.String, sa.ForeignKey("users.tg_id"), nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("response", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "llm_config",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    # Добавим единственную запись в llm_config по умолчанию
    op.execute("INSERT INTO llm_config (id, enabled) VALUES (1, true)")


def downgrade():
    op.drop_table("llm_config")
    op.drop_table("llm_requests")
    op.drop_table("llm_usage")
