"""update users table primary key

Revision ID: 003_update_users_pk
Revises: 002_add_users_and_ordering
Create Date: 2025-02-22
"""

from alembic import op
import sqlalchemy as sa

revision = "003_update_users_pk"
down_revision = "002_add_users_and_ordering"
branch_labels = None
depends_on = None


def upgrade():
    # Удаляем старую таблицу, если она еще не была изменена (для новых проектов):
    op.drop_table("users")
    # Создаем новую таблицу с использованием tg_id в качестве primary key
    op.create_table(
        "users",
        sa.Column("tg_id", sa.String, primary_key=True, nullable=False),
        sa.Column("full_name", sa.String, nullable=False),
        sa.Column("phone", sa.String, nullable=True),
        sa.Column("username", sa.String, nullable=True),
    )


def downgrade():
    op.drop_table("users")
    # Восстанавливаем старую схему можно определить по необходимости
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tg_id", sa.String, unique=True, nullable=False),
        sa.Column("full_name", sa.String, nullable=False),
        sa.Column("phone", sa.String, nullable=True),
        sa.Column("username", sa.String, nullable=True),
    )
