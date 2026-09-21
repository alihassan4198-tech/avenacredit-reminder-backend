from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import get_current_admin, get_db
from app.models import AdminUser
from app.schemas import AdminUserOut, LoginRequest, TokenResponse
from app.security import create_admin_access_token, verify_password


router = APIRouter(prefix="/v1/admin/auth", tags=["admin-auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    invalid_credentials = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user = db.query(AdminUser).filter(AdminUser.email == payload.email.lower()).first()
    if not user:
        raise invalid_credentials

    if user.status != "active" or not user.is_active:
        raise invalid_credentials

    if not verify_password(payload.password, user.password_hash):
        raise invalid_credentials

    user.last_login_at = datetime.utcnow()
    db.add(user)
    db.commit()

    token = create_admin_access_token(
        admin_user_id=user.id,
        email=user.email,
        role=user.role,
    )
    return TokenResponse(access_token=token)


@router.post("/logout")
def logout(_: AdminUser = Depends(get_current_admin)):
    return {"ok": True}


@router.get("/me", response_model=AdminUserOut)
def me(current_admin: AdminUser = Depends(get_current_admin)):
    return current_admin
