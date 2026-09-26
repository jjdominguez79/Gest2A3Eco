"""
Orquestador de sincronizacion de notificaciones.

Sustituye la "sincronizacion simulada" de la UI por el flujo real:
  1. Resuelve el certificado del cliente (CertStore, certificado unico).
  2. Ejecuta exclusivamente el conector DEHu.
  3. Ejecuta el conector -> lista de NotificacionDTO.
  4. Persiste en notif_bandeja (idempotente, sin duplicar) y registra el
     resultado en notif_sync_logs. Actualiza ultima_consulta del buzon.

La UI solo tiene que llamar a sincronizar_buzon() / sincronizar_buzones().
"""
from __future__ import annotations

import hashlib
import json
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from .base import OpcionesSync, obtener_conector
from .cert_store import CertStore, CertError
from utils.estados_dehu import es_pendiente_dehu, normalizar_estado_dehu

# Importar conectores para que se registren (efecto de import).
from . import dehu_playwright  # noqa: F401  (registra ConectorDEHU)
from . import dev_notifications  # noqa: F401  (registra ConectorDEV)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class ResultadoBuzon:
    buzon_id: str
    buzon_nombre: str
    ok: bool
    nuevas: int = 0
    total_detectadas: int = 0
    mensaje: str = ""
    error_detalle: str | None = None


@dataclass
class ResultadoGlobal:
    resultados: list = field(default_factory=list)

    @property
    def total_nuevas(self) -> int:
        return sum(r.nuevas for r in self.resultados)

    @property
    def con_error(self) -> list:
        return [r for r in self.resultados if not r.ok]


@dataclass
class ResultadoImportacionCentral:
    total: int = 0
    nuevas: int = 0
    actualizadas: int = 0
    omitidas: int = 0


@dataclass
class ResultadoActualizacionDehu(ResultadoImportacionCentral):
    encoladas: int = 0
    completadas: int = 0
    fallidas: int = 0
    pendientes: int = 0
    errores: list[str] = field(default_factory=list)


def _bandeja_id(codigo_empresa: str, organismo_codigo: str, referencia: str) -> str:
    base = f"{codigo_empresa}|{organismo_codigo}|{referencia}".encode("utf-8", "ignore")
    return "nb_" + hashlib.sha1(base).hexdigest()[:24]


def sincronizar_buzon(gestor, buzon: dict, opciones: OpcionesSync | None = None,
                      ejercicio: int | None = None) -> ResultadoBuzon:
    """Sincroniza un unico buzon y persiste resultados. No lanza excepciones."""
    opciones = opciones or OpcionesSync()
    ejercicio = ejercicio or datetime.now().year
    nombre = buzon.get("nombre", buzon.get("id", "?"))
    org_codigo = (buzon.get("organismo_codigo") or "").upper()
    org_id = buzon.get("organismo_id")
    codigo_empresa = buzon.get("codigo_empresa")

    log_resultado = "OK"
    error_detalle = None
    nuevas = 0
    total = 0
    mensaje = ""
    ok = True

    try:
        # 1) Certificado (unico del cliente)
        material = CertStore(gestor).material_para_buzon(buzon)

        # 2) Cada buzon usa su conector real; nunca se redirige DEV a DEHu.
        if org_codigo not in {"DEHU", "DEV"}:
            raise CertError(
                f"El buzon '{org_codigo or '(sin codigo)'} ya no esta soportado. "
                "Configura el cliente con DEHu o DGT/DEV."
            )
        conector = obtener_conector(org_codigo)
        if conector is None:
            raise CertError(
                f"No hay conector disponible para el organismo '{org_codigo or '(desconocido)'}'."
            )

        # Filtrar al NIF/CIF del cliente: evita mezclar y duplicar cuando el
        # certificado ve notificaciones de varios titulares (p.ej. RED de la SS).
        try:
            _emp = gestor.get_empresa(codigo_empresa)
            opciones.nif_filtro = (_emp or {}).get("cif") or None
        except Exception:
            opciones.nif_filtro = None

        # 3) Ejecutar
        res = conector.sincronizar(buzon, material, opciones)
        total = res.total
        if not res.ok:
            ok = False
            log_resultado = "ERROR"
            mensaje = res.mensaje
            error_detalle = res.error_detalle
        else:
            # 4) Persistir en bandeja (idempotente)
            for dto in res.notificaciones:
                item_id = _bandeja_id(codigo_empresa, org_codigo, dto.dedup_key())
                existe = _existe_bandeja(gestor, codigo_empresa, item_id)
                gestor.upsert_notif_bandeja_item({
                    "id": item_id,
                    "codigo_empresa": codigo_empresa,
                    "ejercicio": ejercicio,
                    "buzon_id": buzon.get("id"),
                    "organismo_id": org_id,
                    "asunto": dto.asunto,
                    "descripcion": dto.descripcion,
                    "tipo_acto": dto.tipo_acto,
                    "referencia": dto.referencia,
                    "nif_interesado": dto.nif_interesado,
                    "nombre_interesado": dto.nombre_interesado,
                    "fecha_puesta_disposicion": dto.fecha_puesta_disposicion,
                    "fecha_vencimiento": dto.fecha_vencimiento,
                    "estado": dto.estado,
                    "pdf_path": dto.pdf_path,
                    "metadatos_json": json.dumps(dto.metadatos, ensure_ascii=False),
                })
                if not existe:
                    nuevas += 1
            mensaje = f"{total} detectada(s), {nuevas} nueva(s)."
    except Exception as exc:
        ok = False
        log_resultado = "ERROR"
        mensaje = str(exc)
        error_detalle = traceback.format_exc()

    # Registrar log + actualizar buzon (siempre)
    ahora = _now()
    try:
        gestor.upsert_notif_sync_log({
            "codigo_empresa": codigo_empresa,
            "organismo_id": org_id,
            "buzon_id": buzon.get("id"),
            "fecha_hora": ahora,
            "resultado": log_resultado,
            "error_detalle": (error_detalle or "")[:4000] if error_detalle else None,
            "notificaciones_detectadas": total,
        })
        buzon_upd = dict(buzon)
        buzon_upd["ultima_consulta"] = ahora
        gestor.upsert_notif_buzon(buzon_upd)
    except Exception:
        pass

    return ResultadoBuzon(
        buzon_id=buzon.get("id", ""),
        buzon_nombre=nombre,
        ok=ok,
        nuevas=nuevas,
        total_detectadas=total,
        mensaje=mensaje,
        error_detalle=error_detalle,
    )


def sincronizar_buzones(gestor, buzones: list, opciones: OpcionesSync | None = None,
                        ejercicio: int | None = None, solo_activos: bool = True) -> ResultadoGlobal:
    glob = ResultadoGlobal()
    for b in buzones:
        if solo_activos and not int(b.get("activo", 1)):
            continue
        glob.resultados.append(sincronizar_buzon(gestor, b, opciones, ejercicio))
    return glob


def importar_bandeja_central(
    gestor, *, company_code: str = "", backend=None,
) -> ResultadoImportacionCentral:
    """Importa en PostgreSQL local la bandeja detectada por el worker AAPP."""
    if backend is None:
        from services.backend_client_service import BackendClientService
        backend = BackendClientService()
    rows = [
        {**row, "provider": "DEHU"}
        for row in backend.list_dehu_notifications(company_code=company_code, limit=2000)
    ]
    try:
        rows.extend(
            {**row, "provider": "DEV"}
            for row in backend.list_dev_notifications(company_code=company_code, limit=2000)
        )
    except Exception:
        # Compatibilidad durante el despliegue escalonado: DEHu sigue
        # importandose aunque el backend aun no exponga DGT/DEV.
        pass
    buzones = gestor.listar_notif_buzones_global()
    by_id = {str(row.get("id")): row for row in buzones}
    by_company = {}
    for row in buzones:
        provider = (row.get("organismo_codigo") or "").upper()
        if provider in {"DEHU", "DEV"}:
            by_company.setdefault((str(row.get("codigo_empresa") or ""), provider), row)
    result = ResultadoImportacionCentral(total=len(rows))
    for remote in rows:
        codigo = str(remote.get("company_code") or "")
        provider = str(remote.get("provider") or "DEHU").upper()
        buzon = (
            by_id.get(str(remote.get("mailbox_id") or ""))
            or by_company.get((codigo, provider))
        )
        if not codigo or not buzon:
            result.omitidas += 1
            continue
        reference = str(remote.get("reference") or "").strip()
        if not reference:
            result.omitidas += 1
            continue
        item_id = _bandeja_id(codigo, provider, reference)
        existing = gestor.get_notif_bandeja_item(item_id)
        if (
            existing
            and not es_pendiente_dehu(existing.get("estado"))
            and es_pendiente_dehu(remote.get("status"), remote.get("source_endpoint"))
        ):
            # Una respuesta pendiente atrasada nunca reabre un estado terminal.
            result.omitidas += 1
            continue
        metadata = dict(remote.get("metadata") or {})
        metadata.update({
            "backend_notification_id": remote.get("id"),
            "backend_document_id": remote.get("document_id"),
            "request_id": remote.get("request_id"),
            "last_seen_at": remote.get("last_seen_at"),
            "issuing_body": remote.get("issuing_body") or "",
            "issuing_body_source": remote.get("issuing_body_source") or "",
        })
        gestor.upsert_notif_bandeja_item({
            "id": item_id,
            "codigo_empresa": codigo,
            "ejercicio": _notification_year(remote),
            "buzon_id": buzon.get("id"),
            "organismo_id": buzon.get("organismo_id"),
            "asunto": remote.get("subject") or "(sin asunto)",
            "descripcion": (
                remote.get("issuing_body") or remote.get("description") or ""
            ),
            "tipo_acto": remote.get("action_type") or "",
            "referencia": reference,
            "nif_interesado": remote.get("holder_tax_id") or "",
            "nombre_interesado": remote.get("holder_name") or "",
            "fecha_puesta_disposicion": remote.get("available_date") or None,
            "fecha_vencimiento": remote.get("expiration_date") or None,
            "estado": remote.get("status") or "PENDIENTE",
            "pdf_path": (existing or {}).get("pdf_path"),
            "metadatos_json": json.dumps(metadata, ensure_ascii=False, default=str),
        })
        if existing is None:
            result.nuevas += 1
        elif normalizar_estado_dehu(existing.get("estado")) != normalizar_estado_dehu(
            remote.get("status")
        ):
            result.actualizadas += 1
    return result


def actualizar_bandeja_desde_dehu(
    gestor, *, company_code: str = "", backend=None,
    timeout_seconds: float = 240, poll_interval: float = 2,
) -> ResultadoActualizacionDehu:
    """Solicita una lectura real de DEHu y despues importa su resultado.

    Al abrir la pantalla se sigue usando :func:`importar_bandeja_central`, que
    es una recarga barata. Esta funcion queda reservada para la pulsacion
    manual: encola el worker, espera sus solicitudes y solo entonces refresca
    la replica local. Nunca acepta avisos ni solicita documentos.
    """
    if backend is None:
        from services.backend_client_service import BackendClientService
        backend = BackendClientService()

    company_code = str(company_code or "").strip()
    buzones = [
        row for row in gestor.listar_notif_buzones_global()
        if str(row.get("organismo_codigo") or "").upper() == "DEHU"
        and int(row.get("activo", 1) or 0)
        and (not company_code or str(row.get("codigo_empresa") or "") == company_code)
    ]
    por_empresa = {}
    for buzon in buzones:
        codigo = str(buzon.get("codigo_empresa") or "").strip()
        if codigo:
            por_empresa.setdefault(codigo, buzon)

    solicitudes: dict[str, str] = {}
    errores: list[str] = []
    for codigo, buzon in por_empresa.items():
        try:
            empresa = gestor.get_empresa(codigo) or {}
            solicitud = backend.create_certificate_request(
                company_code=codigo,
                certificate_type="DEHU_SYNC",
                parameters={
                    "company_code": codigo,
                    "tax_id": empresa.get("cif") or "",
                    "mailbox_id": buzon.get("id") or "",
                    "mailbox_name": buzon.get("nombre") or "DEHu",
                    "download_mode": "SOLO_DETECTAR",
                },
                idempotency_key=f"desktop-dehu-{uuid.uuid4().hex}",
            )
            request_id = str(solicitud.get("id") or "")
            if request_id:
                solicitudes[request_id] = codigo
            else:
                errores.append(f"{codigo}: el backend no devolvio el identificador")
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            activa = None
            if status_code == 409:
                try:
                    activa = next((
                        row for row in backend.list_certificate_requests(
                            company_code=codigo, limit=50,
                        )
                        if row.get("certificate_type") == "DEHU_SYNC"
                        and str(row.get("status") or "").lower() in {
                            "queued", "processing", "needs_action", "awaiting_issuance",
                        }
                    ), None)
                except Exception:
                    activa = None
            if activa and activa.get("id"):
                estado_activo = str(activa.get("status") or "").lower()
                if (
                    estado_activo == "needs_action"
                    or (
                        estado_activo in {"queued", "awaiting_issuance"}
                        and activa.get("next_attempt_at")
                    )
                ):
                    # Una pulsacion manual significa "consultar ahora". Si el
                    # worker habia aplazado un fallo transitorio, adelantar el
                    # mismo registro en vez de crear otro o esperar el backoff.
                    activa = backend.retry_certificate_request(str(activa["id"]))
                solicitudes[str(activa["id"])] = codigo
            else:
                errores.append(f"{codigo}: {exc}")

    estados: dict[str, str] = {}
    detalles: dict[str, dict] = {}
    limite = time.monotonic() + max(0.0, float(timeout_seconds))
    while solicitudes:
        try:
            recientes = backend.list_certificate_requests(
                company_code=company_code, limit=500,
            )
            estados = {
                str(row.get("id") or ""): str(row.get("status") or "").lower()
                for row in recientes
                if str(row.get("id") or "") in solicitudes
            }
            detalles = {
                str(row.get("id") or ""): row
                for row in recientes
                if str(row.get("id") or "") in solicitudes
            }
        except Exception as exc:
            errores.append(f"No se pudo comprobar el resultado: {exc}")
            break
        ejecutandose = {
            request_id for request_id in solicitudes
            if estados.get(request_id, "queued") in {
                "queued", "processing", "awaiting_issuance",
            }
        }
        if not ejecutandose or time.monotonic() >= limite:
            break
        time.sleep(max(0.05, float(poll_interval)))

    importacion = importar_bandeja_central(
        gestor, company_code=company_code, backend=backend,
    )
    completadas = sum(
        1 for request_id in solicitudes if estados.get(request_id) == "completed"
    )
    fallidas = sum(
        1 for request_id in solicitudes
        if estados.get(request_id) in {"failed", "needs_action", "cancelled"}
    )
    pendientes = len(solicitudes) - completadas - fallidas
    for request_id, codigo in solicitudes.items():
        detalle = detalles.get(request_id) or {}
        if estados.get(request_id) in {"queued", "awaiting_issuance"} and detalle.get("error_message"):
            mensaje_error = str(detalle["error_message"]).splitlines()[0][:500]
            errores.append(
                f"{codigo}: consulta pendiente de reintento: {mensaje_error}"
            )
    return ResultadoActualizacionDehu(
        total=importacion.total,
        nuevas=importacion.nuevas,
        actualizadas=importacion.actualizadas,
        omitidas=importacion.omitidas,
        encoladas=len(solicitudes),
        completadas=completadas,
        fallidas=fallidas,
        pendientes=pendientes,
        errores=errores,
    )


def _notification_year(item: dict) -> int:
    value = str(item.get("available_date") or "")
    try:
        return int(value[:4]) if len(value) >= 4 else datetime.now().year
    except ValueError:
        return datetime.now().year


def _existe_bandeja(gestor, codigo_empresa: str, item_id: str) -> bool:
    try:
        cur = gestor.conn.execute(
            "SELECT 1 FROM notif_bandeja WHERE id=? AND codigo_empresa=?",
            (item_id, codigo_empresa),
        )
        return cur.fetchone() is not None
    except Exception:
        return False
