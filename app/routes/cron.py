import hmac
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_db
from app.services.scheduler import process_due_reminders


router = APIRouter(prefix="/v1/cron", tags=["cron"])


# Called by Vercel Cron (see vercel.json). Vercel sends "Authorization: Bearer <CRON_SECRET>".
# On AWS the same work is done by reminder_job.handler via EventBridge instead.
@router.get("/run-due")
def cron_run_due(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    expected = (settings.cron_secret or "").strip()
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Cron is not configured")
    if not authorization or not hmac.compare_digest(authorization, f"Bearer {expected}"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    return process_due_reminders(db, batch_size=500, worker_id=f"cron-{uuid.uuid4().hex[:12]}")
