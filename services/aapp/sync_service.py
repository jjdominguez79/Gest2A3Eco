"""
Orquestador de sincronizacion de notificaciones.

Sustituye la "sincronizacion simulada" de la UI por el flujo real:
  1. Resuelve el certificado del cliente (CertStore, certificado unico).
  2. Localiza el conector del organismo (registro de base.py); si el organismo
     no tiene conector propio, usa DEHu (que centraliza AEAT, Seg. Social, etc.).
  3. Ejecuta el conector -> lista de NotificacionDTO.
  4. Persiste en notif_bandeja (idempotente, sin duplicar) y registra el
     resultado en notif_sync_logs. Actualiza ultima_consulta del buzon.

La UI solo tiene que llamar a sincronizar_buzon() / sincronizar_buzones().
"""
from __future__ import annotations

import hashlib
import json
import traceback
from dataclasses import dataclass, field
from datetime import datetime

from .base import OpcionesSync, obtener_conector
from .cert_store import CertStore, CertError

# Importar conectores para que se registren (efecto de import).
from . import dehu_playwright  # noqa: F401  (registra ConectorDEHU)


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

        # 2) Conector. Si el organismo no tiene conector propio, se usa DEHu, que
        # centraliza las notificaciones de AEAT, Seguridad Social y demas.
        conector = obtener_conector(org_codigo) or obtener_conector("DEHU")
        if conector is None:
            raise CertError(
                f"No hay conector disponible para el organismo '{org_codigo or '(desconocido)'}'."
            )

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


def _existe_bandeja(gestor, codigo_empresa: str, item_id: str) -> bool:
    try:
        cur = gestor.conn.execute(
            "SELECT 1 FROM notif_bandeja WHERE id=? AND codigo_empresa=?",
            (item_id, codigo_empresa),
        )
        return cur.fetchone() is not None
    except Exception:
        return False
