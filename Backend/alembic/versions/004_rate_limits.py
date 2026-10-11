"""nullable audit actor and rate-limit user

Revision ID: 004_rate_limits
Revises: 003_agent_runs
Create Date: 2026-10-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "004_rate_limits"
down_revision: str | Sequence[str] | None = "003_agent_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("audit_log", "admin_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.add_column("audit_log", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_foreign_key("fk_audit_log_user_id", "audit_log", "users", ["user_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_audit_log_user_id", "audit_log", type_="foreignkey")
    op.drop_index("ix_audit_log_user_id", table_name="audit_log")
    op.drop_column("audit_log", "user_id")
    op.alter_column("audit_log", "admin_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
