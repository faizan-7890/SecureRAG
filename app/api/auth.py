import logging

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import Settings, get_settings
from app.core.security import UserStore, authenticate, create_access_token, require_current_user
from app.models.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UpdateRoleRequest,
    UserListResponse,
    UserProfile,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, settings: Settings = Depends(get_settings)):
    if not settings.auth_secret:
        raise HTTPException(503, "Authentication is not configured.")
    if settings.auth_bootstrap_admin and request.username.strip().lower() == settings.auth_bootstrap_admin.strip().lower():
        logger.warning("Registration rejected: reserved bootstrap admin username %s", request.username, extra={"username": request.username})
        raise HTTPException(400, "This username is reserved for system administration.")
    if UserStore.get(request.username):
        logger.warning("Registration rejected: duplicate username %s", request.username, extra={"username": request.username})
        raise HTTPException(409, "Username is already registered.")
    UserStore.add(request.username, request.password)
    logger.info("User registered: %s", request.username, extra={"username": request.username})
    return TokenResponse(access_token=create_access_token(UserStore.get(request.username), settings))


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, settings: Settings = Depends(get_settings)):
    user = authenticate(request.username, request.password, settings)
    if not user:
        logger.warning("Login failed for username %s", request.username, extra={"username": request.username})
        raise HTTPException(401, "Invalid username or password.")
    logger.info("User logged in: %s", request.username, extra={"username": request.username})
    return TokenResponse(access_token=create_access_token(user, settings))


@router.get("/me", response_model=UserProfile)
def get_me(user: Annotated[dict[str, str] | None, Depends(require_current_user)]):
    if not user:
        raise HTTPException(401, "Authentication required.")
    return UserProfile(username=user["username"], role=user.get("role", "user"))


@router.get("/users", response_model=UserListResponse)
def list_users(
    user: Annotated[dict[str, str] | None, Depends(require_current_user)],
    settings: Settings = Depends(get_settings),
):
    if not user or user.get("role") != "admin":
        raise HTTPException(403, "Admin privileges required.")
    if settings.auth_bootstrap_admin and not UserStore.get(settings.auth_bootstrap_admin) and settings.auth_bootstrap_password:
        UserStore.add(settings.auth_bootstrap_admin, settings.auth_bootstrap_password, "admin")
    users = [UserProfile(username=u["username"], role=u.get("role", "user")) for u in UserStore.all()]
    return UserListResponse(users=users, total=len(users))


@router.patch("/users/{username}/role", response_model=UserProfile)
def update_user_role(
    username: str,
    body: UpdateRoleRequest,
    user: Annotated[dict[str, str] | None, Depends(require_current_user)],
):
    if not user or user.get("role") != "admin":
        raise HTTPException(403, "Admin privileges required.")
    target_user = UserStore.get(username)
    if not target_user:
        raise HTTPException(404, f"User '{username}' not found.")
    UserStore.update_role(username, body.role)
    updated = UserStore.get(username)
    logger.info("User %s role changed to %s by %s", username, body.role, user.get("username"))
    return UserProfile(username=updated["username"], role=updated["role"])
