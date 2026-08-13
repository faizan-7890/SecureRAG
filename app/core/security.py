from __future__ import annotations
from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.core.config import Settings, get_settings


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def _hash_password(password: str) -> str:
    """Hash a password using bcrypt, truncating to 72 bytes as per spec."""
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("utf-8"))


class UserStore:
    users: dict[str, dict[str, str]] = {}

    @classmethod
    def add(cls, username: str, password: str, role: str = "user") -> None:
        cls.users[username] = {
            "username": username,
            "password": _hash_password(password),
            "role": role,
        }

    @classmethod
    def get(cls, username: str | None) -> dict[str, str] | None:
        return cls.users.get(username) if username else None


def authenticate(username: str, password: str, settings: Settings):
    if (
        settings.auth_bootstrap_admin
        and settings.auth_bootstrap_password
        and not UserStore.get(settings.auth_bootstrap_admin)
    ):
        UserStore.add(settings.auth_bootstrap_admin, settings.auth_bootstrap_password, "admin")
    user = UserStore.get(username)
    return user if user and _verify_password(password, user["password"]) else None


def create_access_token(user: dict[str, str], settings: Settings) -> str:
    if not settings.auth_secret:
        raise RuntimeError("AUTH_SECRET is not configured.")
    exp = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": user["username"], "role": user["role"], "exp": exp},
        settings.auth_secret,
        algorithm="HS256",
    )


def current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str] | None:
    if not settings.auth_secret:
        return None
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.auth_secret, algorithms=["HS256"])
        user = UserStore.get(payload.get("sub"))
    except JWTError as error:
        raise HTTPException(401, "Invalid or expired token.", headers={"WWW-Authenticate": "Bearer"}) from error
    if not user:
        raise HTTPException(401, "User not found.")
    return user
