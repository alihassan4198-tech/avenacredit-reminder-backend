from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import AdminUser
from app.security import decode_access_token_payload


bearer_scheme = HTTPBearer(auto_error=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AdminUser:
    token = credentials.credentials
    try:
        payload = decode_access_token_payload(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    admin_id = payload.get("admin_user_id") or payload.get("sub")
    if not admin_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    admin = (
        db.query(AdminUser)
        .filter(
            and_(
                AdminUser.id == str(admin_id),
                AdminUser.status == "active",
                AdminUser.is_active.is_(True),
            )
        )
        .first()
    )
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found")

    return admin
