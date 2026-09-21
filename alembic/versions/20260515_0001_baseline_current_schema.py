"""baseline current schema

Revision ID: 20260515_0001
Revises:
Create Date: 2026-05-15 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260515_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_admin_users_email"), "admin_users", ["email"], unique=True)

    op.create_table(
        "subscribers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_subscribers_email"), "subscribers", ["email"], unique=True)

    op.create_table(
        "reminder_rules_global",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("j20_enabled", sa.Boolean(), nullable=False),
        sa.Column("j20_offset_days", sa.Integer(), nullable=False),
        sa.Column("j5_enabled", sa.Boolean(), nullable=False),
        sa.Column("j5_offset_days", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_name", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("signature_valid", sa.Boolean(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(op.f("ix_webhook_events_idempotency_key"), "webhook_events", ["idempotency_key"], unique=True)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("diff_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", name="uq_audit_logs_id"),
    )

    op.create_table(
        "credit_cards",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subscriber_id", sa.String(length=36), nullable=False),
        sa.Column("card_name", sa.String(length=255), nullable=False),
        sa.Column("card_type", sa.String(length=64), nullable=False),
        sa.Column("credit_limit_cents", sa.Integer(), nullable=False),
        sa.Column("statement_day", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_credit_cards_subscriber_id"), "credit_cards", ["subscriber_id"], unique=False)

    op.create_table(
        "scheduled_reminders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subscriber_id", sa.String(length=36), nullable=False),
        sa.Column("card_id", sa.String(length=36), nullable=False),
        sa.Column("reminder_type", sa.String(length=16), nullable=False),
        sa.Column("target_statement_date", sa.Date(), nullable=False),
        sa.Column("planned_send_at", sa.DateTime(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["credit_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_scheduled_reminders_dedupe_key"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index(op.f("ix_scheduled_reminders_card_id"), "scheduled_reminders", ["card_id"], unique=False)
    op.create_index(op.f("ix_scheduled_reminders_subscriber_id"), "scheduled_reminders", ["subscriber_id"], unique=False)

    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subscriber_id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("card_id", sa.String(length=36), nullable=True),
        sa.Column("reminder_type", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["credit_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notification_preferences_subscriber_id"), "notification_preferences", ["subscriber_id"], unique=False)

    op.create_table(
        "reminder_overrides",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subscriber_id", sa.String(length=36), nullable=False),
        sa.Column("card_id", sa.String(length=36), nullable=True),
        sa.Column("reminder_type", sa.String(length=16), nullable=False),
        sa.Column("offset_days", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["credit_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reminder_overrides_subscriber_id"), "reminder_overrides", ["subscriber_id"], unique=False)

    op.create_table(
        "email_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scheduled_reminder_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_message_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["scheduled_reminder_id"], ["scheduled_reminders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_email_events_scheduled_reminder_id"), "email_events", ["scheduled_reminder_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_email_events_scheduled_reminder_id"), table_name="email_events")
    op.drop_table("email_events")

    op.drop_index(op.f("ix_reminder_overrides_subscriber_id"), table_name="reminder_overrides")
    op.drop_table("reminder_overrides")

    op.drop_index(op.f("ix_notification_preferences_subscriber_id"), table_name="notification_preferences")
    op.drop_table("notification_preferences")

    op.drop_index(op.f("ix_scheduled_reminders_subscriber_id"), table_name="scheduled_reminders")
    op.drop_index(op.f("ix_scheduled_reminders_card_id"), table_name="scheduled_reminders")
    op.drop_table("scheduled_reminders")

    op.drop_index(op.f("ix_credit_cards_subscriber_id"), table_name="credit_cards")
    op.drop_table("credit_cards")

    op.drop_table("audit_logs")

    op.drop_index(op.f("ix_webhook_events_idempotency_key"), table_name="webhook_events")
    op.drop_table("webhook_events")

    op.drop_table("reminder_rules_global")

    op.drop_index(op.f("ix_subscribers_email"), table_name="subscribers")
    op.drop_table("subscribers")

    op.drop_index(op.f("ix_admin_users_email"), table_name="admin_users")
    op.drop_table("admin_users")
