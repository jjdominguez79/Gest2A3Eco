"""
Modelo comun e interfaz para los conectores de organismos (AAPP).

Un "conector" sabe hablar con un organismo concreto (DEHu, Seguridad Social,
etc.) usando el certificado digital de un cliente, y devuelve la lista de
notificaciones detectadas. La orquestacion (guardar en bandeja, logs, etc.)
vive en sync_service.py; aqui solo se define el contrato.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class NotificacionDTO:
    """Una notificacion detectada en el buzon de un organismo."""
    referencia: str                      # identificador unico en el organismo (clave de deduplicacion)
    asunto: str = ""
    descripcion: str | None = None
    tipo_acto: str | None = None
    nif_interesado: str | None = None
    nombre_interesado: str | None = None
    fecha_puesta_disposicion: str | None = None
    fecha_vencimiento: str | None = None
    estado: str = "PENDIENTE"
    pdf_path: str | None = None
    metadatos: dict = field(default_factory=dict)

    def dedup_key(self) -> str:
        return (self.referencia or f"{self.nif_interesado}|{self.asunto}|{self.fecha_puesta_disposicion}").strip()


@dataclass
class ResultadoSync:
    ok: bool
    organismo_codigo: str
    notificaciones: list = field(default_factory=list)
    mensaje: str = ""
    error_detalle: str | None = None

    @property
    def total(self) -> int:
        return len(self.notificaciones)


@dataclass
class OpcionesSync:
    """Ajustes de una ejecucion de sincronizacion."""
    headless: bool = True
    descargar_pdf: bool = False
    carpeta_descargas: str | None = None
    timeout_ms: int = 45000
    modo_diagnostico: bool = False
    carpeta_diagnostico: str | None = None
    log: Callable[[str], None] | None = None
    # Modo aprendizaje: segundos de espera para completar el login con el
    # certificado MANUALMENTE en la ventana (requiere headless=False). Mientras
    # espera, el conector captura las llamadas de red (API del SPA).
    pausa_login_segundos: int = 0
    # Origenes adicionales para los que ofrecer el certificado de cliente
    # (Cl@ve/@firma piden el certificado en SU dominio, no en el de DEHu).
    origenes_certificado: list = field(default_factory=list)
    capturar_red: bool = True
    # Filtrar las notificaciones al NIF/CIF de este cliente (evita mezclar y
    # duplicar cuando el certificado ve las de varios titulares, p.ej. RED de la SS).
    nif_filtro: str | None = None
    # Datos de Seguridad Social del cliente (NAF/CCC) para tramites TGSS.
    datos_ss: dict = field(default_factory=dict)
    # Ruta destino donde el proveedor debe guardar el PDF del certificado.
    ruta_pdf_destino: str | None = None

    def trace(self, msg: str) -> None:
        if self.log:
            try:
                self.log(msg)
            except Exception:
                pass


class ConectorOrganismo:
    """Interfaz que implementa cada conector concreto."""

    #: codigo del organismo tal como aparece en notif_organismos.codigo
    codigo_organismo: str = ""

    def sincronizar(self, buzon: dict, cert_material, opciones: OpcionesSync) -> ResultadoSync:
        raise NotImplementedError


# ── Registro de conectores ────────────────────────────────────────────────
_REGISTRO: dict = {}


def registrar_conector(conector: ConectorOrganismo) -> None:
    _REGISTRO[conector.codigo_organismo.upper()] = conector


def obtener_conector(codigo_organismo):
    if not codigo_organismo:
        return None
    return _REGISTRO.get(codigo_organismo.upper())


def conectores_disponibles():
    return sorted(_REGISTRO.keys())
