from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Subscriber
from app.schemas import PreferencesContextOut, PreferencesUpdateRequest
from app.services.preferences import (
    get_preference_context_from_token,
    mask_email,
    set_card_email_enabled,
    set_subscriber_email_enabled,
)
from app.services.scheduler import rebuild_schedule_for_subscriber


router = APIRouter(prefix="/v1/preferences", tags=["preferences"])


def _get_subscriber_from_token(db: Session, token: str) -> tuple[Subscriber, str | None]:
    try:
        return get_preference_context_from_token(db, token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def _build_public_context(subscriber: Subscriber, focused_card_id: str | None) -> PreferencesContextOut:
    language = (subscriber.language or "en").lower()
    if language not in {"fr", "en"}:
        language = "en"

    card_ids = {card.id for card in subscriber.cards}
    focused_card = focused_card_id if focused_card_id in card_ids else None

    cards_sorted = sorted(
        subscriber.cards,
        key=lambda card: (
            0 if focused_card and card.id == focused_card else 1,
            card.card_name.lower(),
        ),
    )

    return PreferencesContextOut(
        subscriber_email_masked=mask_email(subscriber.email),
        language=language,
        subscriber_status=subscriber.status,
        global_email_enabled=subscriber.email_enabled,
        focused_card_id=focused_card,
        cards=[
            {
                "id": card.id,
                "card_name": card.card_name,
                "card_type": card.card_type,
                "statement_day": card.statement_day,
                "is_active": card.is_active,
                "email_enabled": card.email_enabled,
            }
            for card in cards_sorted
        ],
    )


@router.get("/context", response_model=PreferencesContextOut)
def get_preferences_context(token: str = Query(default="")):
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing token")

    db = SessionLocal()
    try:
        subscriber, focused_card_id = _get_subscriber_from_token(db, token)
        return _build_public_context(subscriber, focused_card_id)
    finally:
        db.close()


@router.patch("/context", response_model=PreferencesContextOut)
def patch_preferences_context(payload: PreferencesUpdateRequest, token: str = Query(default="")):
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing token")

    db = SessionLocal()
    try:
        subscriber, focused_card_id = _get_subscriber_from_token(db, token)

        if payload.global_email_enabled is not None:
            set_subscriber_email_enabled(db, subscriber=subscriber, email_enabled=payload.global_email_enabled)

        for update in payload.card_email_updates:
            try:
                set_card_email_enabled(
                    db,
                    subscriber_id=subscriber.id,
                    card_id=update.card_id,
                    email_enabled=update.email_enabled,
                )
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        db.flush()
        rebuild_schedule_for_subscriber(db, subscriber.id)
        db.commit()
        db.refresh(subscriber)

        refreshed_subscriber, resolved_focused_card_id = _get_subscriber_from_token(db, token)
        if focused_card_id and not resolved_focused_card_id:
            resolved_focused_card_id = focused_card_id
        return _build_public_context(refreshed_subscriber, resolved_focused_card_id)
    finally:
        db.close()


@router.get("/{token}", response_model=PreferencesContextOut)
def get_preferences_legacy(token: str):
    db = SessionLocal()
    try:
        subscriber, focused_card_id = _get_subscriber_from_token(db, token)
        return _build_public_context(subscriber, focused_card_id)
    finally:
        db.close()


@router.patch("/{token}", response_model=PreferencesContextOut)
def patch_preferences_legacy(token: str, payload: PreferencesUpdateRequest):
    db = SessionLocal()
    try:
        subscriber, focused_card_id = _get_subscriber_from_token(db, token)
        if payload.global_email_enabled is not None:
            set_subscriber_email_enabled(db, subscriber=subscriber, email_enabled=payload.global_email_enabled)

        for update in payload.card_email_updates:
            try:
                set_card_email_enabled(
                    db,
                    subscriber_id=subscriber.id,
                    card_id=update.card_id,
                    email_enabled=update.email_enabled,
                )
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        db.flush()
        rebuild_schedule_for_subscriber(db, subscriber.id)
        db.commit()

        refreshed_subscriber, resolved_focused_card_id = _get_subscriber_from_token(db, token)
        if focused_card_id and not resolved_focused_card_id:
            resolved_focused_card_id = focused_card_id
        return _build_public_context(refreshed_subscriber, resolved_focused_card_id)
    finally:
        db.close()
