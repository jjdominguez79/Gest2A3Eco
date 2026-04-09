from __future__ import annotations

from pydantic import BaseModel, EmailStr

from app.schemas.user import UserMe


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserMe
