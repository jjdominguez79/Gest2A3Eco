"""API de documentos del area privada del cliente.

Endpoints internos para publicacion y gestion.
Endpoints de cliente para listado, descarga y lectura.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.client_models import ClientDocument, ClientDocumentRead
from backend.api.client_storage import ClientDocumentStorage
from backend.api.database import SessionLocal
from backend.api.messaging_models import (
    MessagingClient,
    MessagingOrganization,
    MessagingSession,
)
from backend.api.messaging_security import hash_token, is_expired, utcnow
from backend.api.security import require_workstation_or_internal

router = APIRouter(prefix="/api/v1/messaging/client/documents", tags=["client-documents"])

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


def _doc_to_dict(doc: ClientDocument, is_read: bool = False) -> dict:
    result = {
        "id": doc.id,
        "document_type": doc.document_type,
        "source_system": doc.source_system,
        "display_name": doc.display_name,
        "description": doc.description or None,
        "document_date": doc.document_date.isoformat() if doc.document_date else None,
        "fiscal_year": doc.fiscal_year,
        "amount": str(doc.amount) if doc.amount is not None else None,
        "currency": doc.currency,
        "file_name": doc.file_name,
        "content_type": doc.content_type,
        "file_size": doc.file_size,
        "status": doc.status,
        "replaced_by_id": doc.replaced_by_id,
        "withdrawal_reason": doc.withdrawal_reason or None,
        "published_at": doc.published_at.isoformat() if doc.published_at else None,
        "is_read": is_read,
    }
    return {k: v for k, v in result.items() if v is not None}


# ===== ENDPOINTS INTERNOS (workstation / API key) =====


@router.post("/internal/publish")
async def publish_document(
    file: UploadFile = File(...),
    organization_id: str = Form(...),
    document_type: str = Form(...),
    source_system: str = Form(...),
    source_id: str = Form(...),
    source_version: int = Form(1),
    display_name: str = Form(...),
    description: str = Form(""),
    document_date: str = Form(""),
    fiscal_year: int = Form(0),
    amount: str = Form(""),
    currency: str = Form("EUR"),
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Publica un documento en el area del cliente. Idempotente por source."""
    # Verificar organizacion
    org = db.get(MessagingOrganization, organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organizacion no encontrada")

    # Idempotencia: comprobar si ya existe
    existing = db.scalar(
        select(ClientDocument).where(
            ClientDocument.organization_id == organization_id,
            ClientDocument.source_system == source_system,
            ClientDocument.source_id == source_id,
            ClientDocument.source_version == source_version,
        )
    )
    if existing:
        return _doc_to_dict(existing)

    # Leer y almacenar archivo
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacio")

    storage = _get_storage()
    sha256 = storage.compute_sha256(content)
    blob_key = storage.put(content, file.filename or "documento.pdf",
                           organization_id=organization_id)

    # Parsear fecha y cantidad
    parsed_date = None
    if document_date:
        try:
            parsed_date = datetime.fromisoformat(document_date)
            if parsed_date.tzinfo is None:
                parsed_date = parsed_date.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    parsed_amount = None
    if amount:
        try:
            parsed_amount = Decimal(amount)
        except InvalidOperation:
            pass

    doc = ClientDocument(
        organization_id=organization_id,
        document_type=document_type,
        source_system=source_system,
        source_id=source_id,
        source_version=source_version,
        display_name=display_name,
        description=description,
        document_date=parsed_date,
        fiscal_year=fiscal_year,
        amount=parsed_amount,
        currency=currency,
        file_name=file.filename or "documento.pdf",
        content_type=file.content_type or "application/pdf",
        file_size=len(content),
        sha256=sha256,
        blob_key=blob_key,
        status="published",
        published_at=utcnow(),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _doc_to_dict(doc)


@router.post("/internal/{document_id}/replace")
async def replace_document(
    document_id: str,
    file: UploadFile = File(...),
    display_name: str = Form(""),
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Sustituye un documento por una nueva version."""
    old_doc = db.get(ClientDocument, document_id)
    if not old_doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacio")

    storage = _get_storage()
    sha256 = storage.compute_sha256(content)
    blob_key = storage.put(content, file.filename or "documento.pdf",
                           organization_id=old_doc.organization_id)

    new_doc = ClientDocument(
        organization_id=old_doc.organization_id,
        document_type=old_doc.document_type,
        source_system=old_doc.source_system,
        source_id=old_doc.source_id,
        source_version=old_doc.source_version + 1,
        display_name=display_name or old_doc.display_name,
        description=old_doc.description,
        document_date=old_doc.document_date,
        fiscal_year=old_doc.fiscal_year,
        amount=old_doc.amount,
        currency=old_doc.currency,
        file_name=file.filename or old_doc.file_name,
        content_type=file.content_type or old_doc.content_type,
        file_size=len(content),
        sha256=sha256,
        blob_key=blob_key,
        status="published",
        published_at=utcnow(),
    )
    db.add(new_doc)
    db.flush()

    old_doc.status = "replaced"
    old_doc.replaced_by_id = new_doc.id
    old_doc.updated_at = utcnow()
    db.commit()
    db.refresh(new_doc)
    return _doc_to_dict(new_doc)


@router.post("/internal/{document_id}/withdraw")
def withdraw_document(
    document_id: str,
    reason: str = Form(""),
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Retira un documento (deja de estar disponible para descarga)."""
    doc = db.get(ClientDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    if doc.status == "withdrawn":
        return _doc_to_dict(doc)

    doc.status = "withdrawn"
    doc.withdrawal_reason = reason
    doc.withdrawn_at = utcnow()
    doc.updated_at = utcnow()
    db.commit()
    db.refresh(doc)
    return _doc_to_dict(doc)


# ===== ENDPOINTS DE CLIENTE =====


@router.get("/")
def list_documents(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    document_type: str = Query(""),
    fiscal_year: int = Query(0),
    db: Session = Depends(_db),
):
    """Lista documentos del area del cliente, paginados y filtrables."""
    client = _authenticated_client(request, db)

    query = select(ClientDocument).where(
        ClientDocument.organization_id == client.organization_id,
    )
    if document_type:
        query = query.where(ClientDocument.document_type == document_type)
    if fiscal_year:
        query = query.where(ClientDocument.fiscal_year == fiscal_year)

    query = query.order_by(ClientDocument.document_date.desc().nullslast())
    total = db.scalar(
        select(func.count()).select_from(query.subquery())
    )
    docs = db.scalars(query.offset(offset).limit(limit)).all()

    # Obtener estado de lectura para este cliente
    read_doc_ids = set()
    if docs:
        doc_ids = [d.id for d in docs]
        reads = db.scalars(
            select(ClientDocumentRead.document_id).where(
                ClientDocumentRead.document_id.in_(doc_ids),
                ClientDocumentRead.client_id == client.id,
            )
        ).all()
        read_doc_ids = set(reads)

    return {
        "items": [_doc_to_dict(d, is_read=d.id in read_doc_ids) for d in docs],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/{document_id}")
def get_document(
    document_id: str,
    request: Request,
    db: Session = Depends(_db),
):
    """Detalle de un documento."""
    client = _authenticated_client(request, db)
    doc = db.get(ClientDocument, document_id)
    if not doc or doc.organization_id != client.organization_id:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    is_read = db.scalar(
        select(ClientDocumentRead.id).where(
            ClientDocumentRead.document_id == document_id,
            ClientDocumentRead.client_id == client.id,
        )
    ) is not None

    return _doc_to_dict(doc, is_read=is_read)


@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    request: Request,
    db: Session = Depends(_db),
):
    """Descarga el archivo de un documento. Registra la lectura."""
    client = _authenticated_client(request, db)
    doc = db.get(ClientDocument, document_id)
    if not doc or doc.organization_id != client.organization_id:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    if doc.status == "withdrawn":
        raise HTTPException(status_code=410, detail="Documento retirado")

    # Descargar del blob
    storage = _get_storage()
    content = storage.get(doc.blob_key)

    # Registrar lectura (idempotente)
    existing_read = db.scalar(
        select(ClientDocumentRead).where(
            ClientDocumentRead.document_id == document_id,
            ClientDocumentRead.client_id == client.id,
        )
    )
    if not existing_read:
        read_record = ClientDocumentRead(
            document_id=document_id,
            client_id=client.id,
        )
        db.add(read_record)
        db.commit()

    return Response(
        content=content,
        media_type=doc.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{doc.file_name}"',
            "Content-Length": str(len(content)),
        },
    )


@router.post("/{document_id}/read")
def mark_as_read(
    document_id: str,
    request: Request,
    db: Session = Depends(_db),
):
    """Marca un documento como leido por el cliente."""
    client = _authenticated_client(request, db)
    doc = db.get(ClientDocument, document_id)
    if not doc or doc.organization_id != client.organization_id:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    existing = db.scalar(
        select(ClientDocumentRead).where(
            ClientDocumentRead.document_id == document_id,
            ClientDocumentRead.client_id == client.id,
        )
    )
    if not existing:
        read_record = ClientDocumentRead(
            document_id=document_id,
            client_id=client.id,
        )
        db.add(read_record)
        db.commit()

    return {"status": "ok"}
