from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import get_current_admin, get_db
from app.models import AdminUser, AuditLog, CreditCard, EmailEvent, ScheduledReminder, Subscriber, WebhookEvent
from app.schemas import AuditLogOut, DashboardSummaryOut, EmailEventOut, RunDueResponse, ScheduledReminderOut
from app.services.scheduler import process_due_reminders


router = APIRouter(prefix="/v1/admin", tags=["events"])


@router.get("/dashboard-summary", response_model=DashboardSummaryOut)
def dashboard_summary(
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)

    total_subscribers = db.query(Subscriber).count()
    active_subscribers = db.query(Subscriber).filter(Subscriber.status == "active").count()
    paused_subscribers = db.query(Subscriber).filter(Subscriber.status == "paused").count()
    unsubscribed_subscribers = db.query(Subscriber).filter(Subscriber.status == "unsubscribed").count()

    total_cards = db.query(CreditCard).count()
    active_cards = db.query(CreditCard).filter(CreditCard.is_active.is_(True)).count()

    queued_reminders = db.query(ScheduledReminder).filter(ScheduledReminder.status == "queued").count()
    due_reminders = (
        db.query(ScheduledReminder)
        .filter(ScheduledReminder.status == "queued", ScheduledReminder.planned_send_at <= now)
        .count()
    )

    sent_last_24h = (
        db.query(EmailEvent)
        .filter(EmailEvent.event_type == "sent", EmailEvent.created_at >= day_ago)
        .count()
    )
    failed_last_24h = (
        db.query(EmailEvent)
        .filter(EmailEvent.event_type == "failed", EmailEvent.created_at >= day_ago)
        .count()
    )
    cancelled_last_24h = (
        db.query(EmailEvent)
        .filter(EmailEvent.event_type == "cancelled", EmailEvent.created_at >= day_ago)
        .count()
    )

    return DashboardSummaryOut(
        total_subscribers=total_subscribers,
        active_subscribers=active_subscribers,
        paused_subscribers=paused_subscribers,
        unsubscribed_subscribers=unsubscribed_subscribers,
        total_cards=total_cards,
        active_cards=active_cards,
        queued_reminders=queued_reminders,
        due_reminders=due_reminders,
        sent_last_24h=sent_last_24h,
        failed_last_24h=failed_last_24h,
        cancelled_last_24h=cancelled_last_24h,
    )


@router.get("/email-events", response_model=list[EmailEventOut])
def list_email_events(
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    event_type: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    query = db.query(EmailEvent).order_by(EmailEvent.created_at.desc())
    if event_type:
        query = query.filter(EmailEvent.event_type == event_type)
    if provider:
        query = query.filter(EmailEvent.provider == provider)
    return query.offset(offset).limit(limit).all()


@router.get("/scheduled-reminders", response_model=list[ScheduledReminderOut])
def list_scheduled_reminders(
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None),
    subscriber_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    query = db.query(ScheduledReminder).order_by(ScheduledReminder.planned_send_at.asc())
    if status_filter:
        query = query.filter(ScheduledReminder.status == status_filter)
    if subscriber_id:
        query = query.filter(ScheduledReminder.subscriber_id == subscriber_id)
    return query.offset(offset).limit(limit).all()


@router.post("/scheduled-reminders/run-due", response_model=RunDueResponse)
def run_due_reminders(
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    result = process_due_reminders(db, batch_size=500)
    return RunDueResponse(**result)


@router.get("/webhook-events")
def list_webhook_events(
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
):
    rows = db.query(WebhookEvent).order_by(WebhookEvent.processed_at.desc()).limit(limit).all()
    return [
        {
            "id": row.id,
            "event_name": row.event_name,
            "idempotency_key": row.idempotency_key,
            "signature_valid": row.signature_valid,
            "processed_at": row.processed_at,
        }
        for row in rows
    ]


@router.get("/audit-logs", response_model=list[AuditLogOut])
def list_audit_logs(
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    query = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    return query.offset(offset).limit(limit).all()
