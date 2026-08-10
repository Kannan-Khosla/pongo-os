#!/usr/bin/env python3
"""Create or rotate an isolated Pongo OS demo account."""

import argparse
from getpass import getpass
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.auth import User
from app.services.auth import hash_password, normalize_email

email_adapter = TypeAdapter(EmailStr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update a mock-data, read-only demo user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", default="Pongo OS Demo")
    args = parser.parse_args()
    try:
        email = normalize_email(str(email_adapter.validate_python(args.email)))
    except ValidationError as error:
        raise SystemExit("Enter a valid demo email address.") from error
    display_name = args.display_name.strip()
    if not display_name or len(display_name) > 160:
        raise SystemExit("Display name must contain 1–160 characters.")
    password = getpass("Demo password (12+ characters): ")
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters.")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, display_name=display_name, password_hash=hash_password(password), access_level="demo", active=True)
            db.add(user)
            action = "Created"
        elif user.access_level != "demo":
            raise SystemExit("Refusing to convert an existing staff account into a demo account.")
        else:
            user.display_name = display_name
            user.password_hash = hash_password(password)
            user.active = True
            action = "Updated"
        db.commit()
        print(f"{action} demo account {email}.")


if __name__ == "__main__":
    main()
