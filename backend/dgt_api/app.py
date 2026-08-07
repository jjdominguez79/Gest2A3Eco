from __future__ import annotations

from datetime import datetime
import json
import re

from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, selectinload

from backend.dgt_api.database import Base, SessionLocal, engine
from backend.dgt_api.config import get_settings
from backend.dgt_api.models import (
    Comunicacion,
    Documento,
    DocumentoGenerado,
    Enlace,
    Evento,
    Expediente,
    Firma,
    Parte,
    SolicitudSubsanacion,
)
from backend.dgt_api.schemas import DocumentoGeneradoCreate, ExpedienteCreate, ExpedientePatch, PartePatch, SubsanacionCreate
from backend.dgt_api.security import require_internal_key, utcnow
from backend.dgt_api.service import (
    cargar_expediente,
    crear_enlace,
    crear_expediente,
    registrar_evento,
    serializar_expediente,
    verificar_enlace,
)
from backend.dgt_api.storage import delete_private_upload, save_private_upload
from backend.dgt_api.integrations import DatapriusBackend, ProviderError, SignRequestBackend
from backend.dgt_api.validation import validar_parte

app = FastAPI(title="Gestinem Tramites DGT API", version="1.0.0")
WEB_DIR = Path(__file__).with_name("web")
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


internal = Depends(require_internal_key)


def asegurar_expediente_editable(item: Expediente) -> None:
    if item.estado == "terminado":
        raise HTTPException(409, "El expediente esta terminado y es de solo lectura")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/integrations/status", dependencies=[internal])
def integrations_status():
    cfg = get_settings()
    return {
        "signrequest": bool(cfg.signrequest_token and cfg.signrequest_from_email),
        "dataprius": bool(cfg.dataprius_api_key and cfg.dataprius_api_secret),
        "firma_gestor_email": cfg.signrequest_gestor_email or cfg.signrequest_from_email,
        "firma_gestor_telefono": cfg.signrequest_gestor_telefono,
    }


@app.post("/api/v1/integrations/signrequest/send", dependencies=[internal])
async def integration_signrequest_send(
    file: UploadFile = File(...), firmantes: str = Form(...), asunto: str = Form(""),
    mensaje: str = Form(""), external_id: str = Form(""), callback_url: str = Form(""),
    usar_sms: bool = Form(False),
):
    try:
        return SignRequestBackend().enviar(
            await file.read(), file.filename or "documento.pdf", json.loads(firmantes),
            asunto, mensaje, external_id, callback_url, usar_sms,
        )
    except (ProviderError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/v1/integrations/signrequest/{request_id}", dependencies=[internal])
def integration_signrequest_status(request_id: str):
    try:
        estado = SignRequestBackend().consultar(request_id)
        return {key: value for key, value in estado.items() if not key.endswith("_url")}
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/v1/integrations/signrequest/{request_id}/cancel", dependencies=[internal])
def integration_signrequest_cancel(request_id: str):
    try:
        return SignRequestBackend().cancelar(request_id)
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.delete("/api/v1/integrations/signrequest/{request_id}", dependencies=[internal])
def integration_signrequest_delete(request_id: str):
    try:
        return SignRequestBackend().eliminar(request_id)
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/v1/integrations/signrequest/{request_id}/resend", dependencies=[internal])
def integration_signrequest_resend(request_id: str):
    try:
        return SignRequestBackend().reenviar(request_id)
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/v1/integrations/signrequest/{request_id}/evidence/{tipo}", dependencies=[internal])
def integration_signrequest_evidence(request_id: str, tipo: str):
    if tipo not in {"documento", "registro"}:
        raise HTTPException(422, "Tipo de evidencia no valido")
    try:
        return Response(SignRequestBackend().evidencia(request_id, tipo), media_type="application/pdf")
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/v1/integrations/dataprius/upload", dependencies=[internal])
async def integration_dataprius_upload(ruta: str = Form(""), file: UploadFile = File(...)):
    try:
        return DatapriusBackend().subir(ruta, file.filename or "documento", await file.read())
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/t/{referencia}/{rol}", response_class=HTMLResponse)
def portal_form(request: Request, referencia: str, rol: str, token: str = Query(...), db: Session = Depends(get_db)):
    context = public_context(referencia, rol, token, db)
    registrar_evento(db, None, "portal_abierto", rol, {"referencia": referencia})
    db.commit()
    return templates.TemplateResponse(
        request=request,
        name="form.html",
        context={"tramite": context, "token": token},
    )


@app.post("/api/v1/expedientes", dependencies=[internal], status_code=201)
def post_expediente(payload: ExpedienteCreate, db: Session = Depends(get_db)):
    item = crear_expediente(db, payload)
    db.commit()
    return serializar_expediente(cargar_expediente(db, item.id))


@app.get("/api/v1/expedientes", dependencies=[internal])
def get_expedientes(updated_since: datetime | None = None, db: Session = Depends(get_db)):
    stmt = select(Expediente).options(
        selectinload(Expediente.partes), selectinload(Expediente.vehiculo), selectinload(Expediente.operacion)
    ).order_by(Expediente.updated_at.desc())
    if updated_since:
        stmt = stmt.where(Expediente.updated_at > updated_since)
    return [serializar_expediente(item) for item in db.scalars(stmt).unique()]


@app.get("/api/v1/expedientes/{expediente_id}", dependencies=[internal])
def get_expediente(expediente_id: str, db: Session = Depends(get_db)):
    item = cargar_expediente(db, expediente_id)
    result = serializar_expediente(item)
    result["documentos"] = documentos_aportados(expediente_id, db)
    firma = db.scalar(
        select(Firma).where(Firma.expediente_id == expediente_id).order_by(Firma.id.desc())
    )
    result.update(
        {
            "firma_estado": firma.estado if firma else "",
            "firma_provider": firma.proveedor if firma else "",
            "firma_request_id": (firma.evidencia or {}).get("request_id", "") if firma else "",
            "firma_evidencia": firma.evidencia or {} if firma else {},
        }
    )
    return result


@app.patch("/api/v1/expedientes/{expediente_id}", dependencies=[internal])
def patch_expediente(expediente_id: str, payload: ExpedientePatch, db: Session = Depends(get_db)):
    item = cargar_expediente(db, expediente_id)
    asegurar_expediente_editable(item)
    if payload.version is not None and payload.version != item.version:
        raise HTTPException(409, "El expediente fue modificado por otro usuario")
    if payload.codigo_tasa is not None and payload.codigo_tasa and not re.fullmatch(
        r"[A-Za-z0-9-]{6,32}", payload.codigo_tasa.strip()
    ):
        raise HTTPException(422, "El codigo de tasa debe tener entre 6 y 32 letras, numeros o guiones")
    firma_data = payload.model_dump(
        exclude_none=True,
        include={"firma_estado", "firma_provider", "firma_request_id", "firma_evidencia"},
    )
    gestion = payload.model_dump(
        exclude_none=True, include={"codigo_tasa", "modelo_620_presentado"}
    )
    cambios = payload.model_dump(exclude_none=True)
    partes_por_rol = {parte.rol: parte for parte in item.partes}
    for rol in ("vendedor", "comprador"):
        parte = partes_por_rol.get(rol)
        if not parte:
            parte = Parte(expediente_id=item.id, rol=rol)
            item.partes.append(parte)
        for campo in ("nombre", "email", "telefono"):
            key = f"{rol}_{campo}"
            if key in cambios:
                setattr(parte, campo, cambios[key])
    if item.vehiculo is None:
        item.vehiculo = Vehiculo(expediente_id=item.id, datos={})
    if item.operacion is None:
        item.operacion = Operacion(expediente_id=item.id, datos={})
    if "vehiculo_matricula" in cambios:
        item.vehiculo.matricula = cambios["vehiculo_matricula"]
    if "vehiculo_bastidor" in cambios:
        item.vehiculo.bastidor = cambios["vehiculo_bastidor"]
    operacion_directa = {
        key: cambios[key]
        for key in ("precio_venta", "fecha_operacion")
        if key in cambios
    }
    if operacion_directa:
        item.operacion.datos = {**(item.operacion.datos or {}), **operacion_directa}
    for key, value in payload.model_dump(
        exclude_none=True,
        exclude={
            "version", "codigo_tasa", "modelo_620_presentado",
            "firma_estado", "firma_provider", "firma_request_id", "firma_evidencia",
            "vendedor_nombre", "vendedor_email", "vendedor_telefono",
            "comprador_nombre", "comprador_email", "comprador_telefono",
            "vehiculo_matricula", "vehiculo_bastidor", "precio_venta", "fecha_operacion",
        },
    ).items():
        setattr(item, key, value)
    if gestion:
        item.operacion.datos = {**(item.operacion.datos or {}), **gestion}
    if firma_data:
        firma = db.scalar(
            select(Firma).where(Firma.expediente_id == expediente_id).order_by(Firma.id.desc())
        )
        if not firma:
            firma = Firma(expediente_id=expediente_id)
            db.add(firma)
        firma.estado = firma_data.get("firma_estado", firma.estado)
        firma.proveedor = firma_data.get("firma_provider", firma.proveedor)
        evidencia = dict(firma.evidencia or {})
        evidencia.update(firma_data.get("firma_evidencia") or {})
        if "firma_request_id" in firma_data:
            evidencia["request_id"] = firma_data["firma_request_id"]
        firma.evidencia = evidencia
    item.version += 1
    registrar_evento(db, item.id, "expediente_actualizado", "gest2a3eco")
    db.commit()
    return serializar_expediente(cargar_expediente(db, item.id))


@app.post("/api/v1/expedientes/{expediente_id}/finalizar", dependencies=[internal])
def finalizar_expediente(expediente_id: str, db: Session = Depends(get_db)):
    item = cargar_expediente(db, expediente_id)
    if item.estado == "terminado":
        return serializar_expediente(item)
    firma = db.scalar(
        select(Firma).where(Firma.expediente_id == expediente_id).order_by(Firma.id.desc())
    )
    if not firma or str(firma.estado or "").lower() not in {"firmado", "signed", "completed"}:
        raise HTTPException(422, "Solo se puede terminar un expediente con la firma completada")
    item.estado = "terminado"
    item.version += 1
    registrar_evento(db, item.id, "expediente_terminado", "gest2a3eco")
    db.commit()
    return serializar_expediente(cargar_expediente(db, item.id))


@app.delete("/api/v1/expedientes/{expediente_id}", dependencies=[internal], status_code=204)
def delete_expediente(expediente_id: str, db: Session = Depends(get_db)):
    item = cargar_expediente(db, expediente_id)
    storage_keys = list(
        db.scalars(select(Documento.storage_key).where(Documento.expediente_id == expediente_id)).all()
    )
    registrar_evento(db, item.id, "expediente_eliminado", "gest2a3eco", {"referencia": item.referencia})
    db.flush()
    db.execute(update(Evento).where(Evento.expediente_id == expediente_id).values(expediente_id=None))
    for model in (Enlace, Documento, SolicitudSubsanacion, DocumentoGenerado, Firma, Comunicacion):
        db.execute(delete(model).where(model.expediente_id == expediente_id))
    db.delete(item)
    db.commit()
    for storage_key in storage_keys:
        delete_private_upload(storage_key)


@app.post("/api/v1/expedientes/{expediente_id}/links", dependencies=[internal])
def post_links(expediente_id: str, db: Session = Depends(get_db)):
    item = cargar_expediente(db, expediente_id)
    asegurar_expediente_editable(item)
    links = {rol: crear_enlace(db, item, rol) for rol in ("vendedor", "comprador")}
    item.estado = "enlaces_enviados"
    db.commit()
    return links


@app.post("/api/v1/expedientes/{expediente_id}/links/{rol}/revoke", dependencies=[internal])
def revoke_link(expediente_id: str, rol: str, db: Session = Depends(get_db)):
    item = cargar_expediente(db, expediente_id)
    asegurar_expediente_editable(item)
    now = utcnow()
    links = db.scalars(
        select(Enlace).where(Enlace.expediente_id == expediente_id, Enlace.rol == rol, Enlace.revoked_at.is_(None))
    ).all()
    for link in links:
        link.revoked_at = now
    registrar_evento(db, expediente_id, "enlace_revocado", "gest2a3eco", {"rol": rol})
    db.commit()
    return {"revoked": len(links)}


@app.post("/api/v1/expedientes/{expediente_id}/subsanaciones", dependencies=[internal], status_code=201)
def post_subsanacion(expediente_id: str, payload: SubsanacionCreate, db: Session = Depends(get_db)):
    item = cargar_expediente(db, expediente_id)
    asegurar_expediente_editable(item)
    if payload.rol not in {"vendedor", "comprador"}:
        raise HTTPException(422, "Rol no valido")
    parte = next(part for part in item.partes if part.rol == payload.rol)
    db.add(SolicitudSubsanacion(expediente_id=item.id, rol=payload.rol, mensaje=payload.mensaje))
    parte.estado = "requiere_subsanacion"
    item.estado = "requiere_subsanacion"
    link = crear_enlace(db, item, payload.rol)
    registrar_evento(db, item.id, "subsanacion_solicitada", "gest2a3eco", payload.model_dump())
    db.commit()
    return {"status": "pendiente", "rol": payload.rol, "url": link["url"], "expires_at": link["expires_at"]}


@app.post("/api/v1/expedientes/{expediente_id}/validar", dependencies=[internal])
def validar_interno(expediente_id: str, db: Session = Depends(get_db)):
    item = cargar_expediente(db, expediente_id)
    asegurar_expediente_editable(item)
    errors = []
    for parte in item.partes:
        if parte.estado != "completado":
            if parte.submitted_at and ultima_actualizacion_fue_interna(db, item.id, parte.rol):
                parte.estado = "completado"
            else:
                errors.append(f"El {parte.rol} debe enviar el formulario completo.")
        errors.extend(f"{parte.rol.capitalize()}: {error}" for error in validar_parte(parte, parte.rol))
    if errors:
        raise HTTPException(422, detail=errors)
    vendedor = next(parte for parte in item.partes if parte.rol == "vendedor")
    if vendedor.tipo_persona == "juridica" and not db.scalar(
        select(Documento.id).where(
            Documento.expediente_id == expediente_id,
            Documento.rol == "vendedor",
            Documento.tipo == "factura",
        ).limit(1)
    ):
        raise HTTPException(422, "La factura del vendedor juridico es obligatoria")
    if (item.operacion.datos or {}).get("modelo_620_presentado") and not db.scalar(
        select(Documento.id).where(
            Documento.expediente_id == expediente_id,
            Documento.tipo == "modelo_620",
        ).limit(1)
    ):
        raise HTTPException(422, "Debes adjuntar el modelo 620 presentado")
    item.estado = "validado"
    registrar_evento(db, item.id, "expediente_validado", "gest2a3eco")
    db.commit()
    return {"status": "validado"}


@app.patch("/api/v1/expedientes/{expediente_id}/partes/{rol}", dependencies=[internal])
def patch_parte_interna(
    expediente_id: str, rol: str, payload: PartePatch, db: Session = Depends(get_db)
):
    item = cargar_expediente(db, expediente_id)
    asegurar_expediente_editable(item)
    if rol not in {"vendedor", "comprador"}:
        raise HTTPException(422, "Rol no valido")
    parte = next(part for part in item.partes if part.rol == rol)
    estado_anterior = parte.estado
    cambios = []
    for key in ("tipo_persona", "nombre", "nif", "email", "telefono"):
        value = getattr(payload, key)
        if getattr(parte, key) != value:
            cambios.append(key)
            setattr(parte, key, value)
    datos_anteriores = dict(parte.datos or {})
    datos_nuevos = {**datos_anteriores, **payload.datos}
    cambios.extend(
        f"datos.{key}" for key, value in payload.datos.items()
        if datos_anteriores.get(key) != value
    )
    parte.datos = datos_nuevos
    sync_parte_operacion(item, parte, rol)
    if estado_anterior != "completado" and not parte.submitted_at:
        parte.estado = "en_curso"
    else:
        parte.estado = "completado"
    item.estado = "revision_interna" if parte.estado == "completado" else f"{rol}_en_curso"
    registrar_evento(
        db,
        item.id,
        "parte_actualizada_internamente",
        "gest2a3eco",
        {"rol": rol, "estado_anterior": estado_anterior, "campos_modificados": cambios},
    )
    db.commit()
    return serializar_expediente(cargar_expediente(db, item.id))


def ultima_actualizacion_fue_interna(db: Session, expediente_id: str, rol: str) -> bool:
    eventos = db.scalars(
        select(Evento)
        .where(
            Evento.expediente_id == expediente_id,
            Evento.tipo.in_(
                (
                    "parte_actualizada_internamente",
                    "formulario_guardado",
                    "formulario_completado",
                    "subsanacion_solicitada",
                )
            ),
        )
        .order_by(Evento.created_at.desc(), Evento.id.desc())
    ).all()
    for evento in eventos:
        datos = evento.datos or {}
        evento_rol = datos.get("rol") or evento.actor
        if evento_rol == rol:
            return evento.tipo == "parte_actualizada_internamente"
    return False


@app.get("/api/v1/expedientes/{expediente_id}/documentos", dependencies=[internal])
def documentos_aportados(expediente_id: str, db: Session = Depends(get_db)):
    cargar_expediente(db, expediente_id)
    docs = db.scalars(select(Documento).where(Documento.expediente_id == expediente_id)).all()
    return [
        {
            "id": doc.id, "rol": doc.rol, "tipo": doc.tipo, "nombre_archivo": doc.nombre_archivo,
            "content_type": doc.content_type, "size": doc.size, "sha256": doc.sha256, "created_at": doc.created_at,
        }
        for doc in docs
    ]


@app.post("/api/v1/expedientes/{expediente_id}/documentos", dependencies=[internal], status_code=201)
async def post_documento_interno(
    expediente_id: str,
    rol: str = Form(default="gestor"),
    tipo: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    item = cargar_expediente(db, expediente_id)
    asegurar_expediente_editable(item)
    if tipo not in {"factura", "modelo_620", "documentacion"}:
        raise HTTPException(422, "Tipo de documento no valido")
    stored = await save_private_upload(file, item.referencia, rol)
    doc = Documento(expediente_id=item.id, rol=rol[:16], tipo=tipo, **stored)
    db.add(doc)
    registrar_evento(
        db, item.id, "documento_subido_internamente", "gest2a3eco",
        {"tipo": doc.tipo, "nombre": doc.nombre_archivo, "sha256": doc.sha256},
    )
    db.commit()
    return {"id": doc.id, "tipo": doc.tipo, "nombre_archivo": doc.nombre_archivo, "sha256": doc.sha256}


@app.get("/api/v1/documentos/{documento_id}/download", dependencies=[internal])
def download_documento(documento_id: str, db: Session = Depends(get_db)):
    doc = db.get(Documento, documento_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")
    root = Path(get_settings().storage_dir).resolve()
    path = (root / doc.storage_key).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "Archivo no disponible")
    return FileResponse(path, media_type=doc.content_type, filename=doc.nombre_archivo)


@app.delete("/api/v1/documentos/{documento_id}", dependencies=[internal], status_code=204)
def delete_documento(documento_id: str, db: Session = Depends(get_db)):
    doc = db.get(Documento, documento_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")
    asegurar_expediente_editable(cargar_expediente(db, doc.expediente_id))
    storage_key = doc.storage_key
    registrar_evento(
        db, doc.expediente_id, "documento_eliminado", "gest2a3eco",
        {"tipo": doc.tipo, "nombre": doc.nombre_archivo},
    )
    db.delete(doc)
    db.commit()
    delete_private_upload(storage_key)


@app.post("/api/v1/expedientes/{expediente_id}/documentos-generados", dependencies=[internal], status_code=201)
def post_documento_generado(
    expediente_id: str, payload: DocumentoGeneradoCreate, db: Session = Depends(get_db)
):
    item = cargar_expediente(db, expediente_id)
    asegurar_expediente_editable(item)
    datos = payload.model_dump()
    if not datos.get("fecha_generacion"):
        datos["fecha_generacion"] = utcnow().isoformat()
    doc = DocumentoGenerado(
        expediente_id=expediente_id,
        tipo=payload.tipo_documento,
        datos=datos,
    )
    db.add(doc)
    registrar_evento(db, expediente_id, "documento_generado", "gest2a3eco", {"tipo": doc.tipo})
    db.commit()
    return {"id": doc.id}


@app.get("/api/v1/expedientes/{expediente_id}/documentos-generados", dependencies=[internal])
def get_documentos_generados(expediente_id: str, db: Session = Depends(get_db)):
    cargar_expediente(db, expediente_id)
    docs = db.scalars(select(DocumentoGenerado).where(DocumentoGenerado.expediente_id == expediente_id)).all()
    result = [{"id": doc.id, "expediente_id": doc.expediente_id, **(doc.datos or {})} for doc in docs]
    return sorted(result, key=lambda item: item.get("fecha_generacion") or "", reverse=True)


@app.delete("/api/v1/documentos-generados/{documento_id}", dependencies=[internal])
def delete_documento_generado(documento_id: str, db: Session = Depends(get_db)):
    doc = db.get(DocumentoGenerado, documento_id)
    if not doc:
        raise HTTPException(404, "Documento generado no encontrado")
    asegurar_expediente_editable(cargar_expediente(db, doc.expediente_id))
    result = {"id": doc.id, "expediente_id": doc.expediente_id, **(doc.datos or {})}
    registrar_evento(
        db, doc.expediente_id, "documento_generado_eliminado", "gest2a3eco", {"tipo": doc.tipo}
    )
    db.delete(doc)
    db.commit()
    return result


def public_context(referencia: str, rol: str, token: str, db: Session):
    item, _ = verificar_enlace(db, referencia, rol, token)
    own = next(parte for parte in item.partes if parte.rol == rol)
    factura_aportada = bool(
        rol == "vendedor"
        and db.scalar(
            select(Documento.id).where(
                Documento.expediente_id == item.id,
                Documento.rol == "vendedor",
                Documento.tipo == "factura",
            ).limit(1)
        )
    )
    return {
        "referencia": item.referencia,
        "rol": rol,
        "estado": own.estado,
        "parte": {
            "tipo_persona": own.tipo_persona,
            "nombre": own.nombre,
            "nif": own.nif,
            "email": own.email,
            "telefono": own.telefono,
            "datos": own.datos or {},
        },
        "vehiculo": (item.vehiculo.datos | {"matricula": item.vehiculo.matricula, "bastidor": item.vehiculo.bastidor})
        if rol == "vendedor" and item.vehiculo else {},
        "operacion": item.operacion.datos if rol == "vendedor" and item.operacion else {},
        "factura_aportada": factura_aportada,
    }


@app.get("/public/tramites/{referencia}/{rol}")
def get_public(referencia: str, rol: str, token: str = Query(...), db: Session = Depends(get_db)):
    result = public_context(referencia, rol, token, db)
    registrar_evento(db, None, "enlace_abierto", rol, {"referencia": referencia})
    db.commit()
    return result


@app.patch("/public/tramites/{referencia}/{rol}")
def patch_public(referencia: str, rol: str, payload: PartePatch, token: str = Query(...), db: Session = Depends(get_db)):
    item, _ = verificar_enlace(db, referencia, rol, token)
    asegurar_expediente_editable(item)
    parte = next(part for part in item.partes if part.rol == rol)
    for key in ("tipo_persona", "nombre", "nif", "email", "telefono", "datos"):
        setattr(parte, key, getattr(payload, key))
    sync_parte_operacion(item, parte, rol)
    parte.estado = "en_curso"
    item.estado = f"{rol}_en_curso"
    registrar_evento(db, item.id, "formulario_guardado", rol)
    db.commit()
    return public_context(referencia, rol, token, db)


def sync_parte_operacion(item: Expediente, parte: Parte, rol: str) -> None:
    if rol != "vendedor":
        return
    datos = parte.datos or {}
    item.vehiculo.matricula = str(datos.get("vehiculo_matricula") or "").strip().upper()
    item.vehiculo.bastidor = str(datos.get("vehiculo_bastidor") or "").strip().upper()
    item.vehiculo.datos = {
        key: value
        for key, value in datos.items()
        if key.startswith("vehiculo_") or key in {"primera_matriculacion", "kilometraje"}
    }
    operacion = dict(item.operacion.datos or {})
    for key in (
        "precio_venta", "fecha_operacion", "hora_entrega", "forma_pago", "llaves_vehiculo",
    ):
        operacion[key] = datos.get(key, "")
    item.operacion.datos = operacion


@app.post("/public/tramites/{referencia}/{rol}/submit")
def submit_public(
    referencia: str,
    rol: str,
    token: str = Query(...),
    privacy_accepted: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    item, _ = verificar_enlace(db, referencia, rol, token)
    asegurar_expediente_editable(item)
    parte = next(part for part in item.partes if part.rol == rol)
    errors = validar_parte(parte, rol)
    if rol == "vendedor" and parte.tipo_persona == "juridica" and not db.scalar(
        select(Documento.id).where(
            Documento.expediente_id == item.id,
            Documento.rol == "vendedor",
            Documento.tipo == "factura",
        ).limit(1)
    ):
        errors.append("La factura emitida por el vendedor es obligatoria.")
    if errors:
        raise HTTPException(422, detail=errors)
    if not privacy_accepted:
        raise HTTPException(422, "Debe aceptar la informacion de proteccion de datos")
    parte.estado = "completado"
    parte.submitted_at = utcnow()
    item.estado = "pendiente_revision" if all(p.estado == "completado" for p in item.partes) else f"{rol}_completado"
    registrar_evento(db, item.id, "formulario_completado", rol)
    db.commit()
    return {"status": "completado", "expediente_estado": item.estado}


@app.post("/public/tramites/{referencia}/{rol}/documentos", status_code=201)
async def post_public_documento(
    referencia: str,
    rol: str,
    token: str = Query(...),
    tipo: str = Form(default="documentacion"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    item, _ = verificar_enlace(db, referencia, rol, token)
    asegurar_expediente_editable(item)
    parte = next(part for part in item.partes if part.rol == rol)
    if rol != "vendedor" or parte.tipo_persona != "juridica" or tipo != "factura":
        raise HTTPException(422, "Solo el vendedor juridico debe aportar la factura.")
    stored = await save_private_upload(file, referencia, rol)
    doc = Documento(expediente_id=item.id, rol=rol, tipo=tipo[:64], **stored)
    db.add(doc)
    registrar_evento(
        db, item.id, "documento_subido", rol, {"tipo": doc.tipo, "nombre": doc.nombre_archivo, "sha256": doc.sha256}
    )
    db.commit()
    return {"id": doc.id, "tipo": doc.tipo, "nombre_archivo": doc.nombre_archivo, "sha256": doc.sha256}


@app.get("/api/v1/sync", dependencies=[internal])
def sync(updated_since: datetime | None = None, db: Session = Depends(get_db)):
    return get_expedientes(updated_since=updated_since, db=db)
