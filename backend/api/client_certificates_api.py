"""Cola central de solicitudes de certificados AEAT y Seguridad Social.

El cliente Flutter solo crea y consulta solicitudes. El certificado privado
nunca se entrega al navegador: un worker interno ejecutara el tramite y
publicara el PDF resultante en ``client_documents``.
"""
from __future__ import annotations

import json
import base64
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.client_certificate_vault import (
    ClientCertificateVaultStorage,
    decrypt_material,
    encrypt_material,
    inspect_pfx,
)
from backend.api.client_models import (
    ClientCertificateRequest,
    ClientCertificateSecret,
    ClientDocument,
)
from backend.api.database import SessionLocal
from backend.api.client_storage import ClientDocumentStorage
from backend.api.feature_flags import require_certificates_enabled
from backend.api.messaging_models import (
    MessagingClient,
    MessagingOrganization,
    MessagingSession,
    new_id,
)
from backend.api.messaging_security import hash_token, is_expired, utcnow
from backend.api.security import require_aapp_worker_key, require_workstation_or_internal


router = APIRouter(
    prefix="/api/v1/messaging/client/certificates",
    tags=["client-certificates"],
)


CERTIFICATE_TYPES = {
    "AEAT_CORRIENTE": {
        "code": "AEAT_CORRIENTE",
        "organization": "AEAT",
        "name": "Estar al corriente de obligaciones tributarias",
        "parameters": [],
    },
    "AEAT_CENSAL": {
        "code": "AEAT_CENSAL",
        "organization": "AEAT",
        "name": "Situacion censal",
        "parameters": [],
    },
    "AEAT_IAE": {
        "code": "AEAT_IAE",
        "organization": "AEAT",
        "name": "Situacion en el IAE",
        "parameters": [],
    },
    "AEAT_CONTRATISTAS": {
        "code": "AEAT_CONTRATISTAS",
        "organization": "AEAT",
        "name": "Contratistas y subcontratistas",
        "parameters": [
            {
                "key": "contracting_party_tax_id",
                "label": "CIF/NIF de la empresa con la que contrata",
                "type": "tax_id",
                "required": True,
            },
            {
                "key": "contracting_party_name",
                "label": "Nombre o razon social de la empresa",
                "type": "text",
                "required": True,
            },
        ],
    },
    "TGSS_CORRIENTE": {
        "code": "TGSS_CORRIENTE",
        "organization": "TGSS",
        "name": "Estar al corriente en la Seguridad Social",
        "parameters": [],
    },
    "TGSS_SUBVENCIONES": {
        "code": "TGSS_SUBVENCIONES",
        "organization": "TGSS",
        "name": "Estar al corriente para subvenciones",
        "parameters": [],
    },
    "TGSS_LICITACION": {
        "code": "TGSS_LICITACION",
        "organization": "TGSS",
        "name": "Estar al corriente para licitacion publica",
        "parameters": [],
    },
    "TGSS_COTIZACION": {
        "code": "TGSS_COTIZACION",
        "organization": "TGSS",
        "name": "Situacion de cotizacion",
        "parameters": [],
    },
    "TGSS_ART42": {
        "code": "TGSS_ART42",
        "organization": "TGSS",
        "name": "Articulo 42 - Subcontratacion",
        "parameters": [],
    },
    "TGSS_SIN_DEUDA_FECHA": {
        "code": "TGSS_SIN_DEUDA_FECHA",
        "organization": "TGSS",
        "name": "Sin deuda a una fecha",
        "parameters": [
            {
                "key": "as_of_date",
                "label": "Fecha del certificado (AAAA-MM-DD)",
                "type": "date",
                "required": True,
            },
        ],
    },
    "TGSS_INFORME_DEUDA": {
        "code": "TGSS_INFORME_DEUDA",
        "organization": "TGSS",
        "name": "Informe de deuda total",
        "parameters": [],
    },
    "TGSS_DETALLE_DEUDA": {
        "code": "TGSS_DETALLE_DEUDA",
        "organization": "TGSS",
        "name": "Informe de detalle de deuda",
        "parameters": [],
    },
}

INTERNAL_OPERATION_TYPES = {
    "DEHU_SYNC": {
        "code": "DEHU_SYNC",
        "organization": "DEHU",
        "name": "Sincronizacion de notificaciones electronicas",
        "parameters": [],
        "internal_only": True,
    },
}
_ALL_REQUEST_TYPES = {**CERTIFICATE_TYPES, **INTERNAL_OPERATION_TYPES}

ACTIVE_STATUSES = {"queued", "processing", "needs_action"}
RETRYABLE_STATUSES = {"needs_action", "failed"}


class CertificateRequestIn(BaseModel):
    certificate_type: str = Field(min_length=3, max_length=50)
    parameters: dict = Field(default_factory=dict)
    idempotency_key: str = Field(default="", max_length=80)


class WorkerResultIn(BaseModel):
    claim_token: str = Field(min_length=16, max_length=64)
    document_id: str | None = Field(default=None, min_length=1, max_length=36)
    result_summary: str = Field(default="", max_length=2000)


class WorkerFailureIn(BaseModel):
    claim_token: str = Field(min_length=16, max_length=64)
    error_code: str = Field(default="worker_error", max_length=60)
    error_message: str = Field(min_length=1, max_length=4000)
    needs_action: bool = False
    retry_after_seconds: int | None = Field(default=None, ge=30, le=86400)


class WorkerMaterialIn(BaseModel):
    request_id: str = Field(min_length=1, max_length=36)
    claim_token: str = Field(min_length=16, max_length=64)


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
    session = db.scalar(select(MessagingSession).where(
        MessagingSession.token_hash == hash_token(token),
    ))
    if not session or session.revoked_at or is_expired(session.expires_at):
        raise HTTPException(status_code=401, detail="Sesion no valida")
    client = db.get(MessagingClient, session.client_id)
    if not client or not client.active:
        raise HTTPException(status_code=403, detail="Cliente inactivo")
    return client


def _serialize(
    item: ClientCertificateRequest,
    *,
    document_status: str | None = None,
) -> dict:
    try:
        parameters = json.loads(item.parameters_json or "{}")
    except (TypeError, ValueError):
        parameters = {}
    catalog = _ALL_REQUEST_TYPES.get(item.certificate_type, {})
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "requester_type": item.requester_type,
        "certificate_type": item.certificate_type,
        "certificate_name": catalog.get("name", item.certificate_type),
        "issuing_organization": catalog.get("organization", ""),
        "parameters": parameters,
        "status": item.status,
        "attempt_count": item.attempt_count,
        "error_code": item.error_code or None,
        "error_message": item.error_message or None,
        "result_summary": item.result_summary or None,
        "document_id": item.document_id,
        "document_status": document_status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
    }


def _secret_status(secret: ClientCertificateSecret | None) -> dict:
    if not secret or not secret.active:
        return {"configured": False, "status": "missing"}
    now = utcnow()
    valid_until = secret.valid_until
    if valid_until and valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=timezone.utc)
    status = "expired" if valid_until and valid_until <= now else "valid"
    return {
        "configured": True,
        "status": status,
        "common_name": secret.common_name,
        "tax_id": secret.tax_id,
        "issuer": secret.issuer,
        "valid_from": secret.valid_from.isoformat() if secret.valid_from else None,
        "valid_until": secret.valid_until.isoformat() if secret.valid_until else None,
        "version": secret.version,
        "updated_at": secret.updated_at.isoformat() if secret.updated_at else None,
    }


def _organization_by_code(db: Session, company_code: str) -> MessagingOrganization:
    org = db.scalar(select(MessagingOrganization).where(
        MessagingOrganization.company_code == company_code.strip(),
    ))
    if not org or not org.active:
        raise HTTPException(status_code=404, detail="Organizacion no encontrada")
    return org


def _validate_request(
    payload: CertificateRequestIn, *, allow_internal: bool = False,
) -> tuple[str, str]:
    certificate_type = payload.certificate_type.strip().upper()
    allowed_types = _ALL_REQUEST_TYPES if allow_internal else CERTIFICATE_TYPES
    if certificate_type not in allowed_types:
        raise HTTPException(status_code=422, detail="Tipo de certificado no soportado")
    parameters = dict(payload.parameters or {})
    catalog = allowed_types[certificate_type]
    if not catalog.get("internal_only"):
        definitions = catalog.get("parameters") or []
        allowed_keys = {definition["key"] for definition in definitions}
        unknown = set(parameters) - allowed_keys
        if unknown:
            raise HTTPException(status_code=422, detail="Parametros no reconocidos")
        cleaned = {}
        for definition in definitions:
            key = definition["key"]
            value = str(parameters.get(key) or "").strip()
            if definition.get("required") and not value:
                raise HTTPException(
                    status_code=422,
                    detail=f"Falta el campo: {definition['label']}",
                )
            if not value:
                continue
            if definition.get("type") == "tax_id":
                value = re.sub(r"[^A-Z0-9]", "", value.upper())
                if not re.fullmatch(r"[A-Z0-9]{8,12}", value):
                    raise HTTPException(status_code=422, detail="CIF/NIF no valido")
            elif definition.get("type") == "date":
                try:
                    parsed = date.fromisoformat(value)
                except ValueError as exc:
                    raise HTTPException(
                        status_code=422, detail="La fecha debe tener formato AAAA-MM-DD",
                    ) from exc
                if parsed > datetime.now(ZoneInfo("Europe/Madrid")).date():
                    raise HTTPException(status_code=422, detail="La fecha no puede ser futura")
            elif len(value) > 200:
                raise HTTPException(status_code=422, detail="Campo demasiado largo")
            cleaned[key] = value
        parameters = cleaned
    serialized = json.dumps(parameters, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > 8000:
        raise HTTPException(status_code=413, detail="Parametros demasiado grandes")
    return certificate_type, serialized


def _create_request(
    db: Session,
    *,
    org: MessagingOrganization,
    payload: CertificateRequestIn,
    requester_type: str,
    requester_id: str,
    allow_internal: bool = False,
) -> ClientCertificateRequest:
    certificate_type, parameters_json = _validate_request(
        payload, allow_internal=allow_internal,
    )
    key = payload.idempotency_key.strip() or new_id()
    existing = db.scalar(select(ClientCertificateRequest).where(
        ClientCertificateRequest.organization_id == org.id,
        ClientCertificateRequest.idempotency_key == key,
    ))
    if existing:
        return existing
    madrid_now = datetime.now(ZoneInfo("Europe/Madrid"))
    madrid_start = madrid_now.replace(hour=0, minute=0, second=0, microsecond=0)
    madrid_end = madrid_start + timedelta(days=1)
    requested_today = db.scalar(select(ClientCertificateRequest).where(
        ClientCertificateRequest.organization_id == org.id,
        ClientCertificateRequest.certificate_type == certificate_type,
        ClientCertificateRequest.created_at >= madrid_start.astimezone(timezone.utc),
        ClientCertificateRequest.created_at < madrid_end.astimezone(timezone.utc),
    ).order_by(ClientCertificateRequest.created_at.desc()).limit(1))
    if requested_today:
        raise HTTPException(
            status_code=409,
            detail="Este certificado ya se ha solicitado hoy. Podras pedir otro manana.",
        )
    active = db.scalar(select(ClientCertificateRequest).where(
        ClientCertificateRequest.organization_id == org.id,
        ClientCertificateRequest.certificate_type == certificate_type,
        ClientCertificateRequest.status.in_(ACTIVE_STATUSES),
    ).order_by(ClientCertificateRequest.created_at.desc()).limit(1))
    if active:
        raise HTTPException(
            status_code=409,
            detail="Ya existe una solicitud activa de este certificado",
        )
    item = ClientCertificateRequest(
        organization_id=org.id,
        requester_type=requester_type,
        requester_id=requester_id,
        certificate_type=certificate_type,
        parameters_json=parameters_json,
        idempotency_key=key,
        status="queued",
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        same_key = db.scalar(select(ClientCertificateRequest).where(
            ClientCertificateRequest.organization_id == org.id,
            ClientCertificateRequest.idempotency_key == key,
        ))
        if same_key:
            return same_key
        raise HTTPException(
            status_code=409,
            detail="Ya existe una solicitud activa de este certificado",
        ) from exc
    db.refresh(item)
    return item


def _retry_request(
    db: Session,
    item: ClientCertificateRequest,
) -> ClientCertificateRequest:
    delayed_retry = item.status == "queued" and item.next_attempt_at is not None
    if item.status not in RETRYABLE_STATUSES and not delayed_retry:
        raise HTTPException(
            status_code=409,
            detail="La solicitud no esta en un estado que permita reintentarla",
        )
    item.status = "queued"
    item.attempt_count = 0
    item.next_attempt_at = None
    item.claimed_at = None
    item.claim_token = ""
    item.error_code = ""
    item.error_message = ""
    item.result_summary = ""
    item.document_id = None
    item.completed_at = None
    item.cancelled_at = None
    item.updated_at = utcnow()
    db.commit()
    db.refresh(item)
    return item


@router.get("/types")
def list_certificate_types(request: Request, db: Session = Depends(_db)):
    client = _authenticated_client(request, db)
    require_certificates_enabled(db, client.organization_id)
    return {"items": list(CERTIFICATE_TYPES.values())}


@router.get("/certificate-status")
def get_client_certificate_status(request: Request, db: Session = Depends(_db)):
    client = _authenticated_client(request, db)
    require_certificates_enabled(db, client.organization_id)
    secret = db.scalar(select(ClientCertificateSecret).where(
        ClientCertificateSecret.organization_id == client.organization_id,
    ))
    return _secret_status(secret)


@router.post("/requests", status_code=201)
def create_client_request(
    payload: CertificateRequestIn,
    request: Request,
    db: Session = Depends(_db),
):
    client = _authenticated_client(request, db)
    org = require_certificates_enabled(db, client.organization_id)
    secret = db.scalar(select(ClientCertificateSecret).where(
        ClientCertificateSecret.organization_id == org.id,
        ClientCertificateSecret.active.is_(True),
    ))
    secret_state = _secret_status(secret)
    if not secret_state["configured"]:
        raise HTTPException(status_code=409, detail="Certificado digital no configurado")
    if secret_state["status"] == "expired":
        raise HTTPException(status_code=409, detail="El certificado digital esta caducado")
    return _serialize(_create_request(
        db, org=org, payload=payload,
        requester_type="client", requester_id=client.id,
    ))


@router.get("/requests")
def list_client_requests(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(_db),
):
    client = _authenticated_client(request, db)
    require_certificates_enabled(db, client.organization_id)
    items = list(db.scalars(select(ClientCertificateRequest).where(
        ClientCertificateRequest.organization_id == client.organization_id,
        ClientCertificateRequest.requester_type == "client",
    ).order_by(ClientCertificateRequest.created_at.desc()).limit(limit)).all())
    return {"items": [_serialize(item) for item in items]}


@router.get("/requests/{request_id}")
def get_client_request(
    request_id: str, request: Request, db: Session = Depends(_db),
):
    client = _authenticated_client(request, db)
    require_certificates_enabled(db, client.organization_id)
    item = db.get(ClientCertificateRequest, request_id)
    if (
        not item
        or item.organization_id != client.organization_id
        or item.requester_type != "client"
    ):
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return _serialize(item)


@router.post("/requests/{request_id}/cancel")
def cancel_client_request(
    request_id: str, request: Request, db: Session = Depends(_db),
):
    client = _authenticated_client(request, db)
    require_certificates_enabled(db, client.organization_id)
    item = db.get(ClientCertificateRequest, request_id)
    if (
        not item
        or item.organization_id != client.organization_id
        or item.requester_type != "client"
    ):
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if item.status != "queued":
        raise HTTPException(status_code=409, detail="La solicitud ya no se puede cancelar")
    item.status = "cancelled"
    item.cancelled_at = utcnow()
    item.updated_at = utcnow()
    db.commit()
    return _serialize(item)


@router.post("/requests/{request_id}/retry")
def retry_client_request(
    request_id: str, request: Request, db: Session = Depends(_db),
):
    client = _authenticated_client(request, db)
    require_certificates_enabled(db, client.organization_id)
    item = db.get(ClientCertificateRequest, request_id)
    if (
        not item
        or item.organization_id != client.organization_id
        or item.requester_type != "client"
    ):
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return _serialize(_retry_request(db, item))


@router.post("/internal/requests", status_code=201)
def create_internal_request(
    company_code: str,
    payload: CertificateRequestIn,
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    org = _organization_by_code(db, company_code)
    secret = db.scalar(select(ClientCertificateSecret).where(
        ClientCertificateSecret.organization_id == org.id,
        ClientCertificateSecret.active.is_(True),
    ))
    secret_state = _secret_status(secret)
    if not secret_state["configured"]:
        raise HTTPException(status_code=409, detail="Certificado digital no configurado")
    if secret_state["status"] == "expired":
        raise HTTPException(status_code=409, detail="El certificado digital esta caducado")
    return _serialize(_create_request(
        db, org=org, payload=payload,
        requester_type="desktop", requester_id="desktop",
        allow_internal=True,
    ))


@router.get("/internal/requests")
def list_internal_requests(
    company_code: str = "",
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    statement = (
        select(
            ClientCertificateRequest,
            MessagingOrganization,
            ClientDocument.status,
            ClientDocument.fiscal_year,
            ClientDocument.document_date,
        )
        .join(
            MessagingOrganization,
            MessagingOrganization.id == ClientCertificateRequest.organization_id,
        )
        .outerjoin(
            ClientDocument,
            ClientDocument.id == ClientCertificateRequest.document_id,
        )
        .order_by(ClientCertificateRequest.created_at.desc())
        .limit(limit)
    )
    if company_code.strip():
        statement = statement.where(
            MessagingOrganization.company_code == company_code.strip(),
        )
    items = []
    for (
        request_item,
        organization,
        document_status,
        document_fiscal_year,
        document_date,
    ) in db.execute(statement).all():
        serialized = _serialize(request_item, document_status=document_status)
        serialized["company_code"] = organization.company_code
        serialized["company_name"] = organization.name
        serialized["document_fiscal_year"] = document_fiscal_year
        serialized["document_date"] = (
            document_date.isoformat() if document_date else None
        )
        items.append(serialized)
    return {"items": items}


@router.post("/internal/requests/{request_id}/retry")
def retry_internal_request(
    request_id: str,
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    item = db.get(ClientCertificateRequest, request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return _serialize(_retry_request(db, item))


@router.delete("/internal/requests/{request_id}")
def delete_internal_request(
    request_id: str,
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Elimina intentos sin documento que no forman parte del historial util."""
    item = db.get(ClientCertificateRequest, request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if item.document_id or item.status not in {"failed", "cancelled"}:
        raise HTTPException(
            status_code=409,
            detail="Solo se pueden eliminar solicitudes fallidas o canceladas sin documento",
        )
    db.delete(item)
    db.commit()
    return {"deleted": True, "id": request_id}


@router.get("/internal/requests/{request_id}/document")
def download_internal_request_document(
    request_id: str,
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    item = db.get(ClientCertificateRequest, request_id)
    if not item or not item.document_id:
        raise HTTPException(status_code=404, detail="La solicitud no tiene documento")
    document = db.get(ClientDocument, item.document_id)
    if not document or document.organization_id != item.organization_id:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    if document.status == "withdrawn":
        raise HTTPException(status_code=410, detail="Documento retirado")
    content = ClientDocumentStorage().get(document.blob_key)
    return Response(
        content=content,
        media_type=document.content_type or "application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{document.file_name}"',
            "Content-Length": str(len(content)),
        },
    )


@router.get("/internal/certificate-status")
def get_internal_certificate_status(
    company_code: str,
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    org = _organization_by_code(db, company_code)
    secret = db.scalar(select(ClientCertificateSecret).where(
        ClientCertificateSecret.organization_id == org.id,
    ))
    return _secret_status(secret)


@router.post("/internal/certificate")
async def upload_internal_certificate(
    company_code: str = Form(...),
    password: str = Form(default=""),
    file: UploadFile = File(...),
    db: Session = Depends(_db),
    actor: str = Depends(require_workstation_or_internal),
):
    org = _organization_by_code(db, company_code)
    content = await file.read(2 * 1024 * 1024 + 1)
    try:
        metadata = inspect_pfx(content, password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    existing = db.scalar(select(ClientCertificateSecret).where(
        ClientCertificateSecret.organization_id == org.id,
    ))
    version = int(existing.version or 0) + 1 if existing else 1
    encrypted = encrypt_material(content, password, org.id)
    storage = ClientCertificateVaultStorage()
    blob_key = storage.put(encrypted, org.id)
    old_blob_key = existing.encrypted_blob_key if existing else ""
    safe_file_name = re.sub(
        r"[^A-Za-z0-9._-]", "_", (file.filename or "certificado.pfx"),
    )[:255]
    secret = existing or ClientCertificateSecret(organization_id=org.id)
    secret.encrypted_blob_key = blob_key
    secret.pfx_sha256 = metadata.pfx_sha256
    secret.file_name = safe_file_name or "certificado.pfx"
    secret.common_name = metadata.common_name
    secret.tax_id = metadata.tax_id
    secret.issuer = metadata.issuer
    secret.serial_number = metadata.serial_number
    secret.valid_from = metadata.valid_from
    secret.valid_until = metadata.valid_until
    secret.version = version
    secret.active = True
    secret.uploaded_by = actor
    secret.updated_at = utcnow()
    if not existing:
        db.add(secret)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(blob_key)
        raise
    if old_blob_key and old_blob_key != blob_key:
        try:
            storage.delete(old_blob_key)
        except Exception:
            pass
    state = _secret_status(secret)
    normalized_org_tax = re.sub(r"[^0-9A-Z]", "", (org.tax_id or "").upper())
    state["tax_id_warning"] = bool(
        normalized_org_tax and metadata.tax_id and normalized_org_tax != metadata.tax_id
    )
    return state


@router.delete("/internal/certificate")
def delete_internal_certificate(
    company_code: str,
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    org = _organization_by_code(db, company_code)
    secret = db.scalar(select(ClientCertificateSecret).where(
        ClientCertificateSecret.organization_id == org.id,
    ))
    if not secret:
        return {"ok": True}
    blob_key = secret.encrypted_blob_key
    db.delete(secret)
    db.commit()
    try:
        ClientCertificateVaultStorage().delete(blob_key)
    except Exception:
        pass
    return {"ok": True}


@router.post("/internal/worker/claim")
def claim_next_request(
    db: Session = Depends(_db),
    _auth: str = Depends(require_aapp_worker_key),
):
    now = utcnow()
    stale_before = now - timedelta(minutes=15)
    item = db.scalar(
        select(ClientCertificateRequest).where(
            or_(
                and_(
                    ClientCertificateRequest.status == "queued",
                    (
                        ClientCertificateRequest.next_attempt_at.is_(None)
                        | (ClientCertificateRequest.next_attempt_at <= now)
                    ),
                ),
                and_(
                    ClientCertificateRequest.status == "processing",
                    ClientCertificateRequest.claimed_at < stale_before,
                ),
            ),
        ).order_by(ClientCertificateRequest.created_at).with_for_update(
            skip_locked=True,
        ).limit(1)
    )
    if not item:
        return {"item": None}
    item.status = "processing"
    item.claimed_at = now
    item.claim_token = secrets.token_hex(24)
    item.attempt_count = int(item.attempt_count or 0) + 1
    item.updated_at = now
    db.commit()
    result = _serialize(item)
    result["claim_token"] = item.claim_token
    return {"item": result}


@router.post("/internal/worker/certificate-material")
def get_worker_certificate_material(
    payload: WorkerMaterialIn,
    db: Session = Depends(_db),
    _auth: str = Depends(require_aapp_worker_key),
):
    item = _claimed_request(db, payload.request_id, payload.claim_token)
    secret = db.scalar(select(ClientCertificateSecret).where(
        ClientCertificateSecret.organization_id == item.organization_id,
        ClientCertificateSecret.active.is_(True),
    ))
    if not secret:
        raise HTTPException(status_code=409, detail="Certificado digital no configurado")
    try:
        encrypted = ClientCertificateVaultStorage().get(secret.encrypted_blob_key)
        pfx, password = decrypt_material(encrypted, item.organization_id)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="No se pudo obtener el certificado") from exc
    secret.last_used_at = utcnow()
    secret.updated_at = utcnow()
    db.commit()
    return {
        "file_name": secret.file_name,
        "pfx_base64": base64.b64encode(pfx).decode("ascii"),
        "password": password,
        "valid_until": secret.valid_until.isoformat() if secret.valid_until else None,
    }


def _claimed_request(
    db: Session, request_id: str, claim_token: str,
) -> ClientCertificateRequest:
    item = db.get(ClientCertificateRequest, request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if item.status != "processing" or not secrets.compare_digest(
        item.claim_token or "", claim_token,
    ):
        raise HTTPException(status_code=409, detail="Claim del worker no valido")
    return item


@router.post("/internal/worker/requests/{request_id}/complete")
def complete_request(
    request_id: str,
    payload: WorkerResultIn,
    db: Session = Depends(_db),
    _auth: str = Depends(require_aapp_worker_key),
):
    item = _claimed_request(db, request_id, payload.claim_token)
    document = db.get(ClientDocument, payload.document_id) if payload.document_id else None
    if payload.document_id and (
        not document or document.organization_id != item.organization_id
    ):
        raise HTTPException(status_code=422, detail="Documento resultante no valido")
    item.status = "completed"
    item.document_id = document.id if document else None
    item.result_summary = payload.result_summary
    item.error_code = ""
    item.error_message = ""
    item.claim_token = ""
    item.completed_at = utcnow()
    item.updated_at = utcnow()
    db.commit()
    return _serialize(item)


@router.post("/internal/worker/requests/{request_id}/fail")
def fail_request(
    request_id: str,
    payload: WorkerFailureIn,
    db: Session = Depends(_db),
    _auth: str = Depends(require_aapp_worker_key),
):
    item = _claimed_request(db, request_id, payload.claim_token)
    item.error_code = payload.error_code
    item.error_message = payload.error_message
    item.claim_token = ""
    if payload.needs_action:
        item.status = "needs_action"
        item.next_attempt_at = None
    elif payload.retry_after_seconds is not None:
        item.status = "queued"
        item.next_attempt_at = utcnow() + timedelta(seconds=payload.retry_after_seconds)
    else:
        item.status = "failed"
        item.next_attempt_at = None
    item.updated_at = utcnow()
    db.commit()
    return _serialize(item)
