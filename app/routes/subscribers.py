from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.deps import get_current_admin, get_db
from app.models import AdminUser, AuditLog, CreditCard, EmailEvent, ReminderOverride, ScheduledReminder, Subscriber
from app.schemas import (
    CardCreate,
    CardOut,
    CardStatusUpdate,
    CardUpdate,
    PreferenceLinkResponse,
    ReminderOverrideCreate,
    ReminderOverrideOut,
    ReminderOverridePatch,
    SubscriberCreate,
    SubscriberOut,
    SubscriberStatusUpdate,
    SubscriberUpdate,
)
from app.services.audit import write_audit
from app.services.preferences import create_preference_access_token
from app.services.scheduler import rebuild_schedule_for_subscriber


router = APIRouter(prefix="/v1/admin", tags=["subscribers"])


def _validate_timezone(timezone_name: str) -> None:
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid timezone") from exc


@router.get("/subscribers", response_model=list[SubscriberOut])
def list_subscribers(
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, pattern="^(active|paused|unsubscribed|inactive)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    query = db.query(Subscriber).options(joinedload(Subscriber.cards)).order_by(Subscriber.created_at.desc())
    if q:
        query = query.filter(Subscriber.email.ilike(f"%{q}%"))
    if status_filter:
        query = query.filter(Subscriber.status == status_filter)
    return query.offset(offset).limit(limit).all()


@router.post("/subscribers", response_model=SubscriberOut, status_code=status.HTTP_201_CREATED)
def create_subscriber(
    payload: SubscriberCreate,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(Subscriber).filter(Subscriber.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Subscriber already exists")

    _validate_timezone(payload.timezone)

    subscriber = Subscriber(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email.lower(),
        phone=payload.phone,
        signup_source=payload.signup_source,
        language=payload.language,
        timezone=payload.timezone,
        status=payload.status,
        email_enabled=payload.email_enabled,
    )
    db.add(subscriber)
    db.flush()

    rebuild_schedule_for_subscriber(db, subscriber.id)
    write_audit(
        db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="subscriber.create",
        entity_type="subscriber",
        entity_id=subscriber.id,
        diff={"email": subscriber.email},
    )

    db.commit()
    db.refresh(subscriber)
    return subscriber


@router.get("/subscribers/{subscriber_id}", response_model=SubscriberOut)
def get_subscriber(
    subscriber_id: str,
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    subscriber = (
        db.query(Subscriber)
        .options(joinedload(Subscriber.cards))
        .filter(Subscriber.id == subscriber_id)
        .first()
    )
    if not subscriber:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")
    return subscriber


@router.patch("/subscribers/{subscriber_id}", response_model=SubscriberOut)
def patch_subscriber(
    subscriber_id: str,
    payload: SubscriberUpdate,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    subscriber = db.query(Subscriber).filter(Subscriber.id == subscriber_id).first()
    if not subscriber:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")

    diff: dict[str, str | bool] = {}
    should_rebuild = False

    if payload.first_name is not None and payload.first_name != subscriber.first_name:
        diff["first_name"] = f"{subscriber.first_name}->{payload.first_name}"
        subscriber.first_name = payload.first_name
    if payload.last_name is not None and payload.last_name != subscriber.last_name:
        diff["last_name"] = f"{subscriber.last_name}->{payload.last_name}"
        subscriber.last_name = payload.last_name
    if payload.email is not None and payload.email.lower() != subscriber.email:
        duplicate = (
            db.query(Subscriber)
            .filter(Subscriber.email == payload.email.lower(), Subscriber.id != subscriber.id)
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Subscriber email already in use")
        diff["email"] = f"{subscriber.email}->{payload.email.lower()}"
        subscriber.email = payload.email.lower()
    if payload.phone is not None and payload.phone != subscriber.phone:
        diff["phone"] = f"{subscriber.phone}->{payload.phone}"
        subscriber.phone = payload.phone
    if payload.signup_source is not None and payload.signup_source != subscriber.signup_source:
        diff["signup_source"] = f"{subscriber.signup_source}->{payload.signup_source}"
        subscriber.signup_source = payload.signup_source
    if payload.language is not None and payload.language != subscriber.language:
        diff["language"] = f"{subscriber.language}->{payload.language}"
        subscriber.language = payload.language
    if payload.timezone is not None and payload.timezone != subscriber.timezone:
        _validate_timezone(payload.timezone)
        diff["timezone"] = f"{subscriber.timezone}->{payload.timezone}"
        subscriber.timezone = payload.timezone
        should_rebuild = True
    if payload.status is not None and payload.status != subscriber.status:
        diff["status"] = f"{subscriber.status}->{payload.status}"
        subscriber.status = payload.status
        should_rebuild = True
    if payload.email_enabled is not None and payload.email_enabled != subscriber.email_enabled:
        diff["email_enabled"] = payload.email_enabled
        subscriber.email_enabled = payload.email_enabled
        should_rebuild = True

    if should_rebuild:
        db.flush()
        rebuild_schedule_for_subscriber(db, subscriber.id)
    write_audit(
        db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="subscriber.update",
        entity_type="subscriber",
        entity_id=subscriber.id,
        diff=diff,
    )

    db.commit()
    db.refresh(subscriber)
    return subscriber


@router.patch("/subscribers/{subscriber_id}/status", response_model=SubscriberOut)
def patch_subscriber_status(
    subscriber_id: str,
    payload: SubscriberStatusUpdate,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    subscriber = db.query(Subscriber).filter(Subscriber.id == subscriber_id).first()
    if not subscriber:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")

    subscriber.status = payload.status

    db.flush()
    rebuild_schedule_for_subscriber(db, subscriber.id)
    write_audit(
        db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="subscriber.status",
        entity_type="subscriber",
        entity_id=subscriber.id,
        diff={"status": payload.status},
    )

    db.commit()
    db.refresh(subscriber)
    return subscriber


@router.post("/subscribers/{subscriber_id}/cards", response_model=CardOut, status_code=status.HTTP_201_CREATED)
def add_card(
    subscriber_id: str,
    payload: CardCreate,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    subscriber = db.query(Subscriber).filter(Subscriber.id == subscriber_id).first()
    if not subscriber:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")

    card = CreditCard(
        subscriber_id=subscriber.id,
        card_name=payload.card_name,
        card_type=payload.card_type,
        credit_limit_cents=payload.credit_limit_cents,
        statement_day=payload.statement_day,
        is_active=True,
        email_enabled=payload.email_enabled,
        sms_enabled=False,
    )
    db.add(card)
    db.flush()

    rebuild_schedule_for_subscriber(db, subscriber.id)
    write_audit(
        db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="card.create",
        entity_type="card",
        entity_id=card.id,
        diff={"subscriber_id": subscriber.id},
    )

    db.commit()
    db.refresh(card)
    return card


@router.patch("/cards/{card_id}", response_model=CardOut)
def patch_card(
    card_id: str,
    payload: CardUpdate,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    card = db.query(CreditCard).filter(CreditCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")

    diff: dict[str, str | bool] = {}
    should_rebuild = False
    if payload.card_name is not None and payload.card_name != card.card_name:
        diff["card_name"] = f"{card.card_name}->{payload.card_name}"
        card.card_name = payload.card_name
    if payload.card_type is not None and payload.card_type != card.card_type:
        diff["card_type"] = f"{card.card_type}->{payload.card_type}"
        card.card_type = payload.card_type
    if payload.credit_limit_cents is not None and payload.credit_limit_cents != card.credit_limit_cents:
        diff["credit_limit_cents"] = f"{card.credit_limit_cents}->{payload.credit_limit_cents}"
        card.credit_limit_cents = payload.credit_limit_cents
        should_rebuild = True
    if payload.statement_day is not None and payload.statement_day != card.statement_day:
        diff["statement_day"] = f"{card.statement_day}->{payload.statement_day}"
        card.statement_day = payload.statement_day
        should_rebuild = True
    if payload.is_active is not None and payload.is_active != card.is_active:
        diff["is_active"] = payload.is_active
        card.is_active = payload.is_active
        should_rebuild = True
    if payload.email_enabled is not None and payload.email_enabled != card.email_enabled:
        diff["email_enabled"] = payload.email_enabled
        card.email_enabled = payload.email_enabled
        should_rebuild = True

    if should_rebuild:
        db.flush()
        rebuild_schedule_for_subscriber(db, card.subscriber_id)
    write_audit(
        db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="card.update",
        entity_type="card",
        entity_id=card.id,
        diff=diff,
    )

    db.commit()
    db.refresh(card)
    return card


@router.patch("/cards/{card_id}/status", response_model=CardOut)
def patch_card_status(
    card_id: str,
    payload: CardStatusUpdate,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    card = db.query(CreditCard).filter(CreditCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")

    card.is_active = payload.is_active

    db.flush()
    rebuild_schedule_for_subscriber(db, card.subscriber_id)
    write_audit(
        db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="card.status",
        entity_type="card",
        entity_id=card.id,
        diff={"is_active": payload.is_active},
    )

    db.commit()
    db.refresh(card)
    return card


@router.delete("/cards/{card_id}")
def archive_card(
    card_id: str,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    card = db.query(CreditCard).filter(CreditCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")

    if card.is_active:
        card.is_active = False

    rebuild_schedule_for_subscriber(db, card.subscriber_id)
    write_audit(
        db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="card.archive",
        entity_type="card",
        entity_id=card.id,
        diff={"is_active": False},
    )

    db.commit()
    return {"ok": True}


@router.get("/subscribers/{subscriber_id}/overrides", response_model=list[ReminderOverrideOut])
def list_overrides(
    subscriber_id: str,
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return (
        db.query(ReminderOverride)
        .filter(ReminderOverride.subscriber_id == subscriber_id)
        .order_by(ReminderOverride.updated_at.desc())
        .all()
    )


@router.post("/subscribers/{subscriber_id}/overrides", response_model=ReminderOverrideOut, status_code=status.HTTP_201_CREATED)
def create_override(
    subscriber_id: str,
    payload: ReminderOverrideCreate,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    subscriber = db.query(Subscriber).filter(Subscriber.id == subscriber_id).first()
    if not subscriber:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")

    override = ReminderOverride(
        subscriber_id=subscriber.id,
        card_id=payload.card_id,
        reminder_type=payload.reminder_type,
        offset_days=payload.offset_days,
        enabled=payload.enabled,
    )
    db.add(override)
    db.flush()

    rebuild_schedule_for_subscriber(db, subscriber.id)
    write_audit(
        db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="override.create",
        entity_type="override",
        entity_id=override.id,
        diff={"offset_days": payload.offset_days, "reminder_type": payload.reminder_type},
    )

    db.commit()
    db.refresh(override)
    return override


@router.patch("/overrides/{override_id}", response_model=ReminderOverrideOut)
def patch_override(
    override_id: str,
    payload: ReminderOverridePatch,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    override = db.query(ReminderOverride).filter(ReminderOverride.id == override_id).first()
    if not override:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Override not found")

    diff: dict[str, str | bool] = {}
    if payload.offset_days is not None and payload.offset_days != override.offset_days:
        diff["offset_days"] = f"{override.offset_days}->{payload.offset_days}"
        override.offset_days = payload.offset_days
    if payload.enabled is not None and payload.enabled != override.enabled:
        diff["enabled"] = payload.enabled
        override.enabled = payload.enabled

    rebuild_schedule_for_subscriber(db, override.subscriber_id)
    write_audit(
        db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="override.update",
        entity_type="override",
        entity_id=override.id,
        diff=diff,
    )

    db.commit()
    db.refresh(override)
    return override


@router.delete("/overrides/{override_id}")
def delete_override(
    override_id: str,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    override = db.query(ReminderOverride).filter(ReminderOverride.id == override_id).first()
    if not override:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Override not found")

    subscriber_id = override.subscriber_id
    db.delete(override)

    rebuild_schedule_for_subscriber(db, subscriber_id)
    write_audit(
        db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="override.delete",
        entity_type="override",
        entity_id=override_id,
        diff={},
    )

    db.commit()
    return {"ok": True}


@router.get("/subscribers/{subscriber_id}/preference-link", response_model=PreferenceLinkResponse)
def get_preference_link(
    subscriber_id: str,
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    subscriber = db.query(Subscriber).filter(Subscriber.id == subscriber_id).first()
    if not subscriber:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")

    token = create_preference_access_token(db, subscriber_id=subscriber.id)
    db.commit()
    return PreferenceLinkResponse(url=f"{settings.app_base_url}/unsubscribe?token={token}")


@router.get("/subscribers/{subscriber_id}/activity")
def get_subscriber_activity(
    subscriber_id: str,
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
):
    subscriber = db.query(Subscriber).filter(Subscriber.id == subscriber_id).first()
    if not subscriber:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")

    card_ids = [card.id for card in subscriber.cards]

    override_ids = [row.id for row in db.query(ReminderOverride).filter(ReminderOverride.subscriber_id == subscriber_id).all()]

    query = db.query(AuditLog).filter(
        or_(
            (AuditLog.entity_type == "subscriber") & (AuditLog.entity_id == subscriber_id),
            (AuditLog.entity_type == "card") & (AuditLog.entity_id.in_(card_ids if card_ids else ["no-cards"])),
            (AuditLog.entity_type == "override") & (AuditLog.entity_id.in_(override_ids if override_ids else ["no-overrides"])),
        )
    )

    rows = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": row.id,
            "created_at": row.created_at,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "actor_type": row.actor_type,
            "actor_id": row.actor_id,
            "diff_json": row.diff_json,
        }
        for row in rows
    ]


@router.get("/subscribers/{subscriber_id}/email-events")
def get_subscriber_email_events(
    subscriber_id: str,
    _: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=500),
):
    subscriber = db.query(Subscriber).filter(Subscriber.id == subscriber_id).first()
    if not subscriber:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")

    rows = (
        db.query(EmailEvent, ScheduledReminder)
        .join(ScheduledReminder, ScheduledReminder.id == EmailEvent.scheduled_reminder_id)
        .filter(ScheduledReminder.subscriber_id == subscriber_id)
        .order_by(EmailEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": event.id,
            "created_at": event.created_at,
            "provider": event.provider,
            "event_type": event.event_type,
            "provider_message_id": event.provider_message_id,
            "scheduled_reminder_id": event.scheduled_reminder_id,
            "card_id": reminder.card_id,
            "payload_json": event.payload_json,
        }
        for event, reminder in rows
    ]
