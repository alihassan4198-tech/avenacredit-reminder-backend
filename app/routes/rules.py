from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_current_admin, get_db
from app.models import AdminUser, ReminderRuleGlobal
from app.schemas import ReminderRuleOut, ReminderRulePatch
from app.services.audit import write_audit
from app.services.scheduler import rebuild_schedule_for_all_subscribers


router = APIRouter(prefix="/v1/admin", tags=["rules"])


def get_or_create_rules(db: Session) -> ReminderRuleGlobal:
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
    db.commit()
    db.refresh(rules)
    return rules


@router.get("/reminder-rules", response_model=ReminderRuleOut)
def get_rules(_: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    return get_or_create_rules(db)


@router.patch("/reminder-rules", response_model=ReminderRuleOut)
def patch_rules(
    payload: ReminderRulePatch,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    rules = get_or_create_rules(db)

    if payload.j20_enabled is not None:
        rules.j20_enabled = payload.j20_enabled
    if payload.j20_offset_days is not None:
        rules.j20_offset_days = payload.j20_offset_days
    if payload.j5_enabled is not None:
        rules.j5_enabled = payload.j5_enabled
    if payload.j5_offset_days is not None:
        rules.j5_offset_days = payload.j5_offset_days
    if payload.timezone is not None:
        rules.timezone = payload.timezone

    rebuild_schedule_for_all_subscribers(db)
    write_audit(
        db,
        actor_type="admin",
        actor_id=current_admin.id,
        action="rules.update",
        entity_type="reminder_rules_global",
        entity_id=rules.id,
        diff=payload.model_dump(exclude_none=True),
    )

    db.commit()
    db.refresh(rules)
    return rules
