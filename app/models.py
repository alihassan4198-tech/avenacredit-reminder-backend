from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.utcnow()


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="admin")
    status: Mapped[str] = mapped_column(String(32), default="active")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Subscriber(Base):
    __tablename__ = "subscribers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    signup_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language: Mapped[str] = mapped_column(String(8), default="en")
    status: Mapped[str] = mapped_column(String(32), default="active")
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    timezone: Mapped[str] = mapped_column(String(64), default="America/Toronto")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    cards: Mapped[list["CreditCard"]] = relationship(back_populates="subscriber", cascade="all, delete-orphan")


class CreditCard(Base):
    __tablename__ = "credit_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    subscriber_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscribers.id", ondelete="CASCADE"), index=True)
    card_name: Mapped[str] = mapped_column(String(255))
    card_type: Mapped[str] = mapped_column(String(64))
    credit_limit_cents: Mapped[int] = mapped_column(Integer)
    statement_day: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    subscriber: Mapped[Subscriber] = relationship(back_populates="cards")


class ReminderRuleGlobal(Base):
    __tablename__ = "reminder_rules_global"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    j20_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    j20_offset_days: Mapped[int] = mapped_column(Integer, default=20)
    j5_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    j5_offset_days: Mapped[int] = mapped_column(Integer, default=5)
    timezone: Mapped[str] = mapped_column(String(64), default="America/Toronto")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_name: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    payload_json: Mapped[str] = mapped_column(Text)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (UniqueConstraint("id", name="uq_audit_logs_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_type: Mapped[str] = mapped_column(String(32), default="system")
    actor_id: Mapped[str] = mapped_column(String(36), default="system")
    action: Mapped[str] = mapped_column(String(128))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(36))
    diff_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ScheduledReminder(Base):
    __tablename__ = "scheduled_reminders"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_scheduled_reminders_dedupe_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    subscriber_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscribers.id", ondelete="CASCADE"), index=True)
    card_id: Mapped[str] = mapped_column(String(36), ForeignKey("credit_cards.id", ondelete="CASCADE"), index=True)
    reminder_type: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(16), default="email")
    target_statement_date: Mapped[date] = mapped_column(Date)
    planned_send_at: Mapped[datetime] = mapped_column(DateTime)
    dedupe_key: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lock_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    subscriber_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscribers.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(16), default="global")
    card_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("credit_cards.id", ondelete="CASCADE"), nullable=True)
    reminder_type: Mapped[str] = mapped_column(String(16), default="all")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[str] = mapped_column(String(32), default="subscriber")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ReminderOverride(Base):
    __tablename__ = "reminder_overrides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    subscriber_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscribers.id", ondelete="CASCADE"), index=True)
    card_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("credit_cards.id", ondelete="CASCADE"), nullable=True)
    reminder_type: Mapped[str] = mapped_column(String(16))
    offset_days: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class EmailEvent(Base):
    __tablename__ = "email_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    scheduled_reminder_id: Mapped[str] = mapped_column(String(36), ForeignKey("scheduled_reminders.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="mock")
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class NotificationEvent(Base):
    __tablename__ = "notification_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    subscriber_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscribers.id", ondelete="CASCADE"), index=True)
    card_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("credit_cards.id", ondelete="SET NULL"), nullable=True, index=True)
    scheduled_reminder_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("scheduled_reminders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(16), default="email")
    provider: Mapped[str] = mapped_column(String(32), default="mock")
    status: Mapped[str] = mapped_column(String(32))
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PreferenceAccessToken(Base):
    __tablename__ = "preference_access_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    subscriber_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscribers.id", ondelete="CASCADE"), index=True)
    focused_card_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("credit_cards.id", ondelete="SET NULL"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
