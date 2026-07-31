from datetime import datetime, timedelta, timezone
from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.auth import User, UserSession
from app.schemas.auth import AuthResponse, AuthUserRead, LoginRequest, RegisterRequest
from app.services.auth import create_session, hash_password, normalize_email, registration_allowed, user_for_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        settings.auth_cookie_name,
        token,
        max_age=settings.auth_session_hours * 3600,
        httponly=True,
        secure=settings.app_env.casefold() == "production",
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> AuthResponse:
    email = normalize_email(str(payload.email))
    if not registration_allowed(db, settings, payload.registration_access_code):
        db.commit()
        raise HTTPException(status_code=403, detail="Registration is closed or the access code is invalid.")
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(email=email, display_name=payload.display_name.strip(), password_hash=hash_password(payload.password))
    db.add(user)
    db.flush()
    _, token = create_session(db, user, settings)
    db.commit()
    set_session_cookie(response, settings, token)
    return AuthResponse(authenticated=True, user=AuthUserRead.model_validate(user))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> AuthResponse:
    user = db.scalar(
        select(User)
        .where(User.email == normalize_email(str(payload.email)))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = datetime.now(timezone.utc)
    if user and user.locked_until:
        locked_until = user.locked_until if user.locked_until.tzinfo else user.locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now:
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")
    if user is None or not user.active or not verify_password(payload.password, user.password_hash):
        if user is not None:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.auth_max_failed_logins:
                user.locked_until = now + timedelta(minutes=settings.auth_lockout_minutes)
                user.failed_login_count = 0
            db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    _, token = create_session(db, user, settings)
    db.commit()
    set_session_cookie(response, settings, token)
    return AuthResponse(authenticated=True, user=AuthUserRead.model_validate(user))


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> Response:
    token = request.cookies.get(settings.auth_cookie_name)
    if token:
        session = db.scalar(select(UserSession).where(UserSession.token_hash == sha256(token.encode()).hexdigest(), UserSession.revoked_at.is_(None)))
        if session:
            session.revoked_at = datetime.now(timezone.utc)
            db.commit()
    response.delete_cookie(settings.auth_cookie_name, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=AuthResponse)
def me(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> AuthResponse:
    if not settings.auth_required:
        return AuthResponse(authenticated=False, auth_required=False)
    user = user_for_token(db, request.cookies.get(settings.auth_cookie_name))
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return AuthResponse(authenticated=True, user=AuthUserRead.model_validate(user))
