"""API del catalogo de productos y servicios para facturacion online.

Ver docs/adr/0001-facturacion-autonoma-cliente.md, Etapa 4.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.client_catalog_service import (
    catalog_item_to_dict,
    validate_catalog_item_payload,
)
from backend.api.client_models import ClientCatalogItem
from backend.api.client_invoices_api import _authenticated_client, _db
from backend.api.feature_flags import require_invoicing_enabled as _require_invoicing_enabled

router = APIRouter(
    prefix="/api/v1/messaging/client/invoicing/catalog",
    tags=["client-invoicing-catalog"],
)


@router.get("/items")
def list_catalog_items(
    request: Request,
    q: str = Query(""),
    active: bool | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(_db),
):
    client = _authenticated_client(request, db)
    _require_invoicing_enabled(db, client.organization_id)

    query = select(ClientCatalogItem).where(
        ClientCatalogItem.organization_id == client.organization_id,
    )
    if active is not None:
        query = query.where(ClientCatalogItem.active.is_(active))
    if q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.where(
            func.lower(ClientCatalogItem.description).like(like)
            | func.lower(ClientCatalogItem.code).like(like)
        )

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(
        query.order_by(ClientCatalogItem.description).offset(offset).limit(limit)
    ).all()

    return {
        "items": [catalog_item_to_dict(i) for i in items],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post("/items")
def create_catalog_item(
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(_db),
):
    client = _authenticated_client(request, db)
    _require_invoicing_enabled(db, client.organization_id)

    try:
        clean = validate_catalog_item_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    item = ClientCatalogItem(
        organization_id=client.organization_id,
        **clean,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return catalog_item_to_dict(item)


@router.get("/items/{item_id}")
def get_catalog_item(item_id: str, request: Request, db: Session = Depends(_db)):
    client = _authenticated_client(request, db)
    _require_invoicing_enabled(db, client.organization_id)
    item = db.get(ClientCatalogItem, item_id)
    if not item or item.organization_id != client.organization_id:
        raise HTTPException(status_code=404)
    return catalog_item_to_dict(item)


@router.put("/items/{item_id}")
def update_catalog_item(
    item_id: str,
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(_db),
):
    client = _authenticated_client(request, db)
    _require_invoicing_enabled(db, client.organization_id)
    item = db.get(ClientCatalogItem, item_id)
    if not item or item.organization_id != client.organization_id:
        raise HTTPException(status_code=404)

    merged = catalog_item_to_dict(item) | payload
    try:
        clean = validate_catalog_item_payload(merged)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    for field, value in clean.items():
        setattr(item, field, value)
    if "active" in payload:
        item.active = bool(payload["active"])
    # Editar el articulo nunca altera lineas ya copiadas (borradores
    # confirmados o facturas emitidas): estas guardan su propia copia.
    item.revision += 1
    db.commit()
    db.refresh(item)
    return catalog_item_to_dict(item)


@router.delete("/items/{item_id}")
def deactivate_catalog_item(item_id: str, request: Request, db: Session = Depends(_db)):
    """Baja logica. Nunca elimina fisicamente un articulo usado en lineas."""
    client = _authenticated_client(request, db)
    _require_invoicing_enabled(db, client.organization_id)
    item = db.get(ClientCatalogItem, item_id)
    if not item or item.organization_id != client.organization_id:
        raise HTTPException(status_code=404)

    item.active = False
    item.revision += 1
    db.commit()
    return {"status": "deactivated"}
