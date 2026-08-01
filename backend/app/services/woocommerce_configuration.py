import base64
import hashlib
import json
import os
import secrets
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.woocommerce import WooCommerceConfiguration
from app.services.woocommerce_client import WooCommerceClient


ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
_save_lock = Lock()


def save_woocommerce_configuration(
    base_url: str,
    consumer_key: str | None,
    consumer_secret: str | None,
    *,
    allow_host_change: bool = False,
    env_path: Path = ENV_PATH,
    settings: Settings | None = None,
    client_type=WooCommerceClient,
    db: Session | None = None,
    changed_by: str | None = None,
) -> Settings:
    current = settings_with_persisted_woocommerce_configuration(db, settings or get_settings()) if db else (settings or get_settings())
    if db is None and current.app_env.casefold() == "production":
        raise ValueError("Production WooCommerce credentials must be changed in the deployment environment and applied by restarting the service.")
    normalized_url, requested_host = normalize_store_url(base_url)
    allowed_host = current.woocommerce_allowed_host.strip().lower()
    current_host = allowed_host or (urlparse(current.woocommerce_base_url).hostname or "").lower()
    host_changed = bool(current_host and requested_host != current_host)
    if host_changed and not allow_host_change:
        raise ValueError(
            f"WooCommerce store host '{requested_host}' does not match configured allowed host "
            f"'{current_host}'. Retry with allow_host_change=true to replace the allowed host."
        )
    if host_changed and (not (consumer_key or "").strip() or not (consumer_secret or "").strip()):
        raise ValueError("Enter a fresh consumer key and secret when changing the WooCommerce store host.")
    key = (consumer_key or "").strip() or current.woocommerce_consumer_key
    secret = (consumer_secret or "").strip() or current.woocommerce_consumer_secret
    if not key or not secret:
        raise ValueError("Enter both the WooCommerce consumer key and consumer secret.")
    if not key.startswith("ck_") or not secret.startswith("cs_"):
        raise ValueError("WooCommerce keys must begin with ck_ and secrets with cs_.")

    candidate = current.model_copy(
        update={
            "woocommerce_base_url": normalized_url,
            "woocommerce_consumer_key": key,
            "woocommerce_consumer_secret": secret,
            "woocommerce_allowed_host": requested_host,
        },
    )
    client_type(candidate).check_connection()

    if db is not None:
        cipher = credential_cipher(current, env_path=env_path, create_for_local=True)
        row = db.get(WooCommerceConfiguration, 1)
        if row is None:
            row = WooCommerceConfiguration(id=1)
            db.add(row)
        row.base_url = normalized_url
        row.allowed_host = requested_host
        row.consumer_key_ciphertext = cipher.encrypt(key.encode()).decode()
        row.consumer_secret_ciphertext = cipher.encrypt(secret.encode()).decode()
        row.updated_by = (changed_by or "authenticated-user")[:120]
        db.commit()
        db.refresh(row)
        return candidate

    values = {
        "WOOCOMMERCE_BASE_URL": normalized_url,
        "WOOCOMMERCE_CONSUMER_KEY": key,
        "WOOCOMMERCE_CONSUMER_SECRET": secret,
        "WOOCOMMERCE_ALLOWED_HOST": requested_host,
    }
    with _save_lock:
        update_env_file(env_path, values)
        os.environ.update(values)
        get_settings.cache_clear()
    return candidate


def latest_woocommerce_configuration(db: Session) -> WooCommerceConfiguration | None:
    return db.get(WooCommerceConfiguration, 1)


def settings_with_persisted_woocommerce_configuration(db: Session | None, settings: Settings) -> Settings:
    if db is None or not hasattr(settings, "model_copy"):
        return settings
    row = latest_woocommerce_configuration(db)
    if row is None:
        return settings
    cipher = credential_cipher(settings)
    try:
        key = cipher.decrypt(row.consumer_key_ciphertext.encode()).decode()
        secret = cipher.decrypt(row.consumer_secret_ciphertext.encode()).decode()
    except InvalidToken as error:
        raise ValueError("Stored WooCommerce credentials cannot be decrypted with the configured backend encryption key.") from error
    return settings.model_copy(update={
        "woocommerce_base_url": row.base_url,
        "woocommerce_allowed_host": row.allowed_host,
        "woocommerce_consumer_key": key,
        "woocommerce_consumer_secret": secret,
    })


def credential_cipher(settings: Settings, *, env_path: Path = ENV_PATH, create_for_local: bool = False) -> Fernet:
    secret = settings.woocommerce_configuration_encryption_key.strip()
    if not secret and create_for_local and settings.app_env.casefold() != "production":
        secret = secrets.token_urlsafe(48)
        values = {"WOOCOMMERCE_CONFIGURATION_ENCRYPTION_KEY": secret}
        with _save_lock:
            update_env_file(env_path, values)
            os.environ.update(values)
            get_settings.cache_clear()
    if len(secret.encode()) < 32:
        raise ValueError("The backend WooCommerce configuration encryption key must be at least 32 bytes.")
    derived = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(derived)


def normalize_store_url(value: str) -> tuple[str, str]:
    raw = value.strip().rstrip("/")
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("Enter a full WooCommerce store URL, such as https://pongo.ca.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("The store URL cannot contain credentials, a query, or a fragment.")
    if parsed.scheme != "https" and host not in {"localhost", "127.0.0.1"}:
        raise ValueError("WooCommerce connections must use HTTPS.")
    return raw, host


def update_env_file(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(values)
    updated: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key in remaining:
            updated.append(f"{key}={json.dumps(remaining.pop(key))}")
        else:
            updated.append(line)
    if updated and remaining:
        updated.append("")
    updated.extend(f"{key}={json.dumps(value)}" for key, value in remaining.items())

    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".env.", delete=False) as handle:
        handle.write("\n".join(updated).rstrip() + "\n")
        temporary_path = Path(handle.name)
    temporary_path.chmod(0o600)
    temporary_path.replace(path)
