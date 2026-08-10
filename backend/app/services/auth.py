from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import scrypt, sha256
import hmac
import secrets

from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db, use_demo_database
from app.models.auth import AuthThrottle, User, UserSession

REGISTRATION_THROTTLE_KEY = "registration"
REGISTRATION_THROTTLE_LOCK_KEY = int.from_bytes(b"PONGOREG", byteorder="big")
DEMO_SAFE_POST_PATHS = {
    "/api/allocations/preview",
    "/api/fulfillments/preview",
    "/api/items/bulk/preview",
    "/api/picks/preview",
    "/api/receipts/bulk/preview",
    "/api/routes/open-orders/plan",
    "/api/routes/preview",
    "/api/scanner/adjustments/preview",
    "/api/scanner/cycle-count/preview",
    "/api/scanner/receiving/scan/preview",
    "/api/scanner/transfers/preview",
}


def normalize_email(value: str) -> str:
    return value.strip().casefold()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        actual = scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(actual.hex(), expected)
    except (TypeError, ValueError):
        return False


def create_session(db: Session, user: User, settings: Settings) -> tuple[UserSession, str]:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    session = UserSession(
        user_id=user.id,
        token_hash=sha256(token.encode()).hexdigest(),
        expires_at=now + timedelta(hours=settings.auth_session_hours),
    )
    db.add(session)
    return session, token


def user_for_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    now = datetime.now(timezone.utc)
    return db.scalar(
        select(User)
        .join(UserSession)
        .where(
            UserSession.token_hash == sha256(token.encode()).hexdigest(),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
            User.active.is_(True),
        )
    )


def require_authenticated_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User | None:
    if not settings.auth_required:
        return None
    if request.method == "POST" and request.url.path == "/api/integrations/woocommerce/webhooks/orders":
        return None
    user = user_for_token(db, request.cookies.get(settings.auth_cookie_name))
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if user.access_level not in {"staff", "demo"}:
        raise HTTPException(status_code=403, detail="This account has an unsupported access level.")
    request.state.user = user
    if user.access_level == "demo":
        if request.url.path.startswith(("/api/integrations/", "/api/reports/google-sheets")):
            raise HTTPException(status_code=403, detail={"code": "demo_external_access_blocked", "message": "External integrations are unavailable in the isolated demo workspace."})
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not (request.method == "POST" and request.url.path in DEMO_SAFE_POST_PATHS):
            raise HTTPException(status_code=403, detail={"code": "demo_read_only", "message": "This demo account is read-only. You can review mock data and run previews, but cannot save changes."})
        use_demo_database(db)
    return user


def authenticated_actor(
    request: Request,
    user: User | None = Depends(require_authenticated_user),
) -> str:
    user = user or getattr(request.state, "user", None)
    return user.email if user is not None else "system"


def registration_allowed(db: Session, settings: Settings, access_code: str | None) -> bool:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": REGISTRATION_THROTTLE_LOCK_KEY})
    throttle = db.scalar(
        select(AuthThrottle)
        .where(AuthThrottle.throttle_key == REGISTRATION_THROTTLE_KEY)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if throttle is None:
        throttle = AuthThrottle(throttle_key=REGISTRATION_THROTTLE_KEY, failed_attempt_count=0)
        db.add(throttle)
        db.flush()
    now = datetime.now(timezone.utc)
    if throttle.locked_until:
        locked_until = throttle.locked_until if throttle.locked_until.tzinfo else throttle.locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now:
            return False
        throttle.locked_until = None
        throttle.failed_attempt_count = 0
    configured = settings.registration_access_code
    if settings.app_env.casefold() == "production":
        allowed = bool(
            settings.registration_enabled
            and len(configured.encode()) >= 32
            and hmac.compare_digest(configured, access_code or "")
        )
    elif not db.scalar(select(func.count(User.id))):
        allowed = True
    elif not settings.registration_enabled:
        allowed = False
    elif not configured:
        allowed = True
    else:
        allowed = hmac.compare_digest(configured, access_code or "")
    if allowed:
        throttle.failed_attempt_count = 0
        throttle.locked_until = None
        return True
    if settings.registration_enabled and configured:
        throttle.failed_attempt_count += 1
        if throttle.failed_attempt_count >= settings.auth_max_failed_logins:
            throttle.failed_attempt_count = 0
            throttle.locked_until = now + timedelta(minutes=settings.auth_lockout_minutes)
    return False
