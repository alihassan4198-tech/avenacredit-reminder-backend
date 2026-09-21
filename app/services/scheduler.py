import hashlib
import json
from datetime import date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    CreditCard,
    EmailEvent,
    ReminderOverride,
    ReminderRuleGlobal,
    ScheduledReminder,
    Subscriber,
)
from app.services.email_provider import send_email
from app.services.email_templates import ReminderEmailContent, build_reminder_email_content
from app.services.preferences import create_preference_access_token, is_reminder_enabled


def _statement_date_for_month(year: int, month: int, statement_day: int) -> date:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    day = min(statement_day, last_day)
    return date(year, month, day)


def _next_statement_dates(statement_day: int, months: int, now_local: date) -> list[date]:
    results: list[date] = []
    year = now_local.year
    month = now_local.month

    for _ in range(months + 1):
        dt = _statement_date_for_month(year, month, statement_day)
        if dt >= now_local:
            results.append(dt)

        month += 1
        if month > 12:
            month = 1
            year += 1

    return results


def _make_dedupe_key(subscriber_id: str, card_id: str, reminder_type: str, channel: str, statement_date: date) -> str:
    raw = f"{subscriber_id}:{card_id}:{reminder_type}:{channel}:{statement_date.isoformat()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _resolve_offset(db: Session, subscriber_id: str, card_id: str, reminder_type: str, default_offset: int) -> tuple[int, bool]:
    override = (
        db.query(ReminderOverride)
        .filter(
            ReminderOverride.subscriber_id == subscriber_id,
            ReminderOverride.reminder_type == reminder_type,
            ReminderOverride.enabled.is_(True),
            ((ReminderOverride.card_id == card_id) | (ReminderOverride.card_id.is_(None))),
        )
        .order_by(ReminderOverride.card_id.is_(None))
        .first()
    )

    if not override:
        return default_offset, True
    return override.offset_days, True


def _get_rules(db: Session) -> ReminderRuleGlobal:
    rules = db.query(ReminderRuleGlobal).first()
    if rules:
        return rules

    rules = ReminderRuleGlobal(
        j20_enabled=False,
        j20_offset_days=20,
        j5_enabled=True,
        j5_offset_days=5,
        timezone=settings.default_timezone,
    )
    db.add(rules)
    db.flush()
    return rules


def rebuild_schedule_for_subscriber(db: Session, subscriber_id: str) -> int:
    subscriber = db.query(Subscriber).filter(Subscriber.id == subscriber_id).first()
    if not subscriber:
        return 0

    rules = _get_rules(db)

    tz = ZoneInfo(subscriber.timezone or rules.timezone or settings.default_timezone)
    local_today = datetime.now(tz).date()

    db.query(ScheduledReminder).filter(
        ScheduledReminder.subscriber_id == subscriber_id,
        ScheduledReminder.status == "queued",
    ).delete(synchronize_session=False)

    if subscriber.status != "active" or not subscriber.email_enabled:
        return 0

    reminders_created = 0
    cards = (
        db.query(CreditCard)
        .filter(
            CreditCard.subscriber_id == subscriber_id,
            CreditCard.is_active.is_(True),
            CreditCard.email_enabled.is_(True),
        )
        .all()
    )

    for card in cards:
        if not card.is_active or not card.email_enabled:
            continue

        statement_dates = _next_statement_dates(card.statement_day, settings.scheduler_horizon_months, local_today)

        for statement_date in statement_dates:
            reminder_specs: list[tuple[str, int, bool]] = [
                ("J20", rules.j20_offset_days, rules.j20_enabled),
                ("J5", rules.j5_offset_days, rules.j5_enabled),
            ]

            for reminder_type, default_offset, enabled in reminder_specs:
                if not enabled:
                    continue

                offset_days, _ = _resolve_offset(db, subscriber.id, card.id, reminder_type, default_offset)
                planned_local = datetime.combine(statement_date, datetime.min.time()).replace(tzinfo=tz)
                planned_local = planned_local - timedelta(days=offset_days)
                planned_local = planned_local.replace(hour=settings.reminder_send_hour_local, minute=0, second=0, microsecond=0)
                planned_send_at = planned_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

                if planned_send_at < datetime.utcnow() - timedelta(days=1):
                    continue

                channel = "email"
                dedupe_key = _make_dedupe_key(subscriber.id, card.id, reminder_type, channel, statement_date)

                exists = db.query(ScheduledReminder).filter(ScheduledReminder.dedupe_key == dedupe_key).first()
                if exists:
                    continue

                db.add(
                    ScheduledReminder(
                        subscriber_id=subscriber.id,
                        card_id=card.id,
                        reminder_type=reminder_type,
                        channel=channel,
                        target_statement_date=statement_date,
                        planned_send_at=planned_send_at,
                        dedupe_key=dedupe_key,
                        status="queued",
                    )
                )
                reminders_created += 1

    return reminders_created


def rebuild_schedule_for_all_subscribers(db: Session) -> int:
    subscribers = db.query(Subscriber).all()
    total = 0
    for subscriber in subscribers:
        total += rebuild_schedule_for_subscriber(db, subscriber.id)
    return total


def _render_email_content(
    db: Session,
    reminder: ScheduledReminder,
    subscriber: Subscriber,
    card: CreditCard,
) -> ReminderEmailContent:
    target_balance = int(round(card.credit_limit_cents * 0.30))
    pref_token = create_preference_access_token(
        db,
        subscriber_id=subscriber.id,
        focused_card_id=card.id,
    )
    preferences_url = f"{settings.app_base_url}/unsubscribe?token={pref_token}"

    return build_reminder_email_content(
        subscriber_language=subscriber.language,
        subscriber_first_name=subscriber.first_name,
        card_name=card.card_name,
        card_credit_limit_cents=card.credit_limit_cents,
        reminder_type=reminder.reminder_type,
        statement_date=reminder.target_statement_date,
        preferences_url=preferences_url,
        target_balance_cents=target_balance,
    )


def _render_email(db: Session, reminder: ScheduledReminder, subscriber: Subscriber, card: CreditCard) -> tuple[str, str]:
    content = _render_email_content(db, reminder, subscriber, card)
    return content.subject, content.text_body


def _clear_lock(reminder: ScheduledReminder) -> None:
    reminder.locked_at = None
    reminder.lock_owner = None


def _cancel_reminder(db: Session, reminder: ScheduledReminder, reason: str) -> None:
    reminder.status = "cancelled"
    _clear_lock(reminder)
    db.add(
        EmailEvent(
            scheduled_reminder_id=reminder.id,
            provider="system",
            event_type="cancelled",
            payload_json=json.dumps({"reason": reason}),
        )
    )


def _mark_send_failure(
    db: Session,
    *,
    reminder: ScheduledReminder,
    provider: str,
    provider_message_id: str,
    reason: str,
    max_attempts: int,
) -> str:
    next_status = "failed" if reminder.attempt_count >= max_attempts else "queued"
    reminder.status = next_status
    _clear_lock(reminder)

    db.add(
        EmailEvent(
            scheduled_reminder_id=reminder.id,
            provider=provider,
            provider_message_id=provider_message_id or None,
            event_type="failed",
            payload_json=json.dumps({"reason": reason, "attempt_count": reminder.attempt_count}),
        )
    )
    return next_status


def recover_stale_processing_jobs(
    db: Session,
    *,
    now: datetime,
    max_attempts: int,
    processing_timeout_minutes: int,
) -> dict[str, int]:
    stale_before = now - timedelta(minutes=processing_timeout_minutes)
    stale_jobs = (
        db.query(ScheduledReminder)
        .filter(
            ScheduledReminder.status == "processing",
            ScheduledReminder.locked_at.is_not(None),
            ScheduledReminder.locked_at < stale_before,
        )
        .order_by(ScheduledReminder.locked_at.asc())
        .with_for_update(skip_locked=True)
        .all()
    )

    requeued = 0
    failed = 0

    for reminder in stale_jobs:
        if reminder.attempt_count >= max_attempts:
            reminder.status = "failed"
            _clear_lock(reminder)
            db.add(
                EmailEvent(
                    scheduled_reminder_id=reminder.id,
                    provider="system",
                    event_type="failed",
                    payload_json=json.dumps({"reason": "processing_timeout_max_attempts"}),
                )
            )
            failed += 1
        else:
            reminder.status = "queued"
            _clear_lock(reminder)
            requeued += 1

    db.commit()
    return {"requeued": requeued, "failed": failed}


def acquire_due_reminders(
    db: Session,
    *,
    now: datetime,
    batch_size: int,
    worker_id: str,
) -> list[str]:
    due_jobs = (
        db.query(ScheduledReminder)
        .filter(
            ScheduledReminder.status == "queued",
            ScheduledReminder.planned_send_at <= now,
        )
        .order_by(ScheduledReminder.planned_send_at.asc(), ScheduledReminder.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(batch_size)
        .all()
    )

    reminder_ids: list[str] = []
    for reminder in due_jobs:
        reminder.status = "processing"
        reminder.locked_at = now
        reminder.lock_owner = worker_id
        reminder.attempt_count = (reminder.attempt_count or 0) + 1
        reminder_ids.append(reminder.id)

    db.commit()
    return reminder_ids


def process_due_reminders(
    db: Session,
    batch_size: int = 100,
    *,
    worker_id: str | None = None,
) -> dict[str, int]:
    max_attempts = max(1, settings.reminder_max_attempts)
    processing_timeout_minutes = max(1, settings.reminder_processing_timeout_minutes)
    owner = worker_id or f"worker-{uuid4().hex[:12]}"

    now = datetime.utcnow()
    recover_stale_processing_jobs(
        db,
        now=now,
        max_attempts=max_attempts,
        processing_timeout_minutes=processing_timeout_minutes,
    )

    reminder_ids = acquire_due_reminders(
        db,
        now=now,
        batch_size=batch_size,
        worker_id=owner,
    )

    sent = 0
    failed = 0
    cancelled = 0
    processed = 0

    for reminder_id in reminder_ids:
        reminder = (
            db.query(ScheduledReminder)
            .filter(
                ScheduledReminder.id == reminder_id,
                ScheduledReminder.status == "processing",
                ScheduledReminder.lock_owner == owner,
            )
            .first()
        )
        if not reminder:
            continue

        processed += 1
        subscriber = db.query(Subscriber).filter(Subscriber.id == reminder.subscriber_id).first()
        card = db.query(CreditCard).filter(CreditCard.id == reminder.card_id).first()

        if not subscriber or not card:
            _cancel_reminder(db, reminder, "missing_subscriber_or_card")
            cancelled += 1
            db.commit()
            continue

        if reminder.channel != "email":
            _cancel_reminder(db, reminder, "unsupported_channel")
            cancelled += 1
            db.commit()
            continue

        if subscriber.status != "active" or not subscriber.email_enabled or not card.is_active or not card.email_enabled:
            _cancel_reminder(db, reminder, "inactive_or_email_disabled")
            cancelled += 1
            db.commit()
            continue

        if not is_reminder_enabled(
            db,
            subscriber_id=subscriber.id,
            card_id=card.id,
            reminder_type=reminder.reminder_type,
        ):
            _cancel_reminder(db, reminder, "preference_disabled")
            cancelled += 1
            db.commit()
            continue

        content = _render_email_content(db, reminder, subscriber, card)

        try:
            result = send_email(
                to_email=subscriber.email,
                subject=content.subject,
                body_text=content.text_body,
                body_html=content.html_body,
            )
            if result.accepted:
                reminder.status = "sent"
                _clear_lock(reminder)
                db.add(
                    EmailEvent(
                        scheduled_reminder_id=reminder.id,
                        provider=result.provider,
                        provider_message_id=result.message_id,
                        event_type="sent",
                        payload_json=json.dumps({"subject": content.subject}),
                    )
                )
                sent += 1
            else:
                next_status = _mark_send_failure(
                    db,
                    reminder=reminder,
                    provider=result.provider,
                    provider_message_id=result.message_id,
                    reason="provider_rejected",
                    max_attempts=max_attempts,
                )
                if next_status == "failed":
                    failed += 1
        except Exception as exc:
            next_status = _mark_send_failure(
                db,
                reminder=reminder,
                provider="system",
                provider_message_id="",
                reason=str(exc),
                max_attempts=max_attempts,
            )
            if next_status == "failed":
                failed += 1

        db.commit()

    return {"processed": processed, "sent": sent, "failed": failed, "cancelled": cancelled}
