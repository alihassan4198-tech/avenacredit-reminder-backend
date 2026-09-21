"""add admin user profile/status fields

Revision ID: 20260519_0003
Revises: 20260515_0002
Create Date: 2026-05-19 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260519_0003"
down_revision: Union[str, None] = "20260515_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ROLE_CONSTRAINT = "ck_admin_users_role_values"
STATUS_CONSTRAINT = "ck_admin_users_status_values"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def has_column(table_name: str, column_name: str) -> bool:
        columns = inspector.get_columns(table_name)
        return column_name in {col["name"] for col in columns}

    def has_check_constraint(table_name: str, constraint_name: str) -> bool:
        constraints = inspector.get_check_constraints(table_name)
        return constraint_name in {c["name"] for c in constraints}

    if not has_column("admin_users", "full_name"):
        op.add_column("admin_users", sa.Column("full_name", sa.String(length=255), nullable=True))

    if not has_column("admin_users", "status"):
        op.add_column(
            "admin_users",
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        )

    if not has_column("admin_users", "last_login_at"):
        op.add_column("admin_users", sa.Column("last_login_at", sa.DateTime(), nullable=True))

    op.execute("UPDATE admin_users SET status = 'active' WHERE status IS NULL")
    op.execute("UPDATE admin_users SET status = 'disabled' WHERE is_active = false")

    op.alter_column(
        "admin_users",
        "status",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default="active",
    )

    if not has_check_constraint("admin_users", ROLE_CONSTRAINT):
        op.create_check_constraint(
            ROLE_CONSTRAINT,
            "admin_users",
            "role IN ('owner', 'admin')",
        )

    if not has_check_constraint("admin_users", STATUS_CONSTRAINT):
        op.create_check_constraint(
            STATUS_CONSTRAINT,
            "admin_users",
            "status IN ('active', 'disabled')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    constraint_names = {c["name"] for c in inspector.get_check_constraints("admin_users")}
    if STATUS_CONSTRAINT in constraint_names:
        op.drop_constraint(STATUS_CONSTRAINT, "admin_users", type_="check")
    if ROLE_CONSTRAINT in constraint_names:
        op.drop_constraint(ROLE_CONSTRAINT, "admin_users", type_="check")

    columns = {col["name"] for col in inspector.get_columns("admin_users")}
    if "last_login_at" in columns:
        op.drop_column("admin_users", "last_login_at")
    if "status" in columns:
        op.drop_column("admin_users", "status")
    if "full_name" in columns:
        op.drop_column("admin_users", "full_name")
