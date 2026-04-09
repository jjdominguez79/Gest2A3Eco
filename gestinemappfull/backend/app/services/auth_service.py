from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.auth import LoginRequest
from app.services.security_service import create_access_token, verify_password


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def authenticate(self, payload: LoginRequest) -> tuple[str, User]:
        user = self.db.query(User).filter(User.email == payload.email.lower().strip()).first()
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
        if not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
        token = create_access_token(str(user.id))
        return token, user
