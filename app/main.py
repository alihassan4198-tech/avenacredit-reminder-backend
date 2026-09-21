from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, engine
from app.models import AdminUser, Base, ReminderRuleGlobal
from app.routes.auth import router as auth_router
from app.routes.events import router as events_router
from app.routes.preferences import router as preferences_router
from app.routes.rules import router as rules_router
from app.routes.ses_events import router as ses_events_router
from app.routes.subscribers import router as subscribers_router
from app.routes.webhooks import router as webhooks_router
from app.security import hash_password


app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


def _ensure_bootstrap_owner(db: Session) -> None:
    admin_count = db.query(AdminUser.id).count()
    if admin_count > 0:
        return

    bootstrap_email = (settings.admin_bootstrap_email or "").strip()
    bootstrap_password = settings.admin_bootstrap_password or ""
    if not bootstrap_email and not bootstrap_password:
        print("startup: no admin users yet; set ADMIN_EMAIL/ADMIN_PASSWORD once or run app.scripts.create_admin_user", flush=True)
        return
    if len(bootstrap_password) < 12:
        raise ValueError("ADMIN_PASSWORD must be at least 12 characters when bootstrapping owner account")

    db.add(
        AdminUser(
            email=bootstrap_email.lower(),
            password_hash=hash_password(bootstrap_password),
            full_name=None,
            role="owner",
            status="active",
            is_active=True,
        )
    )


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        _ensure_bootstrap_owner(db)

        rules = db.query(ReminderRuleGlobal).first()
        if not rules:
            db.add(
                ReminderRuleGlobal(
                    j20_enabled=False,
                    j20_offset_days=20,
                    j5_enabled=True,
                    j5_offset_days=5,
                    timezone=settings.default_timezone,
                )
            )

        db.commit()
    finally:
        db.close()


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> JSONResponse:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "error"},
        )

    return JSONResponse(
        status_code=200,
        content={"status": "ok", "database": "ok"},
    )


@app.get("/")
def root() -> dict[str, str]:
    # The admin and unsubscribe pages are served by the avenacredit-reminder-form app on Vercel.
    return {"service": settings.app_name, "status": "ok"}


app.include_router(auth_router)
app.include_router(subscribers_router)
app.include_router(rules_router)
app.include_router(events_router)
app.include_router(webhooks_router)
app.include_router(preferences_router)
app.include_router(ses_events_router)
