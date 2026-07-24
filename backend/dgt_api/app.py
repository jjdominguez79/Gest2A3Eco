from __future__ import annotations

from datetime import datetime

from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.dgt_api.database import Base, SessionLocal, engine
from backend.dgt_api.config import get_settings
from backend.dgt_api.models import Documento, DocumentoGenerado, Enlace, Evento, Expediente, Parte, SolicitudSubsanacion
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
from backend.dgt_api.storage import save_private_upload
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


@app.get("/health")
def health():
    return {"status": "ok"}


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
    return result


@app.patch("/api/v1/expedientes/{expediente_id}", dependencies=[internal])
def patch_expediente(expediente_id: str, payload: ExpedientePatch, db: Session = Depends(get_db)):
    item = cargar_expediente(db, expediente_id)
    if payload.version is not None and payload.version != item.version:
        raise HTTPException(409, "El expediente fue modificado por otro usuario")
    for key, value in payload.model_dump(exclude_none=True, exclude={"version"}).items():
        setattr(item, key, value)
    item.version += 1
    registrar_evento(db, item.id, "expediente_actualizado", "gest2a3eco")
    db.commit()
    return serializar_expediente(cargar_expediente(db, item.id))


@app.post("/api/v1/expedientes/{expediente_id}/links", dependencies=[internal])
def post_links(expediente_id: str, db: Session = Depends(get_db)):
    item = cargar_expediente(db, expediente_id)
    links = {rol: crear_enlace(db, item, rol) for rol in ("vendedor", "comprador")}
    item.estado = "enlaces_enviados"
    db.commit()
    return links


@app.post("/api/v1/expedientes/{expediente_id}/links/{rol}/revoke", dependencies=[internal])
def revoke_link(expediente_id: str, rol: str, db: Session = Depends(get_db)):
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
    if payload.rol not in {"vendedor", "comprador"}:
        raise HTTPException(422, "Rol no valido")
    db.add(SolicitudSubsanacion(expediente_id=item.id, rol=payload.rol, mensaje=payload.mensaje))
    item.estado = "requiere_subsanacion"
    registrar_evento(db, item.id, "subsanacion_solicitada", "gest2a3eco", payload.model_dump())
    db.commit()
    return {"status": "pendiente"}


@app.post("/api/v1/expedientes/{expediente_id}/validar", dependencies=[internal])
def validar_interno(expediente_id: str, db: Session = Depends(get_db)):
    item = cargar_expediente(db, expediente_id)
    if not all(parte.estado == "completado" for parte in item.partes):
        raise HTTPException(422, "Ambas partes deben haber completado sus datos")
    vendedor = next(parte for parte in item.partes if parte.rol == "vendedor")
    if vendedor.tipo_persona == "juridica" and not db.scalar(
        select(Documento.id).where(
            Documento.expediente_id == expediente_id,
            Documento.rol == "vendedor",
            Documento.tipo == "factura",
        ).limit(1)
    ):
        raise HTTPException(422, "La factura del vendedor juridico es obligatoria")
    item.estado = "validado"
    registrar_evento(db, item.id, "expediente_validado", "gest2a3eco")
    db.commit()
    return {"status": "validado"}


@app.patch("/api/v1/expedientes/{expediente_id}/partes/{rol}", dependencies=[internal])
def patch_parte_interna(
    expediente_id: str, rol: str, payload: PartePatch, db: Session = Depends(get_db)
):
    item = cargar_expediente(db, expediente_id)
    if rol not in {"vendedor", "comprador"}:
        raise HTTPException(422, "Rol no valido")
    parte = next(part for part in item.partes if part.rol == rol)
    for key in ("tipo_persona", "nombre", "nif", "email", "telefono", "datos"):
        setattr(parte, key, getattr(payload, key))
    parte.estado = "en_curso"
    item.estado = f"{rol}_en_curso"
    registrar_evento(db, item.id, "parte_actualizada_internamente", "gest2a3eco", {"rol": rol})
    db.commit()
    return serializar_expediente(cargar_expediente(db, item.id))


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


@app.post("/api/v1/expedientes/{expediente_id}/documentos-generados", dependencies=[internal], status_code=201)
def post_documento_generado(
    expediente_id: str, payload: DocumentoGeneradoCreate, db: Session = Depends(get_db)
):
    cargar_expediente(db, expediente_id)
    doc = DocumentoGenerado(
        expediente_id=expediente_id,
        tipo=payload.tipo_documento,
        datos=payload.model_dump(),
    )
    db.add(doc)
    registrar_evento(db, expediente_id, "documento_generado", "gest2a3eco", {"tipo": doc.tipo})
    db.commit()
    return {"id": doc.id}


@app.get("/api/v1/expedientes/{expediente_id}/documentos-generados", dependencies=[internal])
def get_documentos_generados(expediente_id: str, db: Session = Depends(get_db)):
    cargar_expediente(db, expediente_id)
    docs = db.scalars(select(DocumentoGenerado).where(DocumentoGenerado.expediente_id == expediente_id)).all()
    return [{"id": doc.id, "expediente_id": doc.expediente_id, **(doc.datos or {})} for doc in docs]


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
    parte = next(part for part in item.partes if part.rol == rol)
    for key in ("tipo_persona", "nombre", "nif", "email", "telefono", "datos"):
        setattr(parte, key, getattr(payload, key))
    parte.estado = "en_curso"
    item.estado = f"{rol}_en_curso"
    registrar_evento(db, item.id, "formulario_guardado", rol)
    db.commit()
    return public_context(referencia, rol, token, db)


@app.post("/public/tramites/{referencia}/{rol}/submit")
def submit_public(
    referencia: str,
    rol: str,
    token: str = Query(...),
    privacy_accepted: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    item, _ = verificar_enlace(db, referencia, rol, token)
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
