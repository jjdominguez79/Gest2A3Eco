"""API de facturacion online del cliente.

Endpoints para borradores, emision, listado, configuracion y worker.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.client_invoice_service import (
    assign_invoice_number,
    chain_verifactu_hash,
    compute_verifactu_hash,
    create_invoice_event,
    create_issued_snapshot,
    recalculate_invoice,
)
from backend.api.client_models import (
    ClientInvoice,
    ClientInvoiceCustomer,
    ClientInvoiceEvent,
    ClientInvoiceLine,
    ClientInvoiceProcessingQueue,
    ClientInvoiceSeries,
)
from backend.api.client_storage import ClientDocumentStorage
from backend.api.client_validation import normalize_tax_id, validate_tax_id
from backend.api.feature_flags import (
    is_invoicing_enabled,
    require_invoicing_enabled as _require_invoicing_enabled,
)
from backend.api.database import SessionLocal
from backend.api.messaging_models import (
    MessagingClient,
    MessagingOrganization,
    MessagingSession,
)
from backend.api.messaging_security import hash_token, is_expired, utcnow
from backend.api.security import require_workstation_or_internal

router = APIRouter(
    prefix="/api/v1/messaging/client/invoicing",
    tags=["client-invoicing"],
)

_storage: ClientDocumentStorage | None = None


def _get_storage() -> ClientDocumentStorage:
    global _storage
    if _storage is None:
        _storage = ClientDocumentStorage()
    return _storage


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _authenticated_client(request: Request, db: Session) -> MessagingClient:
    token = ""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        token = request.cookies.get("msg_session", "")
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")

    session = db.scalar(
        select(MessagingSession).where(
            MessagingSession.token_hash == hash_token(token),
        )
    )
    if not session or session.revoked_at or is_expired(session.expires_at):
        raise HTTPException(status_code=401, detail="Sesion no valida")

    client = db.get(MessagingClient, session.client_id)
    if not client or not client.active:
        raise HTTPException(status_code=403, detail="Cliente inactivo")
    return client


def _invoice_to_dict(inv: ClientInvoice, lines: list[ClientInvoiceLine] | None = None) -> dict:
    result = {
        "id": inv.id,
        "fiscal_year": inv.fiscal_year,
        "series_code": inv.series_code,
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
        "status": inv.status,
        "customer_id": inv.customer_id,
        "subtotal": str(inv.subtotal),
        "total_vat": str(inv.total_vat),
        "withholding_rate": str(inv.withholding_rate),
        "withholding_amount": str(inv.withholding_amount),
        "total": str(inv.total),
        "currency": inv.currency,
        "payment_method": inv.payment_method,
        "notes": inv.notes,
        "recipient_email": inv.recipient_email,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "issued_at": inv.issued_at.isoformat() if inv.issued_at else None,
    }
    if lines is not None:
        result["lines"] = [
            {
                "id": l.id,
                "line_number": l.line_number,
                "description": l.description,
                "quantity": str(l.quantity),
                "unit_price": str(l.unit_price),
                "discount_percent": str(l.discount_percent),
                "vat_rate": str(l.vat_rate),
                "line_total": str(l.line_total),
                "vat_amount": str(l.vat_amount),
            }
            for l in sorted(lines, key=lambda x: x.line_number)
        ]
    return result


def _customer_to_dict(c: ClientInvoiceCustomer) -> dict:
    return {
        "id": c.id,
        "tax_id": c.tax_id,
        "legal_name": c.legal_name,
        "address": c.address,
        "postal_code": c.postal_code,
        "city": c.city,
        "province": c.province,
        "country": c.country,
        "email": c.email,
        "phone": c.phone,
        "default_vat_rate": str(c.default_vat_rate),
        "active": c.active,
    }


# ===== CONFIGURACION =====


@router.get("/config")
def get_invoicing_config(request: Request, db: Session = Depends(_db)):
    """Devuelve configuracion de facturacion para la organizacion del cliente."""
    client = _authenticated_client(request, db)
    org = db.get(MessagingOrganization, client.organization_id)
    if not org:
        raise HTTPException(status_code=404)

    current_year = datetime.now(timezone.utc).year
    series = db.scalars(
        select(ClientInvoiceSeries).where(
            ClientInvoiceSeries.organization_id == org.id,
            ClientInvoiceSeries.fiscal_year == current_year,
        )
    ).all()

    return {
        "enabled": is_invoicing_enabled(org),
        "fiscal_year": current_year,
        "series": [
            {
                "code": s.series_code,
                "next_number": s.next_number,
                "description": s.description,
            }
            for s in series
        ],
    }


# ===== CLIENTES/DEUDORES =====


@router.get("/customers")
def list_customers(request: Request, db: Session = Depends(_db)):
    client = _authenticated_client(request, db)
    _require_invoicing_enabled(db, client.organization_id)

    customers = db.scalars(
        select(ClientInvoiceCustomer).where(
            ClientInvoiceCustomer.organization_id == client.organization_id,
            ClientInvoiceCustomer.active.is_(True),
        ).order_by(ClientInvoiceCustomer.legal_name)
    ).all()
    return [_customer_to_dict(c) for c in customers]


@router.post("/customers")
def create_customer(
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(_db),
):
    client = _authenticated_client(request, db)
    org = _require_invoicing_enabled(db, client.organization_id)

    tax_id = payload.get("tax_id", "").strip()
    if not tax_id:
        raise HTTPException(status_code=400, detail="NIF/CIF es obligatorio")

    normalized = normalize_tax_id(tax_id)
    if not validate_tax_id(normalized):
        raise HTTPException(status_code=400, detail="NIF/CIF no valido")

    # Duplicado
    existing = db.scalar(
        select(ClientInvoiceCustomer).where(
            ClientInvoiceCustomer.organization_id == client.organization_id,
            ClientInvoiceCustomer.tax_id_normalized == normalized,
        )
    )
    if existing:
        return _customer_to_dict(existing)

    legal_name = payload.get("legal_name", "").strip()
    if not legal_name:
        raise HTTPException(status_code=400, detail="Razon social es obligatoria")

    cust = ClientInvoiceCustomer(
        organization_id=client.organization_id,
        tax_id=tax_id.upper().strip(),
        tax_id_normalized=normalized,
        legal_name=legal_name,
        address=payload.get("address", ""),
        postal_code=payload.get("postal_code", ""),
        city=payload.get("city", ""),
        province=payload.get("province", ""),
        country=payload.get("country", "ES"),
        email=payload.get("email", ""),
        phone=payload.get("phone", ""),
        default_vat_rate=Decimal(str(payload.get("default_vat_rate", "21.00"))),
        pending_desktop_import=True,
    )
    db.add(cust)
    db.commit()
    db.refresh(cust)
    return _customer_to_dict(cust)


# ===== BORRADORES =====


@router.get("/drafts")
def list_drafts(request: Request, db: Session = Depends(_db)):
    client = _authenticated_client(request, db)
    _require_invoicing_enabled(db, client.organization_id)

    drafts = db.scalars(
        select(ClientInvoice).where(
            ClientInvoice.organization_id == client.organization_id,
            ClientInvoice.status == "draft",
        ).order_by(ClientInvoice.updated_at.desc())
    ).all()
    return [_invoice_to_dict(inv) for inv in drafts]


@router.post("/drafts")
def create_draft(
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(_db),
):
    client = _authenticated_client(request, db)
    org = _require_invoicing_enabled(db, client.organization_id)

    customer_id = payload.get("customer_id", "")
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id es obligatorio")

    # Verificar que el cliente pertenece a la organizacion
    customer = db.get(ClientInvoiceCustomer, customer_id)
    if not customer or customer.organization_id != client.organization_id:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    fiscal_year = payload.get("fiscal_year", datetime.now(timezone.utc).year)
    series_code = payload.get("series_code", "WEB")

    invoice_date = None
    if payload.get("invoice_date"):
        try:
            invoice_date = datetime.fromisoformat(payload["invoice_date"])
            if invoice_date.tzinfo is None:
                invoice_date = invoice_date.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    inv = ClientInvoice(
        organization_id=client.organization_id,
        customer_id=customer_id,
        fiscal_year=fiscal_year,
        series_code=series_code,
        invoice_date=invoice_date,
        status="draft",
        withholding_rate=Decimal(str(payload.get("withholding_rate", "0"))),
        payment_method=payload.get("payment_method", ""),
        notes=payload.get("notes", ""),
        recipient_email=payload.get("recipient_email", customer.email),
        created_by_client_id=client.id,
    )
    db.add(inv)
    db.flush()

    # Lineas
    lines_data = payload.get("lines", [])
    lines = []
    for i, ld in enumerate(lines_data, 1):
        line = ClientInvoiceLine(
            invoice_id=inv.id,
            line_number=i,
            description=ld.get("description", ""),
            quantity=Decimal(str(ld.get("quantity", "1"))),
            unit_price=Decimal(str(ld.get("unit_price", "0"))),
            discount_percent=Decimal(str(ld.get("discount_percent", "0"))),
            vat_rate=Decimal(str(ld.get("vat_rate", "21.00"))),
        )
        db.add(line)
        lines.append(line)

    recalculate_invoice(inv, lines)
    db.commit()
    db.refresh(inv)
    return _invoice_to_dict(inv, lines)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: str, request: Request, db: Session = Depends(_db)):
    client = _authenticated_client(request, db)
    inv = db.get(ClientInvoice, draft_id)
    if not inv or inv.organization_id != client.organization_id:
        raise HTTPException(status_code=404)
    if inv.status != "draft":
        raise HTTPException(status_code=400, detail="No es un borrador")

    lines = db.scalars(
        select(ClientInvoiceLine).where(ClientInvoiceLine.invoice_id == inv.id)
    ).all()
    return _invoice_to_dict(inv, list(lines))


@router.put("/drafts/{draft_id}")
def update_draft(
    draft_id: str,
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(_db),
):
    client = _authenticated_client(request, db)
    inv = db.get(ClientInvoice, draft_id)
    if not inv or inv.organization_id != client.organization_id:
        raise HTTPException(status_code=404)
    if inv.status != "draft":
        raise HTTPException(status_code=400, detail="Solo se pueden editar borradores")

    # Actualizar campos
    for field in ("payment_method", "notes", "recipient_email"):
        if field in payload:
            setattr(inv, field, payload[field])

    if "withholding_rate" in payload:
        inv.withholding_rate = Decimal(str(payload["withholding_rate"]))

    if "invoice_date" in payload and payload["invoice_date"]:
        try:
            dt = datetime.fromisoformat(payload["invoice_date"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            inv.invoice_date = dt
        except ValueError:
            pass

    if "customer_id" in payload:
        cust = db.get(ClientInvoiceCustomer, payload["customer_id"])
        if cust and cust.organization_id == client.organization_id:
            inv.customer_id = cust.id

    # Reemplazar lineas si se envian
    if "lines" in payload:
        # Borrar existentes
        old_lines = db.scalars(
            select(ClientInvoiceLine).where(ClientInvoiceLine.invoice_id == inv.id)
        ).all()
        for ol in old_lines:
            db.delete(ol)
        db.flush()

        lines = []
        for i, ld in enumerate(payload["lines"], 1):
            line = ClientInvoiceLine(
                invoice_id=inv.id,
                line_number=i,
                description=ld.get("description", ""),
                quantity=Decimal(str(ld.get("quantity", "1"))),
                unit_price=Decimal(str(ld.get("unit_price", "0"))),
                discount_percent=Decimal(str(ld.get("discount_percent", "0"))),
                vat_rate=Decimal(str(ld.get("vat_rate", "21.00"))),
            )
            db.add(line)
            lines.append(line)

        recalculate_invoice(inv, lines)

    inv.updated_at = utcnow()
    db.commit()
    db.refresh(inv)

    final_lines = db.scalars(
        select(ClientInvoiceLine).where(ClientInvoiceLine.invoice_id == inv.id)
    ).all()
    return _invoice_to_dict(inv, list(final_lines))


@router.delete("/drafts/{draft_id}")
def delete_draft(draft_id: str, request: Request, db: Session = Depends(_db)):
    client = _authenticated_client(request, db)
    inv = db.get(ClientInvoice, draft_id)
    if not inv or inv.organization_id != client.organization_id:
        raise HTTPException(status_code=404)
    if inv.status != "draft":
        raise HTTPException(status_code=400, detail="Solo se pueden eliminar borradores")

    # Borrar lineas y factura
    lines = db.scalars(
        select(ClientInvoiceLine).where(ClientInvoiceLine.invoice_id == inv.id)
    ).all()
    for l in lines:
        db.delete(l)
    db.delete(inv)
    db.commit()
    return {"status": "deleted"}


# ===== EMISION =====


@router.post("/drafts/{draft_id}/issue")
def issue_invoice(
    draft_id: str,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(_db),
):
    """Emite una factura: asigna numero, recalcula, crea snapshot inmutable."""
    client = _authenticated_client(request, db)
    org = _require_invoicing_enabled(db, client.organization_id)

    # Idempotencia: verificar si ya se emitio con esta clave
    existing = db.scalar(
        select(ClientInvoice).where(
            ClientInvoice.idempotency_key == idempotency_key,
            ClientInvoice.organization_id == client.organization_id,
        )
    )
    if existing and existing.status != "draft":
        ex_lines = db.scalars(
            select(ClientInvoiceLine).where(
                ClientInvoiceLine.invoice_id == existing.id,
            )
        ).all()
        return _invoice_to_dict(existing, list(ex_lines))

    inv = db.get(ClientInvoice, draft_id)
    if not inv or inv.organization_id != client.organization_id:
        raise HTTPException(status_code=404)
    if inv.status != "draft":
        raise HTTPException(status_code=400, detail="Solo se pueden emitir borradores")

    # Obtener lineas y cliente
    lines = list(db.scalars(
        select(ClientInvoiceLine).where(ClientInvoiceLine.invoice_id == inv.id)
    ).all())
    if not lines:
        raise HTTPException(status_code=400, detail="La factura no tiene lineas")

    customer = db.get(ClientInvoiceCustomer, inv.customer_id)
    if not customer:
        raise HTTPException(status_code=400, detail="Cliente no encontrado")

    # Recalcular con Decimal
    recalculate_invoice(inv, lines)

    # Asignar numero (con bloqueo de fila)
    number = assign_invoice_number(
        db, org.id, inv.fiscal_year, inv.series_code,
    )
    inv.invoice_number = number
    inv.idempotency_key = idempotency_key
    inv.status = "issued_pending_processing"
    inv.issued_at = utcnow()

    if not inv.invoice_date:
        inv.invoice_date = inv.issued_at

    # Snapshot inmutable
    inv.issued_snapshot = create_issued_snapshot(inv, lines, customer, org)

    # Veri*FACTU (preparacion)
    inv.verifactu_hash = compute_verifactu_hash(inv, lines)
    inv.verifactu_chain_hash = chain_verifactu_hash(inv.verifactu_hash, "")

    # Evento
    create_invoice_event(
        db, inv.id, "issued", "draft", "issued_pending_processing",
        actor_type="client", actor_id=client.id,
    )

    # Encolar para procesamiento
    queue_item = ClientInvoiceProcessingQueue(
        invoice_id=inv.id,
        organization_id=org.id,
        queue_status="pending",
    )
    db.add(queue_item)

    db.commit()
    db.refresh(inv)
    return _invoice_to_dict(inv, lines)


# ===== FACTURAS EMITIDAS =====


@router.get("/invoices")
def list_invoices(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: str = Query(""),
    fiscal_year: int = Query(0),
    db: Session = Depends(_db),
):
    client = _authenticated_client(request, db)
    _require_invoicing_enabled(db, client.organization_id)

    query = select(ClientInvoice).where(
        ClientInvoice.organization_id == client.organization_id,
        ClientInvoice.status != "draft",
    )
    if status:
        query = query.where(ClientInvoice.status == status)
    if fiscal_year:
        query = query.where(ClientInvoice.fiscal_year == fiscal_year)

    query = query.order_by(ClientInvoice.issued_at.desc().nullslast())
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    invoices = db.scalars(query.offset(offset).limit(limit)).all()

    return {
        "items": [_invoice_to_dict(inv) for inv in invoices],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: str, request: Request, db: Session = Depends(_db)):
    client = _authenticated_client(request, db)
    _require_invoicing_enabled(db, client.organization_id)
    inv = db.get(ClientInvoice, invoice_id)
    if not inv or inv.organization_id != client.organization_id:
        raise HTTPException(status_code=404)

    lines = db.scalars(
        select(ClientInvoiceLine).where(ClientInvoiceLine.invoice_id == inv.id)
    ).all()
    return _invoice_to_dict(inv, list(lines))


# ===== WORKER ENDPOINTS =====


@router.post("/worker/claim")
def worker_claim(
    payload: dict = Body(...),
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Reclama la siguiente factura pendiente de procesamiento."""
    worker_id = payload.get("worker_id", "unknown")
    lease_minutes = payload.get("lease_minutes", 10)

    # Buscar pendiente o con lease caducado
    now = utcnow()
    item = db.scalar(
        select(ClientInvoiceProcessingQueue)
        .where(
            ClientInvoiceProcessingQueue.queue_status.in_(["pending", "error"]),
        )
        .where(
            (ClientInvoiceProcessingQueue.lease_expires_at.is_(None))
            | (ClientInvoiceProcessingQueue.lease_expires_at < now)
        )
        .where(
            ClientInvoiceProcessingQueue.retry_count
            < ClientInvoiceProcessingQueue.max_retries
        )
        .order_by(ClientInvoiceProcessingQueue.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if not item:
        return {"claimed": False}

    item.queue_status = "claimed"
    item.claimed_by = worker_id
    item.claimed_at = now
    item.lease_expires_at = now + timedelta(minutes=lease_minutes)
    item.updated_at = now

    inv = db.get(ClientInvoice, item.invoice_id)
    if inv:
        old_status = inv.status
        inv.status = "claimed"
        create_invoice_event(
            db, inv.id, "claimed", old_status, "claimed",
            actor_type="worker", actor_id=worker_id,
        )

    db.commit()
    return {"claimed": True, "queue_id": item.id, "invoice_id": item.invoice_id}


@router.get("/worker/invoice/{invoice_id}/payload")
def worker_get_payload(
    invoice_id: str,
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Descarga datos completos de factura para el worker."""
    inv = db.get(ClientInvoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)

    lines = db.scalars(
        select(ClientInvoiceLine).where(ClientInvoiceLine.invoice_id == inv.id)
    ).all()
    customer = db.get(ClientInvoiceCustomer, inv.customer_id)
    org = db.get(MessagingOrganization, inv.organization_id)

    result = _invoice_to_dict(inv, list(lines))
    if customer:
        result["customer"] = _customer_to_dict(customer)
    if org:
        result["organization"] = {
            "company_code": org.company_code,
            "name": org.name,
            "legal_name": org.legal_name or org.name,
            "tax_id": org.tax_id or "",
            "address": org.address or "",
            "postal_code": org.postal_code or "",
            "city": org.city or "",
            "province": org.province or "",
            "country": org.country or "ES",
            "phone": org.phone or "",
            "email": org.email or "",
        }
    result["issued_snapshot"] = inv.issued_snapshot

    # Push tokens del cliente emisor para FCM
    push_tokens = []
    if inv.created_by_client_id:
        from backend.api.messaging_models import MessagingAppDevice
        devices = db.scalars(
            select(MessagingAppDevice).where(
                MessagingAppDevice.user_type == "client",
                MessagingAppDevice.user_id == inv.created_by_client_id,
                MessagingAppDevice.active.is_(True),
            )
        ).all()
        push_tokens = [
            {"token": d.push_token, "platform": d.platform}
            for d in devices if d.push_token
        ]
    result["push_tokens"] = push_tokens

    return result


@router.post("/worker/invoice/{invoice_id}/import-confirmed")
def worker_confirm_import(
    invoice_id: str,
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Confirma que la factura fue importada al escritorio."""
    inv = db.get(ClientInvoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)

    old_status = inv.status
    inv.status = "imported"
    create_invoice_event(
        db, inv.id, "imported", old_status, "imported",
        actor_type="worker",
    )
    db.commit()
    return {"status": "ok"}


@router.post("/worker/invoice/{invoice_id}/pdf")
async def worker_upload_pdf(
    invoice_id: str,
    file: UploadFile = File(...),
    sha256: str = Form(...),
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Sube el PDF renderizado por el worker a Azure y marca rendered."""
    import hashlib

    inv = db.get(ClientInvoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)

    max_pdf_bytes = 50 * 1024 * 1024
    content = await file.read(max_pdf_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacio")
    if len(content) > max_pdf_bytes:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande")

    # Verificar SHA-256
    actual_sha = hashlib.sha256(content).hexdigest()
    if actual_sha != sha256:
        raise HTTPException(status_code=400, detail="SHA-256 no coincide")

    queue_item = db.scalar(
        select(ClientInvoiceProcessingQueue).where(
            ClientInvoiceProcessingQueue.invoice_id == invoice_id,
        )
    )
    if (
        queue_item
        and queue_item.pdf_sha256 == sha256
        and queue_item.pdf_blob_key
    ):
        return {
            "status": "ok",
            "sha256": sha256,
            "blob_key": queue_item.pdf_blob_key,
            "file_size": queue_item.pdf_file_size,
        }

    # Subir a storage permanente ANTES de marcar rendered
    storage = _get_storage()
    display = f"{inv.series_code}-{str(inv.invoice_number or 0).zfill(6)}.pdf"
    blob_key = storage.put(
        content, display, organization_id=inv.organization_id,
    )

    try:
        # Actualizar cola con blob_key, tamanio y SHA-256
        if queue_item:
            queue_item.pdf_sha256 = sha256
            queue_item.pdf_blob_key = blob_key
            queue_item.pdf_file_size = len(content)
            queue_item.queue_status = "rendered"
            queue_item.updated_at = utcnow()

        old_status = inv.status
        inv.status = "rendered"
        create_invoice_event(
            db, inv.id, "rendered", old_status, "rendered",
            actor_type="worker",
        )
        db.commit()
    except Exception:
        # Si falla la transaccion, eliminar el blob huerfano
        try:
            storage.delete(blob_key)
        except Exception:
            pass
        db.rollback()
        raise

    return {
        "status": "ok",
        "sha256": actual_sha,
        "blob_key": blob_key,
        "file_size": len(content),
    }


@router.post("/worker/invoice/{invoice_id}/error")
def worker_report_error(
    invoice_id: str,
    payload: dict = Body(...),
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Reporta un error de procesamiento reintentable."""
    inv = db.get(ClientInvoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)

    error_msg = payload.get("error", "Error desconocido")

    queue_item = db.scalar(
        select(ClientInvoiceProcessingQueue).where(
            ClientInvoiceProcessingQueue.invoice_id == invoice_id,
        )
    )
    if queue_item:
        queue_item.queue_status = "error"
        queue_item.error_message = error_msg
        queue_item.retry_count += 1
        queue_item.lease_expires_at = None
        queue_item.claimed_by = ""
        queue_item.updated_at = utcnow()

    old_status = inv.status
    inv.status = "processing_error"
    create_invoice_event(
        db, inv.id, "processing_error", old_status, "processing_error",
        actor_type="worker", detail=error_msg,
    )
    db.commit()
    return {"status": "ok", "retryable": queue_item.retry_count < queue_item.max_retries if queue_item else False}


@router.post("/worker/invoice/{invoice_id}/publish-document")
def worker_publish_document(
    invoice_id: str,
    payload: dict = Body(...),
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Crea el ClientDocument a partir del PDF ya almacenado en blob."""
    from backend.api.client_models import ClientDocument

    inv = db.get(ClientInvoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)

    queue_item = db.scalar(
        select(ClientInvoiceProcessingQueue).where(
            ClientInvoiceProcessingQueue.invoice_id == invoice_id,
        )
    )
    if not queue_item or not queue_item.pdf_blob_key:
        raise HTTPException(status_code=400, detail="PDF no almacenado todavia")

    # Idempotente: si ya hay document_id, devolver
    if inv.document_id:
        return {"status": "ok", "document_id": inv.document_id}

    display = f"{inv.series_code}-{str(inv.invoice_number or 0).zfill(6)}.pdf"
    doc = ClientDocument(
        organization_id=inv.organization_id,
        document_type="factura_emitida_online",
        source_system="client_invoice",
        source_id=inv.id,
        source_version=1,
        display_name=display,
        description=payload.get("description", ""),
        document_date=inv.invoice_date,
        fiscal_year=inv.fiscal_year,
        amount=inv.total,
        currency=inv.currency,
        file_name=display,
        content_type="application/pdf",
        file_size=queue_item.pdf_file_size,
        sha256=queue_item.pdf_sha256,
        blob_key=queue_item.pdf_blob_key,
        status="published",
    )
    db.add(doc)
    db.flush()

    inv.document_id = doc.id
    db.commit()
    return {"status": "ok", "document_id": doc.id}


@router.post("/worker/invoice/{invoice_id}/emailed")
def worker_mark_emailed(
    invoice_id: str,
    payload: dict | None = Body(default=None),
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Marca la factura como emailed tras envio real por Graph."""
    inv = db.get(ClientInvoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)

    queue_item = db.scalar(
        select(ClientInvoiceProcessingQueue).where(
            ClientInvoiceProcessingQueue.invoice_id == invoice_id,
        )
    )
    if inv.status == "emailed" and (
        queue_item is None or queue_item.queue_status == "completed"
    ):
        return {"status": "ok"}

    payload = payload or {}

    old_status = inv.status
    inv.status = "emailed"
    create_invoice_event(
        db, inv.id, "emailed", old_status, "emailed",
        actor_type="worker",
        detail=payload.get("message_id", ""),
    )

    if queue_item:
        queue_item.queue_status = "completed"
        queue_item.updated_at = utcnow()

    db.commit()
    return {"status": "ok"}


@router.post("/worker/invoice/{invoice_id}/send-email")
def worker_send_email(
    invoice_id: str,
    payload: dict = Body(...),
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Envia email con la factura via Graph. Idempotente por estado."""
    inv = db.get(ClientInvoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)

    # Idempotente: si ya esta marcado como emailed, no reenviar
    if inv.status == "emailed":
        return {"status": "ok", "already_sent": True}

    queue_item = db.scalar(
        select(ClientInvoiceProcessingQueue).where(
            ClientInvoiceProcessingQueue.invoice_id == invoice_id,
        )
    )
    if not queue_item or not queue_item.pdf_blob_key:
        raise HTTPException(status_code=400, detail="PDF no disponible todavia")

    recipient = payload.get("recipient_email", "") or inv.recipient_email or ""
    if not recipient:
        # Sin destinatario: marcar como completado sin envio
        old_status = inv.status
        inv.status = "emailed"
        create_invoice_event(
            db, inv.id, "emailed", old_status, "emailed",
            actor_type="worker", detail="sin_destinatario",
        )
        if queue_item:
            queue_item.queue_status = "completed"
            queue_item.updated_at = utcnow()
        db.commit()
        return {"status": "ok", "skipped": True, "reason": "sin_destinatario"}

    # Descargar PDF del blob storage
    storage = _get_storage()
    try:
        pdf_content = storage.get(queue_item.pdf_blob_key)
    except Exception:
        raise HTTPException(status_code=500, detail="Error descargando PDF")

    # Construir datos del email
    org = db.get(MessagingOrganization, inv.organization_id)
    org_name = org.name if org else ""
    series = inv.series_code or "WEB"
    number = inv.invoice_number or 0
    display = f"{series}-{number:06d}"

    subject = f"Factura {display} - {org_name}"
    body_text = (
        f"Estimado cliente,\n\n"
        f"Adjuntamos la factura {display}.\n\n"
        f"Un saludo,\n{org_name}"
    )

    # Enviar via Graph
    try:
        from backend.api.config import get_settings
        settings = get_settings()
        sender_mailbox = (
            payload.get("sender_mailbox", "") or settings.messaging_graph_from
        )
        if not sender_mailbox:
            raise HTTPException(
                status_code=500, detail="Buzon remitente no configurado",
            )

        from services.graph_mail_service import GraphMailService
        import tempfile
        import os

        # Escribir PDF temporal para Graph
        tmp_dir = tempfile.mkdtemp()
        tmp_pdf = os.path.join(tmp_dir, f"{display}.pdf")
        with open(tmp_pdf, "wb") as f:
            f.write(pdf_content)

        try:
            mail_service = GraphMailService()
            result = mail_service.send(
                sender=sender_mailbox,
                to=[recipient],
                subject=subject,
                body=body_text,
                attachments=[tmp_pdf],
            )
            message_id = getattr(result, "internet_message_id", "") or ""
        finally:
            try:
                os.unlink(tmp_pdf)
                os.rmdir(tmp_dir)
            except OSError:
                pass

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error enviando email: {exc}")

    # Marcar como emailed
    old_status = inv.status
    inv.status = "emailed"
    create_invoice_event(
        db, inv.id, "emailed", old_status, "emailed",
        actor_type="worker", detail=message_id,
    )
    if queue_item:
        queue_item.queue_status = "completed"
        queue_item.updated_at = utcnow()
    db.commit()

    return {"status": "ok", "message_id": message_id}


@router.post("/worker/invoice/{invoice_id}/send-fcm")
def worker_send_fcm(
    invoice_id: str,
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Envia notificacion FCM al emisor. Best-effort, no bloquea."""
    inv = db.get(ClientInvoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)

    # Obtener tokens push del cliente emisor
    push_tokens = []
    if inv.created_by_client_id:
        from backend.api.messaging_models import MessagingAppDevice
        devices = db.scalars(
            select(MessagingAppDevice).where(
                MessagingAppDevice.user_type == "client",
                MessagingAppDevice.user_id == inv.created_by_client_id,
                MessagingAppDevice.active.is_(True),
            )
        ).all()
        push_tokens = [
            {"token": d.push_token, "platform": d.platform}
            for d in devices if d.push_token
        ]

    if not push_tokens:
        return {"status": "ok", "sent": 0, "reason": "sin_tokens"}

    series = inv.series_code or "WEB"
    number = inv.invoice_number or 0
    fcm_payload = {
        "title": "Factura procesada",
        "body": f"Tu factura {series}-{number:06d} ha sido procesada.",
        "invoice_id": invoice_id,
        "type": "invoice_processed",
    }

    sent = 0
    errors = 0
    try:
        from backend.api.messaging_firebase import send_fcm
        for token_info in push_tokens:
            token = token_info.get("token", "")
            platform = token_info.get("platform", "android")
            if not token:
                continue
            try:
                send_fcm(token, fcm_payload, platform=platform)
                sent += 1
            except Exception:
                errors += 1
    except Exception:
        pass  # FCM es best-effort

    return {"status": "ok", "sent": sent, "errors": errors}


@router.get("/worker/invoice/{invoice_id}/status")
def worker_get_status(
    invoice_id: str,
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Consulta el estado de procesamiento de una factura."""
    inv = db.get(ClientInvoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404)

    queue_item = db.scalar(
        select(ClientInvoiceProcessingQueue).where(
            ClientInvoiceProcessingQueue.invoice_id == invoice_id,
        )
    )

    return {
        "invoice_id": invoice_id,
        "invoice_status": inv.status,
        "queue_status": queue_item.queue_status if queue_item else None,
        "pdf_uploaded": bool(queue_item and queue_item.pdf_blob_key),
        "document_published": bool(inv.document_id),
        "retry_count": queue_item.retry_count if queue_item else 0,
        "max_retries": queue_item.max_retries if queue_item else 0,
    }


@router.post("/worker/customer-sync")
def worker_sync_customers(
    payload: dict = Body(...),
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Sincroniza clientes desde el escritorio (bulk upsert por NIF)."""
    org_id = payload.get("organization_id", "")
    customers_data = payload.get("customers", [])

    if not org_id:
        raise HTTPException(status_code=400, detail="organization_id requerido")

    synced = 0
    for cd in customers_data:
        tax_id = cd.get("tax_id", "").strip()
        if not tax_id:
            continue
        normalized = normalize_tax_id(tax_id)

        existing = db.scalar(
            select(ClientInvoiceCustomer).where(
                ClientInvoiceCustomer.organization_id == org_id,
                ClientInvoiceCustomer.tax_id_normalized == normalized,
            )
        )
        if existing:
            # Actualizar datos fiscales
            for field in ("legal_name", "address", "postal_code", "city",
                         "province", "country", "email", "phone"):
                if field in cd and cd[field]:
                    setattr(existing, field, cd[field])
            if "default_vat_rate" in cd:
                existing.default_vat_rate = Decimal(str(cd["default_vat_rate"]))
            if "desktop_tercero_id" in cd:
                existing.desktop_tercero_id = cd["desktop_tercero_id"]
                existing.pending_desktop_import = False
            if "desktop_subcuenta" in cd:
                existing.desktop_subcuenta = cd["desktop_subcuenta"]
            existing.updated_at = utcnow()
        else:
            cust = ClientInvoiceCustomer(
                organization_id=org_id,
                tax_id=tax_id.upper(),
                tax_id_normalized=normalized,
                legal_name=cd.get("legal_name", ""),
                address=cd.get("address", ""),
                postal_code=cd.get("postal_code", ""),
                city=cd.get("city", ""),
                province=cd.get("province", ""),
                country=cd.get("country", "ES"),
                email=cd.get("email", ""),
                phone=cd.get("phone", ""),
                default_vat_rate=Decimal(str(cd.get("default_vat_rate", "21.00"))),
                desktop_tercero_id=cd.get("desktop_tercero_id"),
                desktop_subcuenta=cd.get("desktop_subcuenta", ""),
                pending_desktop_import=False,
            )
            db.add(cust)
        synced += 1

    db.commit()
    return {"status": "ok", "synced": synced}
