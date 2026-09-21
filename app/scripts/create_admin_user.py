from __future__ import annotations

import argparse
import getpass
import sys

from app.db import SessionLocal
from app.models import AdminUser
from app.security import hash_password


VALID_ROLES = {"owner", "admin"}


def _validate_password(password: str) -> None:
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")


def create_admin_user(
    *,
    email: str,
    full_name: str | None,
    role: str,
    password: str,
) -> AdminUser:
    normalized_email = email.strip().lower()
    normalized_role = role.strip().lower()

    if normalized_role not in VALID_ROLES:
        raise ValueError("Role must be one of: owner, admin")

    _validate_password(password)

    db = SessionLocal()
    try:
        existing = db.query(AdminUser).filter(AdminUser.email == normalized_email).first()
        if existing:
            raise ValueError("Email is already used by another admin user")

        user = AdminUser(
            email=normalized_email,
            full_name=(full_name or "").strip() or None,
            role=normalized_role,
            status="active",
            is_active=True,
            password_hash=hash_password(password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create an admin user account")
    parser.add_argument("--email", required=True, help="Admin email")
    parser.add_argument("--name", default="", help="Admin full name")
    parser.add_argument("--role", default="admin", choices=sorted(VALID_ROLES), help="Admin role")
    parser.add_argument(
        "--password",
        default=None,
        help="Admin password (discouraged for interactive use; prefer prompt)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    password = args.password
    if password is None:
        first = getpass.getpass("Password (min 12 chars): ")
        second = getpass.getpass("Confirm password: ")
        if first != second:
            print("Error: Passwords do not match", file=sys.stderr)
            return 1
        password = first

    try:
        user = create_admin_user(
            email=args.email,
            full_name=args.name,
            role=args.role,
            password=password,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(
        "Created admin user "
        f"{user.email} (id={user.id}, role={user.role}, status={user.status})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
