from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.third_party import GlobalThirdPartyCreate, GlobalThirdPartyRead
from app.services.third_party_service import ThirdPartyService


router = APIRouter(prefix="/third-parties")


@router.get("", response_model=list[GlobalThirdPartyRead])
def list_third_parties(
    tax_id: str | None = Query(default=None),
    legal_name: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[GlobalThirdPartyRead]:
    del current_user
    items = ThirdPartyService(db).list(tax_id=tax_id, legal_name=legal_name)
    return [GlobalThirdPartyRead.model_validate(item) for item in items]


@router.post("", response_model=GlobalThirdPartyRead, status_code=status.HTTP_201_CREATED)
def create_third_party(
    payload: GlobalThirdPartyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GlobalThirdPartyRead:
    del current_user
    item = ThirdPartyService(db).create(payload)
    return GlobalThirdPartyRead.model_validate(item)
