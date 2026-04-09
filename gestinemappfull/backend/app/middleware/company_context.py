from __future__ import annotations

import uuid

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.db.session import SessionLocal
from app.models.company import Company
from app.models.company_membership import CompanyMembership
from app.models.user import User
from app.services.security_service import decode_token


class CompanyContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.company_id = None

        company_header = request.headers.get("X-Company-Id")
        if not company_header:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authorization header is required when X-Company-Id is provided."},
            )

        token = auth_header.removeprefix("Bearer ").strip()
        db = SessionLocal()
        try:
            payload = decode_token(token)
            user_id_raw = payload.get("sub")
            company_id = uuid.UUID(company_header)
            user_id = uuid.UUID(user_id_raw)

            user = db.get(User, user_id)
            if user is None or not user.is_active:
                return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "Invalid user."})

            company = db.get(Company, company_id)
            if company is None or not company.is_active:
                return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Company not found."})

            membership = (
                db.query(CompanyMembership)
                .filter(
                    CompanyMembership.user_id == user.id,
                    CompanyMembership.company_id == company.id,
                    CompanyMembership.is_active.is_(True),
                )
                .first()
            )
            if membership is None:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "User does not belong to selected company."},
                )

            request.state.company_id = company.id
            request.state.company_role = membership.role.value
            return await call_next(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        except ValueError:
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": "Invalid company context."})
        finally:
            db.close()
