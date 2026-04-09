from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.global_third_party import GlobalThirdParty
from app.schemas.third_party import GlobalThirdPartyCreate


class ThirdPartyService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, *, tax_id: str | None = None, legal_name: str | None = None) -> list[GlobalThirdParty]:
        query = self.db.query(GlobalThirdParty).filter(GlobalThirdParty.is_active.is_(True))
        if tax_id:
            query = query.filter(GlobalThirdParty.tax_id.ilike(f"%{tax_id.strip()}%"))
        if legal_name:
            term = legal_name.strip()
            query = query.filter(
                or_(
                    GlobalThirdParty.legal_name.ilike(f"%{term}%"),
                    GlobalThirdParty.trade_name.ilike(f"%{term}%"),
                )
            )
        return query.order_by(GlobalThirdParty.legal_name.asc()).all()

    def create(self, payload: GlobalThirdPartyCreate) -> GlobalThirdParty:
        third_party = GlobalThirdParty(
            third_party_type=payload.third_party_type,
            tax_id=(payload.tax_id or "").strip() or None,
            legal_name=payload.legal_name.strip(),
            trade_name=(payload.trade_name or "").strip() or None,
            email=(payload.email or "").strip() or None,
            phone=(payload.phone or "").strip() or None,
            address=(payload.address or "").strip() or None,
            city=(payload.city or "").strip() or None,
            postal_code=(payload.postal_code or "").strip() or None,
            country=(payload.country or "").strip() or None,
            is_active=True,
        )
        self.db.add(third_party)
        self.db.commit()
        self.db.refresh(third_party)
        return third_party
