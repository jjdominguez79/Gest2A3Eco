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
from html import escape
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
    ClientDehuNotification,
    ClientDehuMailboxConfig,
    ClientDehuSyncBatch,
    ClientDehuSeenReference,
    ClientDocument,
)
from backend.api import messaging_mail
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
from backend.api.security import (
    require_aapp_worker_claim_protocol,
    require_aapp_worker_key,
    require_workstation_or_internal,
)
from utils.estados_dehu import es_pendiente_dehu, normalizar_estado_dehu


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

ACTIVE_STATUSES = {"queued", "processing", "needs_action", "awaiting_issuance"}
RETRYABLE_STATUSES = {"needs_action", "failed"}
CLIENT_REMOVED_CODE = "client_removed"


class CertificateRequestIn(BaseModel):
    certificate_type: str = Field(min_length=3, max_length=50)
    parameters: dict = Field(default_factory=dict)
    idempotency_key: str = Field(default="", max_length=80)


class CertificateRetryIn(BaseModel):
    parameters: dict | None = None


class WorkerResultIn(BaseModel):
    claim_token: str = Field(min_length=16, max_length=64)
    document_id: str | None = Field(default=None, min_length=1, max_length=36)
    result_summary: str = Field(default="", max_length=2000)
    certificate_result: str = Field(default="", pattern="^(|POSITIVO|NEGATIVO)$")


class WorkerPendingIssuanceIn(BaseModel):
    claim_token: str = Field(min_length=16, max_length=64)
    receipt_document_id: str | None = Field(default=None, min_length=1, max_length=36)
    external_reference: str = Field(default="", max_length=60)
    requires_review: bool = False
    message: str = Field(default="La AEAT sigue tramitando el certificado.", max_length=2000)


class ReclassifyReceiptIn(BaseModel):
    document_id: str = Field(min_length=1, max_length=36)
    expected_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    external_reference: str = Field(pattern=r"^[A-Z0-9][A-Z0-9/\-]{5,59}$")


class WorkerFailureIn(BaseModel):
    claim_token: str = Field(min_length=16, max_length=64)
    error_code: str = Field(default="worker_error", max_length=60)
    error_message: str = Field(min_length=1, max_length=4000)
    needs_action: bool = False
    retry_after_seconds: int | None = Field(default=None, ge=30, le=86400)


class WorkerMaterialIn(BaseModel):
    request_id: str = Field(min_length=1, max_length=36)
    claim_token: str = Field(min_length=16, max_length=64)


class DehuNotificationIn(BaseModel):
    reference: str = Field(min_length=1, max_length=300)
    mailbox_id: str = Field(default="", max_length=100)
    subject: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=4000)
    issuing_body: str = Field(default="", max_length=500)
    issuing_body_source: str = Field(default="", max_length=500)
    action_type: str = Field(default="", max_length=120)
    holder_tax_id: str = Field(default="", max_length=30)
    holder_name: str = Field(default="", max_length=300)
    available_date: str = Field(default="", max_length=32)
    expiration_date: str = Field(default="", max_length=32)
    status: str = Field(default="PENDIENTE", max_length=30)
    source_endpoint: str = Field(default="", max_length=200)
    metadata: dict = Field(default_factory=dict)
    document_id: str | None = Field(default=None, min_length=1, max_length=36)


class WorkerDehuNotificationsIn(BaseModel):
    claim_token: str = Field(min_length=16, max_length=64)
    notifications: list[DehuNotificationIn] = Field(default_factory=list, max_length=1000)


class DehuMailboxConfigIn(BaseModel):
    mailbox_id: str = Field(default="", max_length=100)
    mailbox_name: str = Field(default="DEHu", max_length=300)
    active: bool = True
    periodicity: str = Field(default="MANUAL", max_length=20)
    notification_email: str = Field(default="", max_length=254)


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
        "dehu_batch_id": item.dehu_batch_id,
        "certificate_name": catalog.get("name", item.certificate_type),
        "issuing_organization": catalog.get("organization", ""),
        "parameters": parameters,
        "status": item.status,
        "attempt_count": item.attempt_count,
        "error_code": item.error_code or None,
        "error_message": item.error_message or None,
        "result_summary": item.result_summary or None,
        "external_reference": item.external_reference or None,
        "certificate_result": item.certificate_result or None,
        "receipt_document_id": item.receipt_document_id,
        "submitted_at": item.submitted_at.isoformat() if item.submitted_at else None,
        "last_checked_at": item.last_checked_at.isoformat() if item.last_checked_at else None,
        "next_attempt_at": item.next_attempt_at.isoformat() if item.next_attempt_at else None,
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
    valid_from = secret.valid_from
    if valid_from and valid_from.tzinfo is None:
        valid_from = valid_from.replace(tzinfo=timezone.utc)
    status = (
        "expired" if valid_until and valid_until <= now else
        "not_yet_valid" if valid_from and valid_from > now else
        "valid"
    )
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


def _serialize_dehu_notification(
    item: ClientDehuNotification,
    organization: MessagingOrganization | None = None,
) -> dict:
    try:
        metadata = json.loads(item.metadata_json or "{}")
    except (TypeError, ValueError):
        metadata = {}
    result = {
        "id": item.id,
        "organization_id": item.organization_id,
        "request_id": item.request_id,
        "mailbox_id": item.mailbox_id,
        "reference": item.external_reference,
        "subject": item.subject,
        "description": item.description,
        "issuing_body": item.issuing_body,
        "issuing_body_source": item.issuing_body_source,
        "action_type": item.action_type,
        "holder_tax_id": item.holder_tax_id,
        "holder_name": item.holder_name,
        "available_date": item.available_date,
        "expiration_date": item.expiration_date,
        "status": item.status,
        "source_endpoint": item.source_endpoint,
        "metadata": metadata,
        "document_id": item.document_id,
        "first_seen_at": item.first_seen_at.isoformat() if item.first_seen_at else None,
        "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
    }
    if organization is not None:
        result["company_code"] = organization.company_code
        result["company_name"] = organization.name
    return result


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
    if certificate_type in CERTIFICATE_TYPES:
        madrid_now = datetime.now(ZoneInfo("Europe/Madrid"))
        madrid_start = madrid_now.replace(hour=0, minute=0, second=0, microsecond=0)
        madrid_end = madrid_start + timedelta(days=1)
        requested_today = db.scalar(select(ClientCertificateRequest).where(
            ClientCertificateRequest.organization_id == org.id,
            ClientCertificateRequest.certificate_type == certificate_type,
            ClientCertificateRequest.status != "cancelled",
            ClientCertificateRequest.created_at >= madrid_start.astimezone(timezone.utc),
            ClientCertificateRequest.created_at < madrid_end.astimezone(timezone.utc),
        ).order_by(ClientCertificateRequest.created_at.desc()).limit(1))
        if requested_today:
            raise HTTPException(
                status_code=409,
                detail=("Este certificado ya se ha solicitado hoy. Puedes reintentar "
                        "la solicitud fallida o eliminarla para pedir otra."),
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
    *,
    parameters: dict | None = None,
    allow_internal: bool = False,
) -> ClientCertificateRequest:
    delayed_retry = item.status in {"queued", "awaiting_issuance"} and item.next_attempt_at is not None
    if item.status not in RETRYABLE_STATUSES and not delayed_retry:
        raise HTTPException(
            status_code=409,
            detail="La solicitud no esta en un estado que permita reintentarla",
        )
    if parameters is not None:
        if item.submitted_at or item.receipt_document_id or item.document_id:
            raise HTTPException(
                status_code=409,
                detail="No se pueden cambiar los datos de una solicitud ya presentada",
            )
        _, item.parameters_json = _validate_request(
            CertificateRequestIn(
                certificate_type=item.certificate_type, parameters=parameters,
            ),
            allow_internal=allow_internal,
        )
    item.status = "awaiting_issuance" if item.submitted_at else "queued"
    item.attempt_count = 0
    item.next_attempt_at = utcnow() if item.submitted_at else None
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
    org = db.get(MessagingOrganization, client.organization_id)
    if not org or not org.active:
        raise HTTPException(status_code=404, detail="Organizacion no encontrada")
    secret = db.scalar(select(ClientCertificateSecret).where(
        ClientCertificateSecret.organization_id == client.organization_id,
    ))
    state = _secret_status(secret)
    return {key: state[key] for key in (
        "configured", "status", "common_name", "issuer", "valid_from",
        "valid_until", "updated_at",
    ) if key in state}


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
    if secret_state["status"] != "valid":
        raise HTTPException(status_code=409, detail="El certificado digital no esta en vigor")
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
        ClientCertificateRequest.error_code != CLIENT_REMOVED_CODE,
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
    if item.status != "queued" or item.submitted_at:
        raise HTTPException(status_code=409, detail="La solicitud ya no se puede cancelar")
    item.status = "cancelled"
    item.cancelled_at = utcnow()
    item.updated_at = utcnow()
    db.commit()
    return _serialize(item)


@router.post("/requests/{request_id}/retry")
def retry_client_request(
    request_id: str, request: Request, payload: CertificateRetryIn | None = None,
    db: Session = Depends(_db),
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
    return _serialize(_retry_request(
        db, item, parameters=payload.parameters if payload else None,
    ))


@router.delete("/requests/{request_id}")
def delete_client_request(
    request_id: str, request: Request, db: Session = Depends(_db),
):
    """Retira la solicitud del cliente sin borrar el historial ni su PDF."""
    client = _authenticated_client(request, db)
    require_certificates_enabled(db, client.organization_id)
    # Comparte el bloqueo de fila con el claim: no se retira un tramite
    # que el worker haya empezado a ejecutar mientras se pulsa Eliminar.
    item = db.scalar(select(ClientCertificateRequest).where(
        ClientCertificateRequest.id == request_id,
        ClientCertificateRequest.organization_id == client.organization_id,
        ClientCertificateRequest.requester_type == "client",
    ).with_for_update())
    if not item:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if item.status == "processing" or item.submitted_at and item.status != "completed":
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar una solicitud en tramitacion o pendiente de emision.",
        )
    item.status = "cancelled"
    item.error_code = CLIENT_REMOVED_CODE
    item.cancelled_at = utcnow()
    item.next_attempt_at = None
    item.claim_token = ""
    item.updated_at = utcnow()
    db.commit()
    return {"deleted": True, "id": request_id}


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
    if secret_state["status"] != "valid":
        raise HTTPException(status_code=409, detail="El certificado digital no esta en vigor")
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
    payload: CertificateRetryIn | None = None,
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    item = db.get(ClientCertificateRequest, request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return _serialize(_retry_request(
        db, item, parameters=payload.parameters if payload else None,
        allow_internal=True,
    ))


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
    if item.document_id or item.receipt_document_id or item.submitted_at or item.status not in {"failed", "cancelled"}:
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
    kind: str = Query(default="certificate", pattern="^(certificate|receipt)$"),
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    item = db.get(ClientCertificateRequest, request_id)
    documento_id = (item.receipt_document_id if kind == "receipt" else item.document_id) if item else None
    if not item or not documento_id:
        raise HTTPException(status_code=404, detail="La solicitud no tiene documento")
    document = db.get(ClientDocument, documento_id)
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


_DEHU_PERIODICITIES = {"MANUAL", "DIARIA", "SEMANAL", "QUINCENAL", "MENSUAL"}


def _serialize_dehu_mailbox(item: ClientDehuMailboxConfig, org=None) -> dict:
    return {
        "organization_id": item.organization_id,
        "company_code": getattr(org, "company_code", ""),
        "company_name": getattr(org, "name", ""),
        "mailbox_id": item.mailbox_id,
        "mailbox_name": item.mailbox_name,
        "active": item.active,
        "periodicity": item.periodicity,
        "notification_email": item.notification_email,
        "next_sync_at": item.next_sync_at.isoformat() if item.next_sync_at else None,
        "last_enqueued_at": (
            item.last_enqueued_at.isoformat() if item.last_enqueued_at else None
        ),
        "last_request_id": item.last_request_id,
    }


def _next_dehu_sync(now: datetime, periodicity: str) -> datetime | None:
    days = {"DIARIA": 1, "SEMANAL": 7, "QUINCENAL": 15, "MENSUAL": 30}
    interval = days.get(periodicity)
    return now + timedelta(days=interval) if interval else None


@router.put("/internal/dehu-mailboxes/{company_code}")
def upsert_internal_dehu_mailbox(
    company_code: str,
    payload: DehuMailboxConfigIn,
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Replica en Azure la programacion necesaria para consultar DEHu sin escritorio."""
    org = _organization_by_code(db, company_code)
    periodicity = payload.periodicity.strip().upper()
    if periodicity not in _DEHU_PERIODICITIES:
        raise HTTPException(status_code=422, detail="Periodicidad DEHu no valida")
    email = payload.notification_email.strip().lower()
    automatic = payload.active and periodicity != "MANUAL"
    if email and "@" not in email:
        raise HTTPException(
            status_code=422,
            detail="El email de aviso DEHu no es valido",
        )
    item = db.get(ClientDehuMailboxConfig, org.id)
    now = utcnow()
    if item is None:
        item = ClientDehuMailboxConfig(organization_id=org.id)
        db.add(item)
    schedule_changed = (
        item.periodicity != periodicity or item.active != payload.active
    )
    item.mailbox_id = payload.mailbox_id.strip()
    item.mailbox_name = payload.mailbox_name.strip() or "DEHu"
    item.active = payload.active
    item.periodicity = periodicity
    item.notification_email = email
    if not automatic:
        item.next_sync_at = None
    elif schedule_changed or item.next_sync_at is None:
        item.next_sync_at = now
    item.updated_at = now
    db.commit()
    return _serialize_dehu_mailbox(item, org)


@router.get("/internal/dehu-mailboxes")
def list_internal_dehu_mailboxes(
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    rows = db.execute(
        select(ClientDehuMailboxConfig, MessagingOrganization)
        .join(MessagingOrganization, MessagingOrganization.id == ClientDehuMailboxConfig.organization_id)
        .order_by(MessagingOrganization.name)
    ).all()
    return {"items": [_serialize_dehu_mailbox(item, org) for item, org in rows]}


@router.delete("/internal/dehu-mailboxes/{company_code}")
def delete_internal_dehu_mailbox(
    company_code: str,
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    org = _organization_by_code(db, company_code)
    item = db.get(ClientDehuMailboxConfig, org.id)
    if item:
        db.delete(item)
        db.commit()
    return {"deleted": bool(item)}


def _enqueue_due_dehu_mailboxes(db: Session, now: datetime) -> None:
    due = db.execute(
        select(ClientDehuMailboxConfig, MessagingOrganization)
        .join(MessagingOrganization, MessagingOrganization.id == ClientDehuMailboxConfig.organization_id)
        .where(
            ClientDehuMailboxConfig.active.is_(True),
            ClientDehuMailboxConfig.periodicity != "MANUAL",
            ClientDehuMailboxConfig.next_sync_at.is_not(None),
            ClientDehuMailboxConfig.next_sync_at <= now,
            MessagingOrganization.active.is_(True),
        )
        .with_for_update(skip_locked=True)
    ).all()
    by_email: dict[str, list[tuple[ClientDehuMailboxConfig, MessagingOrganization]]] = {}
    for config, org in due:
        by_email.setdefault(config.notification_email, []).append((config, org))
    for email, mailboxes in by_email.items():
        batch = ClientDehuSyncBatch(
            notification_email=email,
            total_mailboxes=len(mailboxes),
            status="running",
        )
        db.add(batch)
        db.flush()
        for config, org in mailboxes:
            parameters = {
                "company_code": org.company_code,
                "tax_id": org.tax_id or "",
                "mailbox_id": config.mailbox_id,
                "mailbox_name": config.mailbox_name,
                "download_mode": "SOLO_DETECTAR",
                "automatic": True,
            }
            request_item = ClientCertificateRequest(
                organization_id=org.id,
                requester_type="staff",
                requester_id="dehu-scheduler",
                certificate_type="DEHU_SYNC",
                dehu_batch_id=batch.id,
                parameters_json=json.dumps(parameters, ensure_ascii=False, separators=(",", ":")),
                idempotency_key=f"auto-dehu-{batch.id}",
                status="queued",
            )
            db.add(request_item)
            db.flush()
            config.last_request_id = request_item.id
            config.last_enqueued_at = now
            config.next_sync_at = _next_dehu_sync(now, config.periodicity)
            config.updated_at = now
    if due:
        db.commit()


def _try_send_dehu_batch_summary(db: Session, batch_id: str | None) -> None:
    if not batch_id:
        return
    batch = db.scalar(
        select(ClientDehuSyncBatch)
        .where(ClientDehuSyncBatch.id == batch_id)
        .with_for_update()
    )
    if not batch or batch.status not in {"running", "email_error"}:
        return
    rows = db.execute(
        select(ClientCertificateRequest, MessagingOrganization)
        .join(MessagingOrganization, MessagingOrganization.id == ClientCertificateRequest.organization_id)
        .where(ClientCertificateRequest.dehu_batch_id == batch.id)
        .order_by(MessagingOrganization.name)
    ).all()
    terminal = {"completed", "failed", "needs_action", "cancelled"}
    if len(rows) < batch.total_mailboxes or any(item.status not in terminal for item, _ in rows):
        return
    batch.status = "sending"
    batch.completed_at = utcnow()
    batch.updated_at = utcnow()
    db.commit()
    if not batch.notification_email:
        batch.status = "completed"
        batch.email_error = ""
        batch.updated_at = utcnow()
        db.commit()
        return
    ok_count = sum(1 for item, _ in rows if item.status == "completed")
    error_count = len(rows) - ok_count
    details = "".join(
        "<tr>"
        f"<td>{escape(org.name or org.company_code)}</td>"
        f"<td>{'Correcto' if item.status == 'completed' else 'Error'}</td>"
        f"<td>{escape(item.result_summary or item.error_message or item.status)}</td>"
        "</tr>"
        for item, org in rows
    )
    audit_items = []
    for item, _org in rows:
        try:
            parameters = json.loads(item.parameters_json or "{}")
        except (TypeError, ValueError):
            parameters = {}
        report = parameters.get("_dehu_audit") or []
        if isinstance(report, list):
            audit_items.extend(entry for entry in report if isinstance(entry, dict))

    # Un certificado de autorizado puede mostrar el mismo aviso al consultar
    # mas de un buzon. El correo debe enumerarlo una sola vez.
    unique_audit = {}
    for entry in audit_items:
        key = (
            str(entry.get("reference") or ""),
            str(entry.get("holder_tax_id") or ""),
        )
        anterior = unique_audit.get(key)
        if anterior is None or entry.get("new"):
            unique_audit[key] = entry
    audit_items = [
        entry for entry in unique_audit.values()
        if entry.get("new") and es_pendiente_dehu(entry.get("status"))
    ]
    contracted = [entry for entry in audit_items if entry.get("contracted")]
    opportunities = [entry for entry in audit_items if not entry.get("contracted")]

    def _audit_table(entries: list[dict], *, contracted_service: bool) -> str:
        if not entries:
            return "<p>Ninguna.</p>"
        rows_html = []
        for entry in sorted(
            entries,
            key=lambda value: (
                str(value.get("holder_name") or value.get("company_name") or ""),
                str(value.get("available_date") or ""),
                str(value.get("reference") or ""),
            ),
        ):
            client_name = (
                entry.get("company_name")
                or entry.get("holder_name")
                or "No localizado en Gestinem"
            )
            service = "Importada" if contracted_service else (
                "Cliente sin buzon activo" if entry.get("known_client")
                else "NIF no localizado"
            )
            rows_html.append(
                "<tr>"
                f"<td>{escape(str(client_name))}</td>"
                f"<td>{escape(str(entry.get('holder_tax_id') or 'Sin NIF'))}</td>"
                f"<td>{escape(str(entry.get('category') or 'NOTIFICACION'))}</td>"
                f"<td>{escape(str(entry.get('issuing_body') or 'No indicado'))}</td>"
                f"<td>{escape(str(entry.get('subject') or '(sin asunto)'))}</td>"
                f"<td>{escape(str(entry.get('available_date') or '-'))}</td>"
                f"<td>{escape(str(entry.get('expiration_date') or '-'))}</td>"
                f"<td>{escape(service)}</td>"
                "</tr>"
            )
        return (
            "<table border='1' cellpadding='6' cellspacing='0'>"
            "<tr><th>Cliente/titular</th><th>NIF/CIF</th><th>Tipo</th>"
            "<th>Organismo</th><th>Asunto</th><th>Puesta a disposicion</th>"
            "<th>Fecha maxima</th><th>Tratamiento</th></tr>"
            f"{''.join(rows_html)}</table>"
        )
    html = (
        "<p>Ha finalizado la consulta automatica de buzones DEHu.</p>"
        f"<p><strong>Consultados:</strong> {len(rows)} &nbsp; "
        f"<strong>Correctos:</strong> {ok_count} &nbsp; "
        f"<strong>Errores:</strong> {error_count} &nbsp; "
        f"<strong>Avisos nuevos:</strong> {len(audit_items)} &nbsp; "
        f"<strong>Con servicio:</strong> {len(contracted)} &nbsp; "
        f"<strong>Sin servicio:</strong> {len(opportunities)}</p>"
        "<h3>Notificaciones y comunicaciones nuevas de clientes con buzon activo</h3>"
        f"{_audit_table(contracted, contracted_service=True)}"
        "<h3>Oportunidades: avisos detectados sin buzon activo</h3>"
        "<p>Estos avisos solo se han detectado. No se han importado ni se ha "
        "descargado o abierto su contenido.</p>"
        f"{_audit_table(opportunities, contracted_service=False)}"
        "<h3>Resultado tecnico por buzon consultado</h3>"
        "<table border='1' cellpadding='6' cellspacing='0'>"
        "<tr><th>Cliente</th><th>Resultado</th><th>Detalle</th></tr>"
        f"{details}</table>"
    )
    try:
        sent = messaging_mail.send_mail(
            batch.notification_email,
            f"Resumen DEHu: {len(audit_items)} avisos nuevos, {len(rows)} buzones consultados, {error_count} errores",
            html,
        )
        if not sent:
            raise RuntimeError("El correo no esta configurado en el backend")
    except Exception as exc:
        batch.status = "email_error"
        batch.email_error = str(exc)[:4000]
    else:
        batch.status = "sent"
        batch.email_error = ""
        batch.email_sent_at = utcnow()
    batch.updated_at = utcnow()
    db.commit()


@router.post("/internal/worker/claim")
def claim_next_request(
    db: Session = Depends(_db),
    _auth: str = Depends(require_aapp_worker_key),
    _protocol: str = Depends(require_aapp_worker_claim_protocol),
):
    now = utcnow()
    _enqueue_due_dehu_mailboxes(db, now)
    stale_before = now - timedelta(minutes=15)
    item = db.scalar(
        select(ClientCertificateRequest).where(
            or_(
                and_(
                    ClientCertificateRequest.status.in_({"queued", "awaiting_issuance"}),
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


@router.post("/internal/worker/receipt-document")
def get_worker_receipt_document(
    payload: WorkerMaterialIn,
    db: Session = Depends(_db),
    _auth: str = Depends(require_aapp_worker_key),
):
    """Lee solo el resguardo del expediente reclamado por este worker."""
    item = _claimed_request(db, payload.request_id, payload.claim_token)
    document = db.get(ClientDocument, item.receipt_document_id) if item.receipt_document_id else None
    if not item.submitted_at or not document or document.organization_id != item.organization_id:
        raise HTTPException(status_code=404, detail="Resguardo no encontrado")
    if document.status == "withdrawn":
        raise HTTPException(status_code=410, detail="Resguardo retirado")
    return Response(content=ClientDocumentStorage().get(document.blob_key), media_type="application/pdf")


def _referencia_nueva_dehu(
    db: Session, request_item: ClientCertificateRequest,
    holder_tax_id: str, reference: str, *, conocida: bool = False,
) -> bool:
    clave = (holder_tax_id, reference)
    seen = db.get(ClientDehuSeenReference, clave)
    if seen is None:
        try:
            with db.begin_nested():
                seen = ClientDehuSeenReference(
                    holder_tax_id=holder_tax_id,
                    external_reference=reference,
                    first_request_id=None if conocida else request_item.id,
                    first_batch_id=None if conocida else request_item.dehu_batch_id,
                )
                db.add(seen)
                db.flush()
        except IntegrityError:
            seen = db.get(ClientDehuSeenReference, clave)
    return bool(seen and (
        seen.first_request_id == request_item.id
        or (request_item.dehu_batch_id and seen.first_batch_id == request_item.dehu_batch_id)
    ))


@router.post("/internal/worker/requests/{request_id}/dehu-notifications")
def upsert_worker_dehu_notifications(
    request_id: str,
    payload: WorkerDehuNotificationsIn,
    db: Session = Depends(_db),
    _auth: str = Depends(require_aapp_worker_key),
):
    """Guarda de forma idempotente las notificaciones leidas por el worker."""
    request_item = _claimed_request(db, request_id, payload.claim_token)
    if request_item.certificate_type != "DEHU_SYNC":
        raise HTTPException(status_code=409, detail="La solicitud no es una sincronizacion DEHu")
    now = utcnow()
    stored = []
    created_count = 0
    unassigned_count = 0
    ignored_read_count = 0
    unassigned_tax_ids = set()
    audit_items = []
    # Una organizacion solo es destinataria si tiene contratado/configurado un
    # buzon DEHu activo. El certificado usado para consultar puede ser el de un
    # autorizado RED y devolver avisos de muchas empresas; no debemos conservar
    # los de clientes sin este servicio.
    destinations_by_tax_id = {}
    ambiguous_tax_ids = set()
    rows = db.execute(
        select(MessagingOrganization, ClientDehuMailboxConfig)
        .join(
            ClientDehuMailboxConfig,
            ClientDehuMailboxConfig.organization_id == MessagingOrganization.id,
        )
        .where(
            MessagingOrganization.active.is_(True),
            ClientDehuMailboxConfig.active.is_(True),
        )
    ).all()
    for organization, mailbox in rows:
        normalized = re.sub(r"[^0-9A-Z]", "", (organization.tax_id or "").upper())
        if not normalized:
            continue
        if normalized in destinations_by_tax_id:
            ambiguous_tax_ids.add(normalized)
        else:
            destinations_by_tax_id[normalized] = (organization, mailbox)
    for normalized in ambiguous_tax_ids:
        destinations_by_tax_id.pop(normalized, None)
    known_by_tax_id = {}
    known_ambiguous_tax_ids = set()
    for organization in db.scalars(select(MessagingOrganization)).all():
        normalized = re.sub(r"[^0-9A-Z]", "", (organization.tax_id or "").upper())
        if not normalized:
            continue
        if normalized in known_by_tax_id:
            known_ambiguous_tax_ids.add(normalized)
        else:
            known_by_tax_id[normalized] = organization
    for normalized in known_ambiguous_tax_ids:
        known_by_tax_id.pop(normalized, None)
    for incoming in payload.notifications:
        reference = incoming.reference.strip()
        if not reference:
            raise HTTPException(status_code=422, detail="La referencia DEHu no puede estar vacia")
        holder_tax_id = re.sub(r"[^0-9A-Z]", "", incoming.holder_tax_id.upper())
        if not es_pendiente_dehu(incoming.status, incoming.source_endpoint):
            ignored_read_count += 1
            continue
        destination = destinations_by_tax_id.get(holder_tax_id)
        item = None
        if destination:
            item = db.scalar(select(ClientDehuNotification).where(
                ClientDehuNotification.organization_id == destination[0].id,
                ClientDehuNotification.external_reference == reference,
            ))
            # Una respuesta antigua no puede devolver a pendiente un aviso
            # que el sistema ya conoce como leido/realizado.
            if item and not es_pendiente_dehu(item.status, item.source_endpoint):
                ignored_read_count += 1
                continue
        nueva = _referencia_nueva_dehu(
            db, request_item, holder_tax_id, reference, conocida=item is not None,
        )
        known_organization = known_by_tax_id.get(holder_tax_id)
        report_organization = destination[0] if destination else known_organization
        audit_items.append({
            "reference": reference,
            "holder_tax_id": holder_tax_id,
            "holder_name": incoming.holder_name.strip(),
            "category": str(
                incoming.metadata.get("category")
                or incoming.action_type
                or "NOTIFICACION"
            ),
            "issuing_body": incoming.issuing_body.strip(),
            "subject": incoming.subject.strip(),
            "available_date": incoming.available_date.strip(),
            "expiration_date": incoming.expiration_date.strip(),
            "status": normalizar_estado_dehu(incoming.status),
            "new": nueva,
            "contracted": destination is not None,
            "known_client": report_organization is not None,
            "company_code": report_organization.company_code if report_organization else "",
            "company_name": report_organization.name if report_organization else "",
        })
        if destination is None:
            unassigned_count += 1
            if holder_tax_id:
                unassigned_tax_ids.add(holder_tax_id)
            continue
        target_organization, target_mailbox = destination
        item = db.scalar(select(ClientDehuNotification).where(
            ClientDehuNotification.organization_id == target_organization.id,
            ClientDehuNotification.external_reference == reference,
        ))
        if item is None:
            item = ClientDehuNotification(
                organization_id=target_organization.id,
                external_reference=reference,
                first_seen_at=now,
            )
            db.add(item)
            created_count += 1
        document = db.get(ClientDocument, incoming.document_id) if incoming.document_id else None
        if incoming.document_id and (
            not document or document.organization_id != request_item.organization_id
        ):
            raise HTTPException(status_code=422, detail="Documento DEHu no valido")
        item.request_id = request_item.id
        # El buzon de destino es el configurado para el titular, no el buzon
        # del certificado del autorizado que hizo la consulta.
        item.mailbox_id = target_mailbox.mailbox_id
        item.subject = incoming.subject.strip()
        item.description = incoming.description.strip()
        item.issuing_body = incoming.issuing_body.strip()
        item.issuing_body_source = incoming.issuing_body_source.strip()
        item.action_type = incoming.action_type.strip()
        item.holder_tax_id = holder_tax_id
        item.holder_name = incoming.holder_name.strip()
        item.available_date = incoming.available_date.strip()
        item.expiration_date = incoming.expiration_date.strip()
        item.status = normalizar_estado_dehu(incoming.status)
        item.source_endpoint = incoming.source_endpoint.strip()
        metadata = dict(incoming.metadata)
        metadata.update({
            "certificate_organization_id": request_item.organization_id,
            "assigned_organization_id": target_organization.id,
            "source_mailbox_id": incoming.mailbox_id.strip(),
            "assigned_mailbox_id": target_mailbox.mailbox_id,
        })
        item.metadata_json = json.dumps(
            metadata, ensure_ascii=False, separators=(",", ":"), default=str,
        )
        item.document_id = document.id if document else item.document_id
        item.last_seen_at = now
        item.updated_at = now
        db.flush()
        stored.append(item)
    try:
        request_parameters = json.loads(request_item.parameters_json or "{}")
    except (TypeError, ValueError):
        request_parameters = {}
    request_parameters["_dehu_audit"] = audit_items
    request_item.parameters_json = json.dumps(
        request_parameters, ensure_ascii=False, separators=(",", ":"), default=str,
    )
    request_item.updated_at = now
    db.commit()
    return {
        "items": [_serialize_dehu_notification(item) for item in stored],
        "count": len(stored),
        "assigned_count": len(stored),
        "created_count": created_count,
        "ignored_read_count": ignored_read_count,
        "unassigned_count": unassigned_count,
        "unassigned_tax_ids": sorted(unassigned_tax_ids),
        "discarded_without_active_mailbox_count": unassigned_count,
        "discarded_without_active_mailbox_tax_ids": sorted(unassigned_tax_ids),
        "audit_items": audit_items,
    }


@router.get("/internal/dehu-notifications")
def list_internal_dehu_notifications(
    company_code: str = "",
    limit: int = Query(default=1000, ge=1, le=2000),
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Lista la bandeja DEHu central para importarla en el escritorio."""
    statement = (
        select(ClientDehuNotification, MessagingOrganization)
        .join(
            MessagingOrganization,
            MessagingOrganization.id == ClientDehuNotification.organization_id,
        )
        .where(ClientDehuNotification.status == "PENDIENTE")
        .order_by(ClientDehuNotification.last_seen_at.desc())
        .limit(limit)
    )
    if company_code.strip():
        statement = statement.where(
            MessagingOrganization.company_code == company_code.strip(),
        )
    return {
        "items": [
            _serialize_dehu_notification(item, organization)
            for item, organization in db.execute(statement).all()
        ],
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
    if item.submitted_at and (
        not document or document.id == item.receipt_document_id
        or document.document_type in {"resguardo_aeat", "revision_aeat"}
    ):
        raise HTTPException(status_code=422, detail="Se requiere el certificado definitivo, no su resguardo")
    item.status = "completed"
    item.document_id = document.id if document else None
    item.result_summary = payload.result_summary
    item.certificate_result = payload.certificate_result
    item.next_attempt_at = None
    if item.submitted_at:
        item.last_checked_at = utcnow()
    item.error_code = ""
    item.error_message = ""
    item.claim_token = ""
    item.completed_at = utcnow()
    item.updated_at = utcnow()
    db.commit()
    _try_send_dehu_batch_summary(db, item.dehu_batch_id)
    return _serialize(item)


@router.post("/internal/requests/{request_id}/reclassify-receipt")
def reclassify_receipt(
    request_id: str, company_code: str, payload: ReclassifyReceiptIn,
    db: Session = Depends(_db),
    _auth: str = Depends(require_workstation_or_internal),
):
    """Migracion explicita tras inspeccionar el PDF desde el escritorio."""
    org = _organization_by_code(db, company_code)
    item = db.scalar(select(ClientCertificateRequest).where(
        ClientCertificateRequest.id == request_id,
        ClientCertificateRequest.organization_id == org.id,
    ).with_for_update())
    if not item:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if item.receipt_document_id == payload.document_id and item.external_reference == payload.external_reference:
        return _serialize(item)
    if item.status != "completed" or item.certificate_type != "AEAT_CORRIENTE" or item.document_id != payload.document_id:
        raise HTTPException(status_code=409, detail="No es una solicitud AEAT finalizada con ese documento")
    doc = db.get(ClientDocument, payload.document_id)
    if not doc or doc.organization_id != org.id or doc.status != "published" or not secrets.compare_digest(doc.sha256, payload.expected_sha256):
        raise HTTPException(status_code=409, detail="El documento ha cambiado o no pertenece al expediente")
    # Conservar id, PDF, firma y lecturas; separar la identidad del resguardo.
    doc.source_id = f"{item.id}:resguardo"
    doc.document_type = "resguardo_aeat"
    doc.display_name = "Resguardo - " + CERTIFICATE_TYPES[item.certificate_type]["name"]
    doc.description = "Resguardo de solicitud AEAT; pendiente de certificado definitivo"
    item.receipt_document_id = doc.id
    item.document_id = None
    item.external_reference = payload.external_reference
    item.submitted_at = item.completed_at or item.created_at
    item.completed_at = None
    item.certificate_result = ""
    item.result_summary = "Resguardo recibido; pendiente de emision del certificado AEAT."
    item.status = "awaiting_issuance"
    item.claim_token = ""
    item.next_attempt_at = utcnow()
    item.error_code = ""
    item.error_message = ""
    item.updated_at = utcnow()
    db.commit()
    return _serialize(item)


@router.post("/internal/worker/requests/{request_id}/pending-issuance")
def pending_issuance_request(
    request_id: str,
    payload: WorkerPendingIssuanceIn,
    db: Session = Depends(_db),
    _auth: str = Depends(require_aapp_worker_key),
):
    item = _claimed_request(db, request_id, payload.claim_token)
    if not item.certificate_type.startswith("AEAT_"):
        raise HTTPException(status_code=422, detail="El seguimiento corresponde a solicitudes AEAT")
    if payload.receipt_document_id:
        documento = db.get(ClientDocument, payload.receipt_document_id)
        if not documento or documento.organization_id != item.organization_id:
            raise HTTPException(status_code=422, detail="Resguardo no valido")
        if item.receipt_document_id and item.receipt_document_id != documento.id:
            raise HTTPException(status_code=409, detail="La solicitud ya tiene un resguardo archivado")
        item.receipt_document_id = documento.id
    referencia = payload.external_reference.strip().upper()
    if referencia and not re.fullmatch(r"[A-Z0-9][A-Z0-9/\-]{5,59}", referencia):
        raise HTTPException(status_code=422, detail="Referencia de expediente no valida")
    if item.external_reference and referencia and item.external_reference != referencia:
        raise HTTPException(status_code=409, detail="La referencia del expediente no puede cambiar")
    if referencia:
        item.external_reference = referencia
    now = utcnow()
    primera = item.submitted_at is None
    if primera:
        item.submitted_at = now
    else:
        item.last_checked_at = now
    presentado = item.submitted_at
    if presentado.tzinfo is None:
        presentado = presentado.replace(tzinfo=timezone.utc)
    vencido = now >= presentado + timedelta(hours=72)
    revision = payload.requires_review or not item.external_reference
    item.status = "needs_action" if revision else "awaiting_issuance"
    item.next_attempt_at = None if revision else now + timedelta(hours=24)
    item.result_summary = payload.message
    item.error_code = "aeat_issuance_review" if revision else "aeat_issuance_delayed" if vencido else ""
    item.error_message = (
        "La AEAT no ha emitido el certificado tras 72 horas. Revisar el expediente; "
        "esto no significa que el certificado sea negativo."
        if vencido else payload.message if revision else ""
    )
    item.certificate_result = ""
    item.document_id = None
    item.completed_at = None
    item.claim_token = ""
    item.updated_at = now
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
    _try_send_dehu_batch_summary(db, item.dehu_batch_id)
    return _serialize(item)
