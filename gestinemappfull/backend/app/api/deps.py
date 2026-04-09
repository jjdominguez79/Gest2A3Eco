from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.company_membership import CompanyMembership
from app.models.user import User
from app.services.security_service import decode_token


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    token = credentials.credentials
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    user = db.get(User, uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive.")
    return user


def get_active_company_id(request: Request) -> uuid.UUID:
    company_id = getattr(request.state, "company_id", None)
    if company_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Company-Id header is required for this endpoint.",
        )
    return company_id


def get_active_membership(
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_active_company_id),
    db: Session = Depends(get_db),
) -> CompanyMembership:
    membership = (
        db.query(CompanyMembership)
        .filter(
            CompanyMembership.user_id == current_user.id,
            CompanyMembership.company_id == company_id,
            CompanyMembership.is_active.is_(True),
        )
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to active company.")
    return membership
