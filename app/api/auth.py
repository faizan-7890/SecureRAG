import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import Settings, get_settings
from app.core.security import UserStore, authenticate, create_access_token
from app.models.schemas import LoginRequest, RegisterRequest, TokenResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, settings: Settings = Depends(get_settings)):
    if not settings.auth_secret:
        raise HTTPException(503, "Authentication is not configured.")
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
