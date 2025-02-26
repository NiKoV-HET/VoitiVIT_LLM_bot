"""Add llm_model and llm_enabled to users

Revision ID: 006_add_llm_fields
Revises: 005_llm_functionality
Create Date: 2023-02-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "006_add_llm_fields"
down_revision = "005_llm_functionality"
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем поле llm_model в таблицу users
    op.add_column("users", sa.Column("llm_model", sa.String(255), nullable=True))
    
    # Добавляем поле llm_enabled в таблицу users с значением по умолчанию True
    op.add_column("users", sa.Column("llm_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")))


def downgrade():
    # Удаляем поля
    op.drop_column("users", "llm_enabled")
    op.drop_column("users", "llm_model") 