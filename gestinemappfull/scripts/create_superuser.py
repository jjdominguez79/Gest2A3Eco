from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal
from app.models.user import User
from app.services.security_service import hash_password


def create_superuser(db: Session, *, email: str, password: str, full_name: str) -> None:
    existing = db.query(User).filter(User.email == email.lower().strip()).first()
    if existing is not None:
        print(f"User already exists: {existing.email}")
        return

    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        is_active=True,
        is_superuser=True,
    )
    db.add(user)
    db.commit()
    print(f"Superuser created: {user.email}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create initial GestinemAppFull superuser")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--full-name", required=True)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        create_superuser(db, email=args.email, password=args.password, full_name=args.full_name)
    finally:
        db.close()


if __name__ == "__main__":
    main()
