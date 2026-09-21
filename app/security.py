from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.config import settings


password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, plain_password)
    except VerifyMismatchError:
        return False


def create_access_token(subject: str) -> str:
    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    expire_at = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": subject,
        "admin_user_id": subject,
        "exp": expire_at,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_admin_access_token(*, admin_user_id: str, email: str, role: str) -> str:
    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    expire_at = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": admin_user_id,
        "admin_user_id": admin_user_id,
        "email": email,
        "role": role,
        "exp": expire_at,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token_payload(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if not isinstance(payload, dict):
            raise ValueError("Invalid token")
        return payload
    except JWTError as exc:
        raise ValueError("Invalid token") from exc


def decode_access_token(token: str) -> str:
    payload = decode_access_token_payload(token)
    subject = payload.get("admin_user_id") or payload.get("sub")
    if not subject:
        raise ValueError("Token missing subject")
    return str(subject)


def create_preferences_token(subscriber_id: str) -> str:
    expires_delta = timedelta(days=settings.preferences_token_expire_days)
    expire_at = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": subscriber_id, "scope": "preferences", "exp": expire_at}
    return jwt.encode(payload, settings.preferences_token_secret, algorithm=settings.jwt_algorithm)


def decode_preferences_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.preferences_token_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("scope") != "preferences":
            raise ValueError("Invalid token scope")
        subject = payload.get("sub")
        if not subject:
            raise ValueError("Token missing subject")
        return subject
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
