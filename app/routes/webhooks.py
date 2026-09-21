import hashlib
import hmac
import json
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import CreditCard, EmailEvent, ScheduledReminder, Subscriber, WebhookEvent
from app.schemas import WebhookPayloadV1, WebhookPayloadV2
from app.services.card_catalog import resolve_card_name
from app.services.audit import write_audit
from app.services.email_provider import send_email
from app.services.email_templates import WelcomeEmailCardSummary, build_welcome_email_content
from app.services.preferences import create_preference_access_token
from app.services.scheduler import rebuild_schedule_for_subscriber


router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


def validate_signature(raw_body: bytes, signature: str) -> bool:
    expected = hmac.new(settings.webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_webhook_payload(raw_body: bytes) -> tuple[str, WebhookPayloadV1 | WebhookPayloadV2]:
    try:
        payload_json = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body") from exc

    try:
        cards = payload_json.get("cards", []) if isinstance(payload_json, dict) else []
        if cards and isinstance(cards[0], dict) and "selectionType" in cards[0]:
            return "v2", WebhookPayloadV2.model_validate(payload_json)
        return "v1", WebhookPayloadV1.model_validate(payload_json)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc


def validate_timezone(timezone_name: str) -> None:
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid timezone") from exc


def _append_webhook_event_meta(
    webhook_event: WebhookEvent,
    *,
    welcome_status: str,
    provider: str,
    provider_message_id: str | None,
) -> None:
    try:
        payload_data = json.loads(webhook_event.payload_json)
        if not isinstance(payload_data, dict):
            payload_data = {"payload": webhook_event.payload_json}
    except json.JSONDecodeError:
        payload_data = {"payload": webhook_event.payload_json}

    payload_data["welcome_email"] = {
        "status": welcome_status,
        "provider": provider,
        "provider_message_id": provider_message_id or "",
    }
    webhook_event.payload_json = json.dumps(payload_data, default=str)


def _build_welcome_cards(db: Session, *, subscriber_id: str) -> list[WelcomeEmailCardSummary]:
    cards = (
        db.query(CreditCard)
        .filter(
            CreditCard.subscriber_id == subscriber_id,
            CreditCard.is_active.is_(True),
            CreditCard.email_enabled.is_(True),
        )
        .order_by(CreditCard.card_name.asc(), CreditCard.statement_day.asc())
        .all()
    )

    return [
        WelcomeEmailCardSummary(
            card_name=card.card_name,
            card_type=card.card_type,
            credit_limit_cents=card.credit_limit_cents,
            statement_day=card.statement_day,
        )
        for card in cards
    ]


def _get_welcome_anchor_reminder_id(db: Session, *, subscriber_id: str) -> str | None:
    reminder = (
        db.query(ScheduledReminder)
        .filter(ScheduledReminder.subscriber_id == subscriber_id)
        .order_by(ScheduledReminder.created_at.desc())
        .first()
    )
    if not reminder:
        return None
    return reminder.id


@router.post("/subscriber-onboarded")
async def subscriber_onboarded(
    request: Request,
    x_signature: str = Header(alias="X-Signature"),
    x_timestamp: str = Header(alias="X-Timestamp"),
    x_idempotency_key: str = Header(alias="X-Idempotency-Key"),
):
    raw_body = await request.body()

    try:
        timestamp = int(x_timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid timestamp") from exc

    now = int(time.time())
    if abs(now - timestamp) > settings.allowed_clock_skew_seconds:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Timestamp out of allowed window")

    signature_valid = validate_signature(raw_body=raw_body, signature=x_signature)
    if not signature_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    db: Session = SessionLocal()
    subscriber_id: str | None = None
    consent_email_for_welcome = True
    source = "legacy_webhook"
    try:
        existing_event = db.query(WebhookEvent).filter(WebhookEvent.idempotency_key == x_idempotency_key).first()
        if existing_event:
            return {"ok": True, "duplicate": True, "idempotent": True}

        payload_version, payload = parse_webhook_payload(raw_body)
        validate_timezone(payload.subscriber.timezone)

        event = WebhookEvent(
            event_name=payload.event,
            idempotency_key=x_idempotency_key,
            signature_valid=True,
            payload_json=json.dumps(payload.model_dump(), default=str),
        )
        db.add(event)

        subscriber = db.query(Subscriber).filter(Subscriber.email == payload.subscriber.email.lower()).first()
        consent_email = getattr(payload.subscriber, "consentEmail", True)
        consent_sms = getattr(payload.subscriber, "consentSms", False)
        consent_email_for_welcome = bool(consent_email)
        source = getattr(payload, "source", "legacy_webhook")
        if not subscriber:
            subscriber = Subscriber(
                first_name=getattr(payload.subscriber, "firstName", None),
                last_name=getattr(payload.subscriber, "lastName", None),
                email=payload.subscriber.email.lower(),
                phone=getattr(payload.subscriber, "phone", None),
            signup_source=source,
                language=payload.subscriber.language,
                timezone=payload.subscriber.timezone,
                status="active",
                email_enabled=consent_email,
                sms_enabled=consent_sms,
            )
            db.add(subscriber)
            db.flush()
        else:
            subscriber.first_name = getattr(payload.subscriber, "firstName", None)
            subscriber.last_name = getattr(payload.subscriber, "lastName", None)
            subscriber.phone = getattr(payload.subscriber, "phone", None)
            if hasattr(payload, "source"):
                subscriber.signup_source = payload.source
            subscriber.language = payload.subscriber.language
            subscriber.timezone = payload.subscriber.timezone
            subscriber.email_enabled = consent_email
            subscriber.sms_enabled = consent_sms

        for card_input in payload.cards:
            if payload_version == "v2":
                card_name = resolve_card_name(
                    selection_type=card_input.selectionType,
                    popular_card_key=card_input.popularCardKey,
                    custom_card_name=card_input.customCardName,
                )
                card_type = card_input.cardType
                statement_day = card_input.statementDay
                credit_limit_cents = int(card_input.creditLimit * 100)
            else:
                card_name = card_input.cardName.strip()
                card_type = card_input.cardType
                statement_day = card_input.statementDay
                credit_limit_cents = int(card_input.creditLimit * 100)

            existing_card = (
                db.query(CreditCard)
                .filter(
                    CreditCard.subscriber_id == subscriber.id,
                    CreditCard.card_name == card_name,
                    CreditCard.statement_day == statement_day,
                )
                .first()
            )

            if existing_card:
                existing_card.card_type = card_type
                existing_card.credit_limit_cents = credit_limit_cents
                existing_card.statement_day = statement_day
                existing_card.is_active = True
            else:
                db.add(
                    CreditCard(
                        subscriber_id=subscriber.id,
                        card_name=card_name,
                        card_type=card_type,
                        credit_limit_cents=credit_limit_cents,
                        statement_day=statement_day,
                        is_active=True,
                        email_enabled=True,
                        sms_enabled=False,
                    )
                )

        db.flush()
        subscriber_id = subscriber.id
        rebuild_schedule_for_subscriber(db, subscriber.id)
        write_audit(
            db,
            actor_type="system",
            actor_id="webhook",
            action="webhook.subscriber_onboarded",
            entity_type="subscriber",
            entity_id=subscriber.id,
            diff={
                "payload_version": payload_version,
                "cards_count": len(payload.cards),
                "source": source,
            },
        )

        db.commit()

        if not subscriber_id:
            return {"ok": True, "duplicate": False, "idempotent": False}

        subscriber = db.query(Subscriber).filter(Subscriber.id == subscriber_id).first()
        event = db.query(WebhookEvent).filter(WebhookEvent.idempotency_key == x_idempotency_key).first()
        if not subscriber or not event:
            return {"ok": True, "duplicate": False, "idempotent": False}

        if not subscriber.email or not subscriber.email_enabled or not consent_email_for_welcome:
            _append_webhook_event_meta(
                event,
                welcome_status="skipped",
                provider="system",
                provider_message_id="",
            )
            write_audit(
                db,
                actor_type="system",
                actor_id="webhook",
                action="welcome_email.skipped",
                entity_type="subscriber",
                entity_id=subscriber.id,
                diff={
                    "reason": "email_disabled_or_missing_consent",
                    "idempotency_key": x_idempotency_key,
                    "source": source,
                },
            )
            db.commit()
            return {"ok": True, "duplicate": False, "idempotent": False}

        cards = _build_welcome_cards(db, subscriber_id=subscriber.id)
        if not cards:
            _append_webhook_event_meta(
                event,
                welcome_status="skipped",
                provider="system",
                provider_message_id="",
            )
            write_audit(
                db,
                actor_type="system",
                actor_id="webhook",
                action="welcome_email.skipped",
                entity_type="subscriber",
                entity_id=subscriber.id,
                diff={
                    "reason": "no_active_email_cards",
                    "idempotency_key": x_idempotency_key,
                    "source": source,
                },
            )
            db.commit()
            return {"ok": True, "duplicate": False, "idempotent": False}

        pref_token = create_preference_access_token(db, subscriber_id=subscriber.id)
        preferences_url = f"{settings.app_base_url}/unsubscribe?token={pref_token}"
        welcome_content = build_welcome_email_content(
            subscriber_language=subscriber.language,
            subscriber_first_name=subscriber.first_name,
            cards=cards,
            preferences_url=preferences_url,
        )

        try:
            result = send_email(
                to_email=subscriber.email,
                subject=welcome_content.subject,
                body_text=welcome_content.text_body,
                body_html=welcome_content.html_body,
            )

            anchor_reminder_id = _get_welcome_anchor_reminder_id(db, subscriber_id=subscriber.id)

            status_value = "sent" if result.accepted else "failed"
            _append_webhook_event_meta(
                event,
                welcome_status=status_value,
                provider=result.provider,
                provider_message_id=result.message_id,
            )
            if anchor_reminder_id:
                db.add(
                    EmailEvent(
                        scheduled_reminder_id=anchor_reminder_id,
                        provider=result.provider,
                        provider_message_id=result.message_id,
                        event_type=f"welcome_{status_value}",
                        payload_json=json.dumps(
                            {
                                "source": source,
                                "idempotency_key": x_idempotency_key,
                            }
                        ),
                    )
                )
            write_audit(
                db,
                actor_type="system",
                actor_id="webhook",
                action=f"welcome_email.{status_value}",
                entity_type="subscriber",
                entity_id=subscriber.id,
                diff={
                    "provider": result.provider,
                    "provider_message_id": result.message_id,
                    "idempotency_key": x_idempotency_key,
                    "source": source,
                },
            )
        except Exception as exc:
            anchor_reminder_id = _get_welcome_anchor_reminder_id(db, subscriber_id=subscriber.id)
            _append_webhook_event_meta(
                event,
                welcome_status="failed",
                provider="system",
                provider_message_id="",
            )
            if anchor_reminder_id:
                db.add(
                    EmailEvent(
                        scheduled_reminder_id=anchor_reminder_id,
                        provider="system",
                        provider_message_id=None,
                        event_type="welcome_failed",
                        payload_json=json.dumps(
                            {
                                "source": source,
                                "idempotency_key": x_idempotency_key,
                                "error": str(exc),
                            }
                        ),
                    )
                )
            write_audit(
                db,
                actor_type="system",
                actor_id="webhook",
                action="welcome_email.failed",
                entity_type="subscriber",
                entity_id=subscriber.id,
                diff={
                    "provider": "system",
                    "error": str(exc),
                    "idempotency_key": x_idempotency_key,
                    "source": source,
                },
            )

        db.commit()
    finally:
        db.close()

    return {"ok": True, "duplicate": False, "idempotent": False}
