from collections.abc import Callable
from typing import Any

from cryptography.fernet import InvalidToken
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.reporting import GoogleReportsConfiguration
from app.services.woocommerce_configuration import credential_cipher


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
