"""link feedbacks and logs to users

Revision ID: 004_link_feedback_logs_to_users
Revises: 003_update_users_pk
Create Date: 2025-02-22
"""

from alembic import op
import sqlalchemy as sa

revision = "004_link_feedback_logs_to_users"
down_revision = "003_update_users_pk"
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем внешний ключ для таблицы feedbacks
    op.create_foreign_key("fk_feedbacks_user", "feedbacks", "users", ["user_id"], ["tg_id"], ondelete="CASCADE")
    # Добавляем внешний ключ для таблицы logs
    op.create_foreign_key("fk_logs_user", "logs", "users", ["user_id"], ["tg_id"], ondelete="CASCADE")


def downgrade():
    op.drop_constraint("fk_feedbacks_user", "feedbacks", type_="foreignkey")
    op.drop_constraint("fk_logs_user", "logs", type_="foreignkey")
