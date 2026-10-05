"""API autenticada de ayudas para Flutter y panel interno del escritorio."""

from __future__ import annotations

import os
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.api.client_profile_api import _authenticated_client
from backend.api.client_models import ClientFeatureFlagAudit
from backend.api.config import get_settings
from backend.api.database import SessionLocal
from backend.api.feature_flags import is_subsidies_enabled, require_subsidies_enabled
from backend.api.messaging_models import MessagingClient, MessagingOrganization
from backend.api.security import require_workstation_or_internal
from backend.api.subvenciones_models import (
    SubvencionConfiguracion,
    SubvencionConvocatoria,
    SubvencionEntrega,
    SubvencionEjecucion,
    SubvencionPreferencia,
    SubvencionSuscripcion,
)
from backend.api.subvenciones_service import (
    CCAA,
    PROVINCIAS,
    SubvencionesService,
    coincide_cliente,
    slug,
    territorio_organizacion,
)

router = APIRouter(
    prefix="/api/v1/messaging/client/subvenciones",
    tags=["client-subsidies"],
)

AVISO_LEGAL = (
    "Informacion orientativa obtenida de la Base de Datos Nacional de Subvenciones. "
    "No sustituye al texto oficial, que prevalece en caso de discrepancia."
)


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class SuscripcionIn(BaseModel):
    nivel: str = Field(max_length=16)
    codigo: str = Field(max_length=160)
    nombre: str = Field(max_length=200)


class PreferenciasIn(BaseModel):
    notificaciones_activas: bool = False
    incluir_nacionales: bool = True
    usar_territorio_empresa: bool = True
    suscripciones: list[SuscripcionIn] = Field(default_factory=list, max_length=100)


class ConfiguracionIn(BaseModel):
    servicio_activo: bool
    avisos_activos: bool
    resumenes_ia_activos: bool


class ConvocatoriaPatch(BaseModel):
    visible: bool | None = None
    revisada: bool | None = None
    rehacer_resumen: bool = False


class OrganizacionPatch(BaseModel):
    activa: bool


class OrganizacionesBulkPatch(BaseModel):
    codigos: list[str] = Field(min_length=1, max_length=500)
    activa: bool


def _preference(db: Session, client_id: str, *, create: bool = False) -> SubvencionPreferencia | None:
    item = db.get(SubvencionPreferencia, client_id)
    if item is None and create:
        item = SubvencionPreferencia(client_id=client_id)
        db.add(item)
        db.flush()
    return item


def _subscriptions(db: Session, client_id: str) -> list[SubvencionSuscripcion]:
    return db.scalars(select(SubvencionSuscripcion).where(
        SubvencionSuscripcion.client_id == client_id,
    ).order_by(SubvencionSuscripcion.nivel, SubvencionSuscripcion.nombre)).all()


def _org_for_client(db: Session, client: MessagingClient) -> MessagingOrganization:
    return require_subsidies_enabled(db, client.organization_id)


def _summary(call: SubvencionConvocatoria) -> dict:
    summary = call.resumen_json or {}
    organ = " · ".join(x for x in (call.organo_nivel2, call.organo_nivel3) if x)
    return {
        "codigo_bdns": call.codigo_bdns,
        "titulo": call.titulo,
        "organo": organ or call.organo_nivel1,
        "ambito": call.ambito,
        "alcance_nacional": call.alcance_nacional,
        "ccaa": call.ccaa_json or [],
        "provincias": call.provincias_json or [],
        "municipio": call.municipio_nombre or None,
        "fecha_publicacion": call.fecha_recepcion.isoformat() if call.fecha_recepcion else None,
        "fecha_fin": call.fecha_fin.isoformat() if call.fecha_fin else None,
        "plazo_texto": None if call.fecha_fin else " · ".join(
            x for x in (call.texto_inicio, call.texto_fin) if x
        ) or None,
        "abierto": call.abierto,
        "presupuesto": call.presupuesto,
        "resumen_corto": summary.get("resumen"),
        "etiquetas": summary.get("etiquetas") or [],
        "revisada": call.revisada,
    }


def _detail(call: SubvencionConvocatoria) -> dict:
    return {
        **_summary(call),
        "organo_nivel1": call.organo_nivel1,
        "organo_nivel2": call.organo_nivel2,
        "organo_nivel3": call.organo_nivel3,
        "fecha_inicio": call.fecha_inicio.isoformat() if call.fecha_inicio else None,
        "texto_inicio": call.texto_inicio or None,
        "texto_fin": call.texto_fin or None,
        "tipo_convocatoria": call.tipo_convocatoria or None,
        "finalidad": call.finalidad or None,
        "beneficiarios_oficiales": call.beneficiarios_json or [],
        "sectores": call.sectores_json or [],
        "instrumentos": call.instrumentos_json or [],
        "mrr": call.mrr,
        "resumen": call.resumen_json if call.resumen_estado == "ok" else None,
        "resumen_estado": call.resumen_estado,
        "enlaces": call.enlaces_json or [],
        "aviso_legal": AVISO_LEGAL,
    }


@router.get("")
def listar(
    request: Request,
    para_mi: bool = True,
    vigentes: bool = True,
    ambito: str = "",
    territorio: str = "",
    etiqueta: str = "",
    q: str = Query("", max_length=120),
    pagina: int = Query(0, ge=0),
    tamano: int = Query(20, ge=1, le=100),
    db: Session = Depends(_db),
):
    client = _authenticated_client(request, db)
    org = _org_for_client(db, client)
    preference = _preference(db, client.id)
    subscriptions = _subscriptions(db, client.id)
    stmt = select(SubvencionConvocatoria).where(SubvencionConvocatoria.visible.is_(True))
    if vigentes:
        stmt = stmt.where(
            SubvencionConvocatoria.abierto.is_not(False),
            or_(SubvencionConvocatoria.fecha_fin.is_(None), SubvencionConvocatoria.fecha_fin >= date.today()),
        )
    if ambito:
        stmt = stmt.where(SubvencionConvocatoria.ambito == ambito.upper())
    if q.strip():
        stmt = stmt.where(SubvencionConvocatoria.titulo.ilike(f"%{q.strip()}%"))
    rows = db.scalars(stmt.order_by(
        SubvencionConvocatoria.fecha_recepcion.desc(), SubvencionConvocatoria.codigo_bdns.desc(),
    )).all()
    if para_mi:
        rows = [item for item in rows if coincide_cliente(item, org, preference, subscriptions)]
    if territorio:
        needle = territorio.strip()
        rows = [item for item in rows if (
            needle in (item.ccaa_json or []) or needle in (item.provincias_json or [])
            or needle == item.municipio_slug
        )]
    if etiqueta:
        rows = [item for item in rows if etiqueta in ((item.resumen_json or {}).get("etiquetas") or [])]
    total = len(rows)
    page = rows[pagina * tamano:(pagina + 1) * tamano]
    return {"total": total, "pagina": pagina, "tamano": tamano, "elementos": [_summary(x) for x in page]}


@router.get("/preferencias")
def preferencias(request: Request, db: Session = Depends(_db)):
    client = _authenticated_client(request, db)
    org = _org_for_client(db, client)
    item = _preference(db, client.id)
    subscriptions = _subscriptions(db, client.id)
    return {
        "notificaciones_activas": bool(item and item.notificaciones_activas),
        "incluir_nacionales": True if item is None else item.incluir_nacionales,
        "usar_territorio_empresa": True if item is None else item.usar_territorio_empresa,
        "territorio_empresa": territorio_organizacion(org),
        "suscripciones": [
            {"nivel": x.nivel, "codigo": x.codigo, "nombre": x.nombre}
            for x in subscriptions
        ],
    }


def _validate_subscription(value: SuscripcionIn) -> tuple[str, str, str]:
    level = value.nivel.strip().upper()
    code = value.codigo.strip()
    name = value.nombre.strip()
    if level not in {"AUTONOMICA", "PROVINCIAL", "MUNICIPAL"}:
        raise HTTPException(422, "Nivel territorial no valido")
    if level == "AUTONOMICA" and code not in CCAA:
        raise HTTPException(422, "Comunidad autonoma no valida")
    if level == "PROVINCIAL" and not code.startswith("ES"):
        raise HTTPException(422, "Provincia no valida")
    if level == "MUNICIPAL":
        ccaa_code, separator, municipality = code.partition(":")
        municipality = slug(municipality if separator else (code or name))
        if separator and ccaa_code not in CCAA:
            raise HTTPException(422, "Comunidad del municipio no valida")
        code = f"{ccaa_code}:{municipality}" if separator else municipality
        if not municipality:
            raise HTTPException(422, "Municipio no valido")
    if not name:
        raise HTTPException(422, "El territorio necesita nombre")
    return level, code, name


@router.put("/preferencias")
def guardar_preferencias(payload: PreferenciasIn, request: Request, db: Session = Depends(_db)):
    client = _authenticated_client(request, db)
    _org_for_client(db, client)
    validated = [_validate_subscription(item) for item in payload.suscripciones]
    if len(set((level, code) for level, code, _name in validated)) != len(validated):
        raise HTTPException(422, "Hay territorios duplicados")
    preference = _preference(db, client.id, create=True)
    assert preference is not None
    preference.notificaciones_activas = payload.notificaciones_activas
    preference.incluir_nacionales = payload.incluir_nacionales
    preference.usar_territorio_empresa = payload.usar_territorio_empresa
    db.query(SubvencionSuscripcion).filter(
        SubvencionSuscripcion.client_id == client.id,
    ).delete(synchronize_session=False)
    for level, code, name in validated:
        db.add(SubvencionSuscripcion(
            client_id=client.id, nivel=level, codigo=code, nombre=name,
        ))
    db.commit()
    return preferencias(request, db)


@router.get("/territorios")
def territorios(request: Request, q: str = Query("", max_length=100), db: Session = Depends(_db)):
    client = _authenticated_client(request, db)
    org = _org_for_client(db, client)
    result = [
        {"nivel": "AUTONOMICA", "codigo": code, "nombre": name}
        for code, name in CCAA.items()
    ]
    provinces: dict[str, str] = dict(PROVINCIAS)
    municipalities: dict[str, str] = {}
    for call in db.scalars(select(SubvencionConvocatoria).where(SubvencionConvocatoria.visible.is_(True))).all():
        for code in call.provincias_json or []:
            provinces.setdefault(code, code)
        if call.municipio_slug:
            ccaa_code = (call.ccaa_json or [""])[0]
            code = f"{ccaa_code}:{call.municipio_slug}" if ccaa_code else call.municipio_slug
            region = CCAA.get(ccaa_code, "")
            municipalities[code] = (
                f"{call.municipio_nombre} ({region})" if region else call.municipio_nombre
            )
    home = territorio_organizacion(org)
    if home["provincia"]:
        provinces[home["provincia"]] = home["provincia_nombre"]
    if home["municipio_slug"]:
        code = (
            f"{home['ccaa']}:{home['municipio_slug']}"
            if home["ccaa"] else home["municipio_slug"]
        )
        municipalities[code] = (
            f"{home['municipio']} ({home['ccaa_nombre']})"
            if home["ccaa_nombre"] else home["municipio"]
        )
    result.extend({"nivel": "PROVINCIAL", "codigo": k, "nombre": v} for k, v in sorted(provinces.items(), key=lambda x: x[1]))
    result.extend({"nivel": "MUNICIPAL", "codigo": k, "nombre": v} for k, v in sorted(municipalities.items(), key=lambda x: x[1]))
    needle = q.strip().casefold()
    return [item for item in result if not needle or needle in item["nombre"].casefold()][:200]


@router.get("/{codigo}")
def detalle(codigo: str, request: Request, db: Session = Depends(_db)):
    client = _authenticated_client(request, db)
    _org_for_client(db, client)
    call = db.scalar(select(SubvencionConvocatoria).where(
        SubvencionConvocatoria.codigo_bdns == codigo,
        SubvencionConvocatoria.visible.is_(True),
    ))
    if not call:
        raise HTTPException(404, "Convocatoria no encontrada")
    return _detail(call)


def _run_background() -> None:
    with SessionLocal() as db:
        SubvencionesService(db).ejecutar()


@router.get("/internal/dashboard", dependencies=[Depends(require_workstation_or_internal)])
def dashboard(db: Session = Depends(_db)):
    config = db.get(SubvencionConfiguracion, "global")
    last = db.scalar(select(SubvencionEjecucion).order_by(SubvencionEjecucion.id.desc()).limit(1))
    return {
        "configuracion": {
            "global_activo": get_settings().client_subsidies_enabled,
            "servicio_activo": True if config is None else config.servicio_activo,
            "avisos_activos": False if config is None else config.avisos_activos,
            "resumenes_ia_activos": False if config is None else config.resumenes_ia_activos,
            "ia_configurada": bool(os.getenv("ANTHROPIC_API_KEY", "").strip()),
        },
        "totales": {
            "convocatorias": db.scalar(select(func.count()).select_from(SubvencionConvocatoria)) or 0,
            "vigentes": db.scalar(select(func.count()).select_from(SubvencionConvocatoria).where(
                SubvencionConvocatoria.visible.is_(True),
                SubvencionConvocatoria.abierto.is_not(False),
                or_(SubvencionConvocatoria.fecha_fin.is_(None), SubvencionConvocatoria.fecha_fin >= date.today()),
            )) or 0,
            "suscriptores": db.scalar(
                select(func.count())
                .select_from(SubvencionPreferencia)
                .join(MessagingClient, MessagingClient.id == SubvencionPreferencia.client_id)
                .join(
                    MessagingOrganization,
                    MessagingOrganization.id == MessagingClient.organization_id,
                )
                .where(
                    SubvencionPreferencia.notificaciones_activas.is_(True),
                    MessagingClient.active.is_(True),
                    MessagingOrganization.active.is_(True),
                    MessagingOrganization.client_subsidies_enabled.is_(True),
                )
            ) or 0,
            "fallos_entrega": db.scalar(select(func.count()).select_from(SubvencionEntrega).where(
                SubvencionEntrega.estado == "fallido",
            )) or 0,
        },
        "ultima_ejecucion": None if not last else {
            "id": last.id, "inicio": last.inicio, "fin": last.fin, "estado": last.estado,
            "leidas": last.leidas, "nuevas": last.nuevas, "actualizadas": last.actualizadas,
            "resumidas": last.resumidas, "avisos_enviados": last.avisos_enviados,
            "detalle": last.detalle,
        },
    }


@router.put("/internal/configuracion")
def guardar_configuracion(
    payload: ConfiguracionIn,
    actor: str = Depends(require_workstation_or_internal),
    db: Session = Depends(_db),
):
    config = db.get(SubvencionConfiguracion, "global") or SubvencionConfiguracion(id="global")
    config.servicio_activo = payload.servicio_activo
    config.avisos_activos = payload.avisos_activos
    config.resumenes_ia_activos = payload.resumenes_ia_activos
    config.updated_by = actor
    db.add(config)
    db.commit()
    return {"ok": True}


@router.post("/internal/sincronizar", status_code=202, dependencies=[Depends(require_workstation_or_internal)])
def sincronizar(background: BackgroundTasks):
    background.add_task(_run_background)
    return {"lanzada": True}


@router.get("/internal/convocatorias", dependencies=[Depends(require_workstation_or_internal)])
def convocatorias_internas(
    q: str = Query("", max_length=120), limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(_db),
):
    stmt = select(SubvencionConvocatoria)
    if q.strip():
        stmt = stmt.where(SubvencionConvocatoria.titulo.ilike(f"%{q.strip()}%"))
    rows = db.scalars(stmt.order_by(SubvencionConvocatoria.fecha_recepcion.desc()).limit(limit)).all()
    return [{**_summary(x), "visible": x.visible, "resumen_estado": x.resumen_estado} for x in rows]


@router.patch("/internal/convocatorias/{codigo}", dependencies=[Depends(require_workstation_or_internal)])
def editar_convocatoria(codigo: str, payload: ConvocatoriaPatch, db: Session = Depends(_db)):
    call = db.scalar(select(SubvencionConvocatoria).where(SubvencionConvocatoria.codigo_bdns == codigo))
    if not call:
        raise HTTPException(404, "Convocatoria no encontrada")
    if payload.visible is not None:
        call.visible = payload.visible
    if payload.revisada is not None:
        call.revisada = payload.revisada
    if payload.rehacer_resumen:
        call.resumen_estado = "pendiente"
        call.hash_resumen = ""
    db.commit()
    return {**_summary(call), "visible": call.visible, "resumen_estado": call.resumen_estado}


@router.get("/internal/suscripciones", dependencies=[Depends(require_workstation_or_internal)])
def suscripciones_internas(db: Session = Depends(_db)):
    rows = []
    clients = db.execute(
        select(MessagingClient, MessagingOrganization)
        .join(
            MessagingOrganization,
            MessagingOrganization.id == MessagingClient.organization_id,
        )
        .where(
            MessagingClient.active.is_(True),
            MessagingOrganization.active.is_(True),
            MessagingOrganization.client_subsidies_enabled.is_(True),
        )
        .order_by(MessagingOrganization.company_code, MessagingClient.email)
    ).all()
    for client, org in clients:
        preference = _preference(db, client.id)
        rows.append({
            "client_id": client.id, "usuario": client.name, "email": client.email,
            "empresa": org.name, "codigo_empresa": org.company_code,
            "configurada": preference is not None,
            "notificaciones_activas": bool(preference and preference.notificaciones_activas),
            "incluir_nacionales": None if preference is None else preference.incluir_nacionales,
            "usar_territorio_empresa": None if preference is None else preference.usar_territorio_empresa,
            "territorios": [x.nombre for x in _subscriptions(db, client.id)],
        })
    return rows


@router.get("/internal/envios", dependencies=[Depends(require_workstation_or_internal)])
def envios_internos(limit: int = Query(300, ge=1, le=1000), db: Session = Depends(_db)):
    rows = db.scalars(select(SubvencionEntrega).order_by(SubvencionEntrega.actualizada_at.desc()).limit(limit)).all()
    result = []
    for item in rows:
        client = db.get(MessagingClient, item.client_id)
        call = db.get(SubvencionConvocatoria, item.convocatoria_id)
        result.append({
            "id": item.id, "usuario": client.name if client else "", "email": client.email if client else "",
            "codigo_bdns": call.codigo_bdns if call else "", "titulo": call.titulo if call else "",
            "estado": item.estado, "intentos": item.intentos,
            "dispositivos_enviados": item.dispositivos_enviados,
            "ultimo_error": item.ultimo_error, "enviada_at": item.enviada_at,
        })
    return result


@router.get("/internal/organizaciones", dependencies=[Depends(require_workstation_or_internal)])
def organizaciones_internas(db: Session = Depends(_db)):
    result = []
    for org in db.scalars(select(MessagingOrganization).order_by(
        MessagingOrganization.company_code,
    )).all():
        clients = db.scalars(select(MessagingClient).where(
            MessagingClient.organization_id == org.id,
            MessagingClient.active.is_(True),
        )).all()
        result.append({
            "codigo_empresa": org.company_code,
            "empresa": org.name,
            "activa": bool(getattr(org, "client_subsidies_enabled", False)),
            "efectiva": is_subsidies_enabled(org),
            "usuarios_activos": len(clients),
            "territorio": territorio_organizacion(org),
        })
    return result


@router.patch(
    "/internal/organizaciones/{company_code}",
)
def editar_organizacion(
    company_code: str,
    payload: OrganizacionPatch,
    actor: str = Depends(require_workstation_or_internal),
    db: Session = Depends(_db),
):
    org = db.scalar(select(MessagingOrganization).where(
        MessagingOrganization.company_code == company_code,
    ))
    if not org:
        raise HTTPException(404, "Empresa no encontrada")
    previous = bool(getattr(org, "client_subsidies_enabled", False))
    org.client_subsidies_enabled = payload.activa
    if previous != payload.activa:
        db.add(ClientFeatureFlagAudit(
            organization_id=org.id,
            flag_name="client_subsidies_enabled",
            old_value=previous,
            new_value=payload.activa,
            changed_by=actor,
        ))
    db.commit()
    return {
        "codigo_empresa": org.company_code,
        "empresa": org.name,
        "activa": bool(org.client_subsidies_enabled),
        "efectiva": is_subsidies_enabled(org),
    }


@router.patch(
    "/internal/organizaciones",
)
def editar_organizaciones(
    payload: OrganizacionesBulkPatch,
    actor: str = Depends(require_workstation_or_internal),
    db: Session = Depends(_db),
):
    codes = list(dict.fromkeys(code.strip() for code in payload.codigos if code.strip()))
    if not codes:
        raise HTTPException(422, "Seleccione al menos una empresa")
    organizations = db.scalars(select(MessagingOrganization).where(
        MessagingOrganization.company_code.in_(codes),
    )).all()
    by_code = {item.company_code: item for item in organizations}
    missing = [code for code in codes if code not in by_code]
    if missing:
        raise HTTPException(404, f"Empresas no encontradas: {', '.join(missing[:10])}")
    changed = 0
    for code in codes:
        org = by_code[code]
        previous = bool(getattr(org, "client_subsidies_enabled", False))
        if previous == payload.activa:
            continue
        org.client_subsidies_enabled = payload.activa
        db.add(ClientFeatureFlagAudit(
            organization_id=org.id,
            flag_name="client_subsidies_enabled",
            old_value=previous,
            new_value=payload.activa,
            changed_by=actor,
        ))
        changed += 1
    db.commit()
    return {"ok": True, "seleccionadas": len(codes), "actualizadas": changed}
