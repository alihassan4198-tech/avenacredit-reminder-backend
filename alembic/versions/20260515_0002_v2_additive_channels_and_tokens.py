"""v2 additive channels and tokens

Revision ID: 20260515_0002
Revises: 20260515_0001
Create Date: 2026-05-15 00:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260515_0002"
down_revision: Union[str, None] = "20260515_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    def has_table(table_name: str) -> bool:
        return sa.inspect(bind).has_table(table_name)

    def has_column(table_name: str, column_name: str) -> bool:
        columns = sa.inspect(bind).get_columns(table_name)
        return column_name in {col["name"] for col in columns}

    def has_index(table_name: str, index_name: str) -> bool:
        indexes = sa.inspect(bind).get_indexes(table_name)
        return index_name in {idx["name"] for idx in indexes}

    if not has_column("subscribers", "first_name"):
        op.add_column("subscribers", sa.Column("first_name", sa.String(length=120), nullable=True))
    if not has_column("subscribers", "last_name"):
        op.add_column("subscribers", sa.Column("last_name", sa.String(length=120), nullable=True))
    if not has_column("subscribers", "phone"):
        op.add_column("subscribers", sa.Column("phone", sa.String(length=32), nullable=True))
    if not has_column("subscribers", "signup_source"):
        op.add_column("subscribers", sa.Column("signup_source", sa.String(length=128), nullable=True))
    if not has_column("subscribers", "email_enabled"):
        op.add_column(
            "subscribers",
            sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
    if not has_column("subscribers", "sms_enabled"):
        op.add_column(
            "subscribers",
            sa.Column("sms_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )

    if not has_column("credit_cards", "email_enabled"):
        op.add_column(
            "credit_cards",
            sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
    if not has_column("credit_cards", "sms_enabled"):
        op.add_column(
            "credit_cards",
            sa.Column("sms_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )

    if not has_column("scheduled_reminders", "channel"):
        op.add_column(
            "scheduled_reminders",
            sa.Column("channel", sa.String(length=16), nullable=False, server_default="email"),
        )
    if not has_column("scheduled_reminders", "attempt_count"):
        op.add_column(
            "scheduled_reminders",
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )
    if not has_column("scheduled_reminders", "locked_at"):
        op.add_column("scheduled_reminders", sa.Column("locked_at", sa.DateTime(), nullable=True))
    if not has_column("scheduled_reminders", "lock_owner"):
        op.add_column("scheduled_reminders", sa.Column("lock_owner", sa.String(length=64), nullable=True))

    op.execute("UPDATE reminder_rules_global SET j20_enabled = false")
    op.alter_column(
        "reminder_rules_global",
        "j20_enabled",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )

    if not has_table("notification_events"):
        op.create_table(
            "notification_events",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("subscriber_id", sa.String(length=36), nullable=False),
            sa.Column("card_id", sa.String(length=36), nullable=True),
            sa.Column("scheduled_reminder_id", sa.String(length=36), nullable=True),
            sa.Column("channel", sa.String(length=16), nullable=False, server_default="email"),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("provider_message_id", sa.String(length=128), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["card_id"], ["credit_cards.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["scheduled_reminder_id"], ["scheduled_reminders.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not has_index("notification_events", op.f("ix_notification_events_subscriber_id")):
        op.create_index(op.f("ix_notification_events_subscriber_id"), "notification_events", ["subscriber_id"], unique=False)
    if not has_index("notification_events", op.f("ix_notification_events_card_id")):
        op.create_index(op.f("ix_notification_events_card_id"), "notification_events", ["card_id"], unique=False)
    if not has_index("notification_events", op.f("ix_notification_events_scheduled_reminder_id")):
        op.create_index(op.f("ix_notification_events_scheduled_reminder_id"), "notification_events", ["scheduled_reminder_id"], unique=False)
    if not has_index("notification_events", op.f("ix_notification_events_created_at")):
        op.create_index(op.f("ix_notification_events_created_at"), "notification_events", ["created_at"], unique=False)

    if not has_table("preference_access_tokens"):
        op.create_table(
            "preference_access_tokens",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("subscriber_id", sa.String(length=36), nullable=False),
            sa.Column("focused_card_id", sa.String(length=36), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["focused_card_id"], ["credit_cards.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )
    if not has_index("preference_access_tokens", op.f("ix_preference_access_tokens_token_hash")):
        op.create_index(op.f("ix_preference_access_tokens_token_hash"), "preference_access_tokens", ["token_hash"], unique=True)
    if not has_index("preference_access_tokens", op.f("ix_preference_access_tokens_subscriber_id")):
        op.create_index(op.f("ix_preference_access_tokens_subscriber_id"), "preference_access_tokens", ["subscriber_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_preference_access_tokens_subscriber_id"), table_name="preference_access_tokens")
    op.drop_index(op.f("ix_preference_access_tokens_token_hash"), table_name="preference_access_tokens")
    op.drop_table("preference_access_tokens")

    op.drop_index(op.f("ix_notification_events_created_at"), table_name="notification_events")
    op.drop_index(op.f("ix_notification_events_scheduled_reminder_id"), table_name="notification_events")
    op.drop_index(op.f("ix_notification_events_card_id"), table_name="notification_events")
    op.drop_index(op.f("ix_notification_events_subscriber_id"), table_name="notification_events")
    op.drop_table("notification_events")

    op.alter_column(
        "reminder_rules_global",
        "j20_enabled",
        existing_type=sa.Boolean(),
        server_default=None,
        existing_nullable=False,
    )

    op.drop_column("scheduled_reminders", "lock_owner")
    op.drop_column("scheduled_reminders", "locked_at")
    op.drop_column("scheduled_reminders", "attempt_count")
    op.drop_column("scheduled_reminders", "channel")

    op.drop_column("credit_cards", "sms_enabled")
    op.drop_column("credit_cards", "email_enabled")

    op.drop_column("subscribers", "sms_enabled")
    op.drop_column("subscribers", "email_enabled")
    op.drop_column("subscribers", "signup_source")
    op.drop_column("subscribers", "phone")
    op.drop_column("subscribers", "last_name")
    op.drop_column("subscribers", "first_name")
