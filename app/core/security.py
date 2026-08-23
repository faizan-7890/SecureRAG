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
        hashed = _hash_password(password)
        cls.users[username] = {
            "username": username,
            "password": hashed,
            "role": role,
        }
        try:
            from sqlalchemy import select
            from app.core.db import db_session
            from app.models.db_models import UserDB

            with db_session() as session:
                existing = session.scalar(select(UserDB).where(UserDB.username == username))
                if existing:
                    existing.hashed_password = hashed
                    existing.role = role
                else:
                    user_db = UserDB(username=username, hashed_password=hashed, role=role)
                    session.add(user_db)
        except Exception:
            # Fallback for environments before db init
            pass

    @classmethod
    def get(cls, username: str | None) -> dict[str, str] | None:
        if not username:
            return None
        if username in cls.users:
            return cls.users[username]

        try:
            from sqlalchemy import select
            from app.core.db import db_session
            from app.models.db_models import UserDB

            with db_session() as session:
                user_db = session.scalar(select(UserDB).where(UserDB.username == username))
                if user_db:
                    user_dict = {
                        "username": user_db.username,
                        "password": user_db.hashed_password,
                        "role": user_db.role,
                    }
                    cls.users[username] = user_dict
                    return user_dict
        except Exception:
            pass

        return None

    @classmethod
    def all(cls) -> list[dict[str, str]]:
        try:
            from sqlalchemy import select
            from app.core.db import db_session
            from app.models.db_models import UserDB

            with db_session() as session:
                users_db = session.scalars(select(UserDB)).all()
                if users_db:
                    result: list[dict[str, str]] = []
                    for u in users_db:
                        ud = {"username": u.username, "password": u.hashed_password, "role": u.role}
                        cls.users[u.username] = ud
                        result.append(ud)
                    return result
        except Exception:
            pass

        return list(cls.users.values())

    @classmethod
    def update_role(cls, username: str, role: str) -> bool:
        cls.users.setdefault(username, {})
        if username in cls.users and "username" in cls.users[username]:
            cls.users[username]["role"] = role

        try:
            from sqlalchemy import select
            from app.core.db import db_session
            from app.models.db_models import UserDB

            with db_session() as session:
                user_db = session.scalar(select(UserDB).where(UserDB.username == username))
                if user_db:
                    user_db.role = role
                    if username in cls.users:
                        cls.users[username]["role"] = role
                    return True
        except Exception:
            pass

        return username in cls.users and "username" in cls.users[username]


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


def require_current_user(
    user: Annotated[dict[str, str] | None, Depends(current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str] | None:
    """Enforce authentication when AUTH_SECRET is configured.

    If auth is not configured (AUTH_SECRET=None), returns None (allows unauthenticated access).
    If auth is configured and the caller is unauthenticated, raises HTTP 401.
    """
    if settings.auth_secret and user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

