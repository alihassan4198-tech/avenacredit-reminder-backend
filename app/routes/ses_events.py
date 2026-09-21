import hmac
import json
import urllib.request
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.config import settings
from app.db import SessionLocal
from app.models import EmailEvent, Subscriber
from app.services.audit import write_audit


router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])

# SES event type -> email_events.event_type
EVENT_TYPES = {"Bounce": "bounced", "Complaint": "complained", "Delivery": "delivered"}


def _check_token(token: str | None) -> None:
    expected = (settings.ses_events_token or "").strip()
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="SES events are not configured")
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _check_topic(topic_arn: str | None) -> None:
    expected = (settings.ses_events_topic_arn or "").strip()
    if expected and topic_arn != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unexpected topic")


def _confirm_subscription(subscribe_url: str) -> None:
    parsed = urlparse(subscribe_url)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not (host.startswith("sns.") and host.endswith(".amazonaws.com")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid SubscribeURL")
    with urllib.request.urlopen(subscribe_url, timeout=10) as response:
        response.read()


def _affected_recipients(ses_event: dict, event_type: str) -> list[str]:
    if event_type == "Bounce":
        bounce = ses_event.get("bounce") or {}
        if bounce.get("bounceType") != "Permanent":
            return []
        recipients = bounce.get("bouncedRecipients") or []
    elif event_type == "Complaint":
        recipients = (ses_event.get("complaint") or {}).get("complainedRecipients") or []
    else:
        return []
    return [str(r.get("emailAddress", "")).strip().lower() for r in recipients if r.get("emailAddress")]


def _record_ses_event(ses_event: dict) -> dict[str, int | str]:
    # Configuration-set events use "eventType"; identity notifications use "notificationType".
    event_type = ses_event.get("eventType") or ses_event.get("notificationType") or ""
    mapped_type = EVENT_TYPES.get(event_type)
    if not mapped_type:
        return {"ignored": event_type or "unknown"}

    message_id = str((ses_event.get("mail") or {}).get("messageId") or "")
    db = SessionLocal()
    try:
        recorded = 0
        sent_event = (
            db.query(EmailEvent)
            .filter(EmailEvent.provider_message_id == message_id)
            .order_by(EmailEvent.created_at.asc())
            .first()
            if message_id
            else None
        )
        if sent_event:
            db.add(
                EmailEvent(
                    scheduled_reminder_id=sent_event.scheduled_reminder_id,
                    provider="ses",
                    provider_message_id=message_id,
                    event_type=mapped_type,
                    payload_json=json.dumps(ses_event)[:20000],
                )
            )
            recorded = 1

        # Stop emailing addresses that hard-bounced or complained, so the SES account stays in good standing.
        disabled = 0
        for email in _affected_recipients(ses_event, event_type):
            subscriber = db.query(Subscriber).filter(Subscriber.email == email).first()
            if not subscriber or not subscriber.email_enabled:
                continue
            subscriber.email_enabled = False
            write_audit(
                db,
                actor_type="system",
                actor_id="ses",
                action=f"ses.{mapped_type}.email_disabled",
                entity_type="subscriber",
                entity_id=subscriber.id,
                diff={"email_enabled": [True, False], "message_id": message_id},
            )
            disabled += 1

        db.commit()
        return {"event": mapped_type, "recorded": recorded, "email_disabled": disabled}
    finally:
        db.close()


@router.post("/ses-events")
async def ses_events(request: Request, token: str | None = Query(default=None)):
    _check_token(token)

    try:
        envelope = json.loads((await request.body()).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body") from exc

    _check_topic(envelope.get("TopicArn"))
    message_type = request.headers.get("x-amz-sns-message-type") or envelope.get("Type")

    if message_type == "SubscriptionConfirmation":
        _confirm_subscription(str(envelope.get("SubscribeURL") or ""))
        return {"ok": True, "confirmed": True}

    if message_type != "Notification":
        return {"ok": True, "ignored": message_type}

    try:
        ses_event = json.loads(envelope.get("Message") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid SES message") from exc

    return {"ok": True, **_record_ses_event(ses_event)}
