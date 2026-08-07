import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.fernet import InvalidToken
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.reporting import GoogleReportsConfiguration
from app.services.woocommerce_configuration import credential_cipher

GOOGLE_OAUTH_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REPORT_SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
)
GOOGLE_OAUTH_STATE_TTL_SECONDS = 600


def effective_google_reports_settings(db: Session | None, settings: Settings) -> Settings:
    if db is None or not hasattr(settings, "model_copy"):
        return settings
    row = db.get(GoogleReportsConfiguration, 1)
    if row is None:
        return settings
    cipher = credential_cipher(settings)
    try:
        values = {
            "google_reports_client_id": cipher.decrypt(row.client_id_ciphertext.encode()).decode(),
            "google_reports_client_secret": cipher.decrypt(row.client_secret_ciphertext.encode()).decode(),
            "google_reports_refresh_token": cipher.decrypt(row.refresh_token_ciphertext.encode()).decode(),
            "google_reports_folder_id": row.folder_id,
        }
    except InvalidToken as error:
        raise ValueError("Stored Google Sheets credentials cannot be decrypted with the configured backend encryption key.") from error
    return settings.model_copy(update=values)


def google_reports_configuration_status(db: Session | None, settings: Settings) -> dict[str, Any]:
    row = db.get(GoogleReportsConfiguration, 1) if db is not None else None
    current = effective_google_reports_settings(db, settings)
    configured = bool(
        current.google_reports_client_id
        and current.google_reports_client_secret
        and current.google_reports_refresh_token
    )
    return {
        "configured": configured,
        "client_id_present": bool(current.google_reports_client_id),
        "client_secret_present": bool(current.google_reports_client_secret),
        "refresh_token_present": bool(current.google_reports_refresh_token),
        "folder_id": current.google_reports_folder_id,
        "folder_configured": bool(current.google_reports_folder_id),
        "configuration_source": "pongo_database" if row else ("deployment_environment" if configured else "not_configured"),
        "configuration_updated_by": row.updated_by if row else None,
        "configuration_updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


def save_google_reports_configuration(
    db: Session,
    settings: Settings,
    *,
    client_id: str | None,
    client_secret: str | None,
    refresh_token: str | None,
    folder_id: str | None,
    changed_by: str,
    verifier: Callable[[Settings], str],
) -> dict[str, Any]:
    current = effective_google_reports_settings(db, settings)
    values = {
        "google_reports_client_id": (client_id or "").strip() or current.google_reports_client_id,
        "google_reports_client_secret": (client_secret or "").strip() or current.google_reports_client_secret,
        "google_reports_refresh_token": (refresh_token or "").strip() or current.google_reports_refresh_token,
        "google_reports_folder_id": (folder_id or "").strip(),
    }
    if not all(values[key] for key in ("google_reports_client_id", "google_reports_client_secret", "google_reports_refresh_token")):
        raise ValueError("Enter the Google OAuth client ID, client secret, and refresh token.")

    candidate = current.model_copy(update=values)
    verifier(candidate)

    return _persist_google_reports_configuration(db, settings, values=values, changed_by=changed_by)


def save_google_reports_oauth_client(
    db: Session,
    settings: Settings,
    *,
    client_id: str | None,
    client_secret: str | None,
    folder_id: str | None,
    changed_by: str,
) -> dict[str, Any]:
    current = effective_google_reports_settings(db, settings)
    values = {
        "google_reports_client_id": (client_id or "").strip() or current.google_reports_client_id,
        "google_reports_client_secret": (client_secret or "").strip() or current.google_reports_client_secret,
        "google_reports_refresh_token": current.google_reports_refresh_token,
        "google_reports_folder_id": (folder_id or "").strip(),
    }
    if not all(values[key] for key in ("google_reports_client_id", "google_reports_client_secret")):
        raise ValueError("Enter the Google OAuth client ID and client secret.")
    return _persist_google_reports_configuration(db, settings, values=values, changed_by=changed_by)


def save_google_reports_refresh_token(
    db: Session,
    settings: Settings,
    *,
    refresh_token: str,
    changed_by: str,
) -> dict[str, Any]:
    current = effective_google_reports_settings(db, settings)
    values = {
        "google_reports_client_id": current.google_reports_client_id,
        "google_reports_client_secret": current.google_reports_client_secret,
        "google_reports_refresh_token": refresh_token.strip(),
        "google_reports_folder_id": current.google_reports_folder_id,
    }
    if not all(values[key] for key in ("google_reports_client_id", "google_reports_client_secret", "google_reports_refresh_token")):
        raise ValueError("Google did not return the credentials needed for ongoing report access.")
    return _persist_google_reports_configuration(db, settings, values=values, changed_by=changed_by)


def _persist_google_reports_configuration(
    db: Session,
    settings: Settings,
    *,
    values: dict[str, str],
    changed_by: str,
) -> dict[str, Any]:
    cipher = credential_cipher(settings, create_for_local=True)
    row = db.get(GoogleReportsConfiguration, 1)
    if row is None:
        row = GoogleReportsConfiguration(id=1)
        db.add(row)
    row.client_id_ciphertext = cipher.encrypt(values["google_reports_client_id"].encode()).decode()
    row.client_secret_ciphertext = cipher.encrypt(values["google_reports_client_secret"].encode()).decode()
    row.refresh_token_ciphertext = cipher.encrypt(values["google_reports_refresh_token"].encode()).decode()
    row.folder_id = values["google_reports_folder_id"]
    row.updated_by = changed_by[:120]
    db.commit()
    db.refresh(row)
    return google_reports_configuration_status(db, settings)


def google_oauth_authorization_url(settings: Settings, *, actor: str, redirect_uri: str) -> str:
    if not settings.google_reports_client_id or not settings.google_reports_client_secret:
        raise ValueError("Enter the Google OAuth client ID and client secret.")
    state = credential_cipher(settings).encrypt(
        json.dumps({"actor": actor, "redirect_uri": redirect_uri}, separators=(",", ":")).encode()
    ).decode()
    return f"{GOOGLE_OAUTH_AUTHORIZATION_URL}?{urlencode({
        'client_id': settings.google_reports_client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': ' '.join(GOOGLE_REPORT_SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',
        'include_granted_scopes': 'true',
        'state': state,
    })}"


def verify_google_oauth_state(settings: Settings, *, state: str, actor: str, redirect_uri: str) -> None:
    try:
        payload = json.loads(
            credential_cipher(settings).decrypt(state.encode(), ttl=GOOGLE_OAUTH_STATE_TTL_SECONDS).decode()
        )
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Google sign-in expired or could not be verified. Start the connection again.") from error
    if payload.get("actor") != actor or payload.get("redirect_uri") != redirect_uri:
        raise ValueError("Google sign-in could not be matched to this Pongo session. Start the connection again.")


def exchange_google_oauth_code(settings: Settings, *, code: str, redirect_uri: str) -> str:
    response = httpx.post(
        GOOGLE_OAUTH_TOKEN_URL,
        data={
            "client_id": settings.google_reports_client_id,
            "client_secret": settings.google_reports_client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    response.raise_for_status()
    refresh_token = str(response.json().get("refresh_token") or "").strip()
    if not refresh_token:
        raise ValueError("Google did not return ongoing access. Reconnect and approve access when Google asks.")
    return refresh_token
