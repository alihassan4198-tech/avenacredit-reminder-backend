import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import CreditCard, NotificationPreference, PreferenceAccessToken, Subscriber
from app.security import decode_preferences_token


def upsert_preference(
    db: Session,
    *,
    subscriber_id: str,
    scope: str,
    reminder_type: str,
    enabled: bool,
    updated_by: str,
    card_id: str | None = None,
) -> NotificationPreference:
    pref = (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.subscriber_id == subscriber_id,
            NotificationPreference.scope == scope,
            NotificationPreference.reminder_type == reminder_type,
            NotificationPreference.card_id == card_id,
        )
        .first()
    )

    if pref:
        pref.enabled = enabled
        pref.updated_by = updated_by
        return pref

    pref = NotificationPreference(
        subscriber_id=subscriber_id,
        scope=scope,
        reminder_type=reminder_type,
        enabled=enabled,
        updated_by=updated_by,
        card_id=card_id,
    )
    db.add(pref)
    return pref


def is_reminder_enabled(db: Session, *, subscriber_id: str, card_id: str, reminder_type: str) -> bool:
    prefs = (
        db.query(NotificationPreference)
        .filter(NotificationPreference.subscriber_id == subscriber_id)
        .all()
    )

    global_all = None
    global_type = None
    card_all = None
    card_type = None

    for pref in prefs:
        if pref.scope == "global" and pref.reminder_type == "all":
            global_all = pref.enabled
        elif pref.scope == "global" and pref.reminder_type == reminder_type:
            global_type = pref.enabled
        elif pref.scope == "card" and pref.card_id == card_id and pref.reminder_type == "all":
            card_all = pref.enabled
        elif pref.scope == "card" and pref.card_id == card_id and pref.reminder_type == reminder_type:
            card_type = pref.enabled

    if global_all is False:
        return False
    if global_type is False:
        return False

    if card_all is not None:
        return card_all
    if card_type is not None:
        return card_type

    return True


def mask_email(email: str) -> str:
    if "@" not in email:
        return "***"

    local, domain = email.split("@", 1)
    if len(local) <= 2:
        local_masked = local[0] + "*"
    else:
        local_masked = local[0] + ("*" * (len(local) - 2)) + local[-1]

    return f"{local_masked}@{domain}"


def hash_preference_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_preference_access_token(
    db: Session,
    *,
    subscriber_id: str,
    focused_card_id: str | None = None,
) -> str:
    lifetime_days = settings.preferences_token_expire_days if settings.preferences_token_expire_days > 0 else 90
    expires_at = datetime.utcnow() + timedelta(days=lifetime_days)
    opaque_token = secrets.token_urlsafe(32)

    db.add(
        PreferenceAccessToken(
            token_hash=hash_preference_token(opaque_token),
            subscriber_id=subscriber_id,
            focused_card_id=focused_card_id,
            expires_at=expires_at,
            revoked_at=None,
        )
    )
    db.flush()
    return opaque_token


def revoke_preference_access_token(db: Session, *, token: str) -> bool:
    token_row = db.query(PreferenceAccessToken).filter(PreferenceAccessToken.token_hash == hash_preference_token(token)).first()
    if not token_row:
        return False
    token_row.revoked_at = datetime.utcnow()
    return True


def get_preference_context_from_token(db: Session, token: str) -> tuple[Subscriber, str | None]:
    if not token:
        raise ValueError("Missing token")

    token_row = db.query(PreferenceAccessToken).filter(PreferenceAccessToken.token_hash == hash_preference_token(token)).first()
    if token_row:
        if token_row.revoked_at is not None:
            raise ValueError("Token revoked")
        if token_row.expires_at < datetime.utcnow():
            raise ValueError("Token expired")

        subscriber = (
            db.query(Subscriber)
            .options(joinedload(Subscriber.cards))
            .filter(Subscriber.id == token_row.subscriber_id)
            .first()
        )
        if not subscriber:
            raise ValueError("Subscriber not found")

        return subscriber, token_row.focused_card_id

    # Backward-compatibility path: accept legacy JWT preference tokens.
    try:
        subscriber_id = decode_preferences_token(token)
    except ValueError as exc:
        raise ValueError("Invalid token") from exc

    subscriber = (
        db.query(Subscriber)
        .options(joinedload(Subscriber.cards))
        .filter(Subscriber.id == subscriber_id)
        .first()
    )
    if not subscriber:
        raise ValueError("Subscriber not found")

    return subscriber, None


def set_subscriber_email_enabled(db: Session, *, subscriber: Subscriber, email_enabled: bool) -> None:
    subscriber.email_enabled = email_enabled


def set_card_email_enabled(
    db: Session,
    *,
    subscriber_id: str,
    card_id: str,
    email_enabled: bool,
) -> CreditCard:
    card = (
        db.query(CreditCard)
        .filter(CreditCard.id == card_id, CreditCard.subscriber_id == subscriber_id)
        .first()
    )
    if not card:
        raise ValueError("Card not found")

    card.email_enabled = email_enabled
    return card
