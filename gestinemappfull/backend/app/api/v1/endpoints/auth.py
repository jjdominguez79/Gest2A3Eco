from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserMe
from app.services.auth_service import AuthService


router = APIRouter(prefix="/auth")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    token, user = AuthService(db).authenticate(payload)
    return TokenResponse(access_token=token, user=UserMe.model_validate(user))


@router.get("/me", response_model=UserMe)
def me(current_user: User = Depends(get_current_user)) -> UserMe:
    return UserMe.model_validate(current_user)
