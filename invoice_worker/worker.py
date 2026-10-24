"""Worker de escritorio: sincronizacion contable de la facturacion online.

Desde la Etapa 8 (ADR 0001), su UNICA responsabilidad respecto a las
facturas creadas en Flutter es:

1. Consumir clientes pendientes de integrar (tercero/subcuenta 430).
2. Consumir facturas pendientes de importar a contabilidad.
3. Crear o vincular terceros.
4. Crear la relacion tercero-empresa.
5. Asignar subcuenta 430 de forma atomica (advisory lock + UNIQUE,
   seccion 17 del encargo).
6. Importar la factura a ``facturas_emitidas_docs``.
7. Comunicar el resultado al backend.

Ya NO genera PDF, NO envia email, NO envia FCM, NO remite nada a la AEAT
para facturas APP: todo eso es responsabilidad exclusiva de billing_worker
(cloud, ver billing_worker/). El worker NO usa Graph ni Firebase
directamente; los secretos de proveedores permanecen en el backend.

Cada paso es idempotente. Las caidas no duplican datos.
"""

from __future__ import annotations

import json
import logging
import re
import signal
import sys
import time
from datetime import datetime
from decimal import Decimal
from typing import Protocol

import requests

from invoice_worker.config import WorkerConfig

logger = logging.getLogger(__name__)

# Backoff maximo entre reintentos (5 minutos)
_MAX_BACKOFF_SECONDS = 300

# Intentos ante conflicto de UNIQUE(codigo_empresa, subcuenta) al asignar
# una subcuenta 430 nueva (seccion 17 del encargo).
_SUBCUENTA_430_MAX_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# Protocolos para inyeccion de dependencias (tests usan adaptadores simulados)
# ---------------------------------------------------------------------------

class DesktopGestor(Protocol):
    """Interfaz minima del gestor de datos del escritorio."""

    def get_tercero_by_nif_normalizado(self, nif: str) -> dict | None: ...
    def upsert_tercero(self, tercero: dict) -> str: ...
    def get_tercero_empresa(
        self, codigo_empresa: str, tercero_id: str, ejercicio: int,
    ) -> dict | None: ...
    def upsert_tercero_empresa(self, rel: dict) -> None: ...
    def upsert_maestro_subcuenta(self, datos: dict) -> int: ...
    def get_maestro_subcuenta_por_subcuenta(self, codigo: str, sub: str) -> dict | None: ...
    def listar_maestro_subcuentas_empresa(self, codigo: str, tipo: str | None = None, activo: bool = True) -> list: ...
    def upsert_factura_emitida(self, factura: dict) -> str: ...
    def enviar_facturas_emitidas_a_contabilidad(
        self, codigo_empresa: str, ejercicio: int, ids: list,
    ) -> None: ...
    def get_empresa(self, codigo: str) -> dict | None: ...
    def advisory_lock_empresa_430(self, codigo_empresa: str) -> None: ...


# ---------------------------------------------------------------------------
# Adaptadores de produccion
# ---------------------------------------------------------------------------

class RealDesktopGestor:
    """Conecta con el PostgreSQL compartido del escritorio."""

    def __init__(self, dsn: str) -> None:
        from models.gestor_postgres import GestorPostgres
        self._gestor = GestorPostgres(dsn)

    def __getattr__(self, name: str):
        return getattr(self._gestor, name)


# ---------------------------------------------------------------------------
# Worker principal
# ---------------------------------------------------------------------------

class InvoiceWorker:
    def __init__(
        self,
        config: WorkerConfig,
        *,
        gestor: DesktopGestor | None = None,
    ) -> None:
        self.config = config
        self._session = requests.Session()
        self._session.headers["x-api-key"] = config.api_token

        # Adaptador inyectable (produccion usa el real)
        self._gestor = gestor

        # Control de parada
        self._running = True
        self._consecutive_errors = 0

    def _ensure_gestor(self) -> DesktopGestor:
        if self._gestor is None:
            if not self.config.desktop_dsn:
                raise RuntimeError(
                    "DSN de PostgreSQL no configurado; "
                    "ejecuta la configuracion de credenciales"
                )
            self._gestor = RealDesktopGestor(self.config.desktop_dsn)
        return self._gestor

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def stop(self, signum: int | None = None, frame=None) -> None:
        """Apagado controlado: el bucle terminara tras el paso actual."""
        logger.info(
            "Senal de parada recibida (signal=%s), finalizando...",
            signum,
        )
        self._running = False

    def run_forever(self) -> None:
        """Bucle principal del worker con backoff y apagado controlado."""
        logger.info(
            "Worker %s iniciado (poll=%ds, lease=%dm, max_retries=%d)",
            self.config.worker_id,
            self.config.poll_interval_seconds,
            self.config.lease_minutes,
            self.config.max_retries,
        )

        # Registrar signals para apagado controlado
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        if sys.platform == "win32":
            try:
                signal.signal(signal.SIGBREAK, self.stop)  # type: ignore[attr-defined]
            except (AttributeError, OSError):
                pass

        while self._running:
            try:
                self._heartbeat()
                customer_claim = self._claim_customer()
                if customer_claim:
                    self._process_customer(customer_claim)
                    self._consecutive_errors = 0
                    continue
                claimed = self._claim_accounting()
                if claimed:
                    self._process_accounting(claimed)
                    self._consecutive_errors = 0
                else:
                    self._sleep(self.config.poll_interval_seconds)
            except KeyboardInterrupt:
                logger.info("Worker detenido por usuario")
                break
            except Exception:
                self._consecutive_errors += 1
                logger.exception("Error en bucle principal")
                backoff = min(
                    self.config.poll_interval_seconds * (2 ** self._consecutive_errors),
                    _MAX_BACKOFF_SECONDS,
                )
                logger.info(
                    "Esperando %ds antes de reintentar (errores consecutivos: %d)",
                    backoff, self._consecutive_errors,
                )
                self._sleep(backoff)

        logger.info("Worker %s detenido", self.config.worker_id)

    def _sleep(self, seconds: float) -> None:
        """Sleep que respeta la senal de parada."""
        end = time.monotonic() + seconds
        while self._running and time.monotonic() < end:
            time.sleep(min(1.0, end - time.monotonic()))

    def _heartbeat(self) -> None:
        """Latido best-effort para observabilidad (seccion 22 del encargo)."""
        try:
            self._session.post(
                f"{self.config.api_base_url}/worker/accounting/heartbeat",
                json={"instance_id": self.config.worker_id},
                timeout=10,
            )
        except Exception:
            logger.debug("No se pudo enviar el heartbeat (no bloqueante)", exc_info=True)

    # ------------------------------------------------------------------
    # Altas de cliente: tercero + subcuenta 430
    # ------------------------------------------------------------------

    def _claim_customer(self) -> dict | None:
        """Reclama el siguiente cliente creado desde Flutter."""
        resp = self._session.post(
            f"{self.config.api_base_url}/worker/customer/claim",
            json={
                "worker_id": self.config.worker_id,
                "lease_minutes": self.config.lease_minutes,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data if data.get("claimed") else None

    def _process_customer(self, claim: dict) -> None:
        customer = claim.get("customer") or {}
        organization = claim.get("organization") or {}
        customer_id = str(customer.get("id") or "")
        try:
            tercero_id, subcuenta = self._import_customer_to_desktop(
                organization, customer,
            )
            resp = self._session.post(
                f"{self.config.api_base_url}/worker/customer/{customer_id}/confirm",
                json={
                    "desktop_tercero_id": str(tercero_id),
                    "desktop_subcuenta": subcuenta,
                },
            )
            resp.raise_for_status()
            logger.info(
                "Cliente %s integrado como tercero %s, subcuenta %s",
                customer_id, tercero_id, subcuenta,
            )
        except Exception as exc:
            logger.exception("Error integrando cliente %s", customer_id)
            if customer_id:
                try:
                    self._session.post(
                        f"{self.config.api_base_url}/worker/customer/{customer_id}/error",
                        json={"error": str(exc)},
                    ).raise_for_status()
                except Exception:
                    logger.exception("No se pudo reportar el error del cliente %s", customer_id)

    def _import_customer_to_desktop(
        self, organization: dict, customer: dict,
    ) -> tuple[str, str]:
        """Crea o vincula el tercero y asigna su 430 en Gest2A3Eco."""
        gestor = self._ensure_gestor()
        codigo_empresa = str(organization.get("company_code") or "").strip()
        if not codigo_empresa:
            raise ValueError("company_code no disponible")
        empresa = gestor.get_empresa(codigo_empresa)
        if not empresa:
            raise ValueError(f"Empresa {codigo_empresa} no existe en escritorio")

        nif_raw = str(customer.get("tax_id") or "").strip().upper()
        nif_normalizado = re.sub(r"[^A-Z0-9]", "", nif_raw)
        if not nif_normalizado:
            raise ValueError("NIF del cliente vacio")
        tercero = gestor.get_tercero_by_nif_normalizado(nif_normalizado)
        if tercero:
            tercero_id = str(tercero["id"])
        else:
            tercero_id = str(gestor.upsert_tercero({
                "nif": nif_normalizado,
                "nif_normalizado": nif_normalizado,
                "nombre": customer.get("legal_name", ""),
                "nombre_legal": customer.get("legal_name", ""),
                "direccion": customer.get("address", ""),
                "cp": customer.get("postal_code", ""),
                "poblacion": customer.get("city", ""),
                "provincia": customer.get("province", ""),
                "pais": customer.get("country", "ES"),
                "email": customer.get("email", ""),
                "telefono": customer.get("phone", ""),
                "origen": "flutter",
            }))

        digitos_plan = int(empresa.get("digitos_plan") or 8)
        relacion = gestor.get_tercero_empresa(codigo_empresa, tercero_id, 0) or {}
        subcuenta_existente = str(relacion.get("subcuenta_cliente") or "")
        if subcuenta_existente.startswith("430") and subcuenta_existente.isdigit():
            # Reutiliza la subcuenta ya asignada a este tercero en esta
            # empresa; nunca la reasigna ni la cambia por otra.
            subcuenta = subcuenta_existente
            if not gestor.get_maestro_subcuenta_por_subcuenta(codigo_empresa, subcuenta):
                gestor.upsert_maestro_subcuenta({
                    "codigo_empresa": codigo_empresa,
                    "tercero_id": tercero_id,
                    "subcuenta": subcuenta,
                    "nombre_subcuenta": customer.get("legal_name", ""),
                    "tipo_subcuenta": "cliente",
                    "nif_snapshot": nif_normalizado,
                    "activo": True,
                    "origen": "flutter",
                    "pendiente_alta_a3": True,
                })
        else:
            subcuenta = self._resolve_subcuenta_430(
                gestor, codigo_empresa, nif_normalizado, digitos_plan,
                tercero_id=tercero_id,
                legal_name=customer.get("legal_name", ""),
            )
        gestor.upsert_tercero_empresa({
            "codigo_empresa": codigo_empresa,
            "ejercicio": 0,
            "tercero_id": tercero_id,
            "subcuenta_cliente": subcuenta,
        })
        return tercero_id, subcuenta

    def _resolve_subcuenta_430(
        self, gestor: DesktopGestor, codigo: str, nif: str, digitos: int,
        *, tercero_id: str, legal_name: str,
    ) -> str:
        """Busca subcuenta 430 existente para el NIF o asigna y reserva una nueva.

        Atomico frente a concurrencia (seccion 17 del encargo):

        1. Adquiere ``pg_advisory_xact_lock`` por empresa (se libera solo al
           terminar la transaccion actual) antes de leer el maximo existente,
           para minimizar colisiones en el caso comun.
        2. La restriccion ``UNIQUE(codigo_empresa, subcuenta)`` de
           ``maestro_subcuentas_empresa`` es la garantia final: si, aun asi,
           dos procesos coincidieran en el mismo numero, el INSERT que pierde
           la carrera falla y aqui se reintenta (hasta
           ``_SUBCUENTA_430_MAX_ATTEMPTS`` veces) recalculando el siguiente
           numero libre.

        Nunca reutiliza una subcuenta ya asignada a otro tercero.
        """
        last_error: Exception | None = None
        for attempt in range(1, _SUBCUENTA_430_MAX_ATTEMPTS + 1):
            gestor.advisory_lock_empresa_430(codigo)
            existing = gestor.listar_maestro_subcuentas_empresa(
                codigo, tipo="cliente", activo=True,
            )
            for sub in existing:
                snap = (sub.get("nif_snapshot") or "").upper()
                if snap == nif and sub.get("subcuenta", "").startswith("430"):
                    return sub["subcuenta"]

            prefix = "430"
            suffix_len = digitos - len(prefix)
            max_num = 0
            for sub in existing:
                sc = sub.get("subcuenta", "")
                if sc.startswith(prefix) and len(sc) == digitos:
                    try:
                        num = int(sc[len(prefix):])
                        if num > max_num:
                            max_num = num
                    except ValueError:
                        continue
            next_num = max_num + 1
            subcuenta = f"{prefix}{next_num:0{suffix_len}d}"

            try:
                gestor.upsert_maestro_subcuenta({
                    "codigo_empresa": codigo,
                    "tercero_id": tercero_id,
                    "subcuenta": subcuenta,
                    "nombre_subcuenta": legal_name,
                    "tipo_subcuenta": "cliente",
                    "nif_snapshot": nif,
                    "activo": True,
                    "origen": "flutter",
                    "pendiente_alta_a3": True,
                })
                return subcuenta
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Conflicto asignando subcuenta %s en %s (intento %d/%d); "
                    "reintentando: %s",
                    subcuenta, codigo, attempt, _SUBCUENTA_430_MAX_ATTEMPTS, exc,
                )

        raise RuntimeError(
            f"No se pudo asignar una subcuenta 430 para {codigo} tras "
            f"{_SUBCUENTA_430_MAX_ATTEMPTS} intentos"
        ) from last_error

    # ------------------------------------------------------------------
    # Importacion contable de facturas (cola independiente)
    # ------------------------------------------------------------------

    def _claim_accounting(self) -> dict | None:
        """Reclama la siguiente factura pendiente de importar a contabilidad.

        Usa ClientInvoiceAccountingQueue (Etapa 3), nunca
        ClientInvoiceProcessingQueue (exclusiva de billing_worker desde la
        Etapa 5). Un fallo aqui nunca afecta a la validez fiscal de la
        factura (ADR 0001, seccion 5/16).
        """
        resp = self._session.post(
            f"{self.config.api_base_url}/worker/accounting/claim",
            json={
                "worker_id": self.config.worker_id,
                "lease_minutes": self.config.lease_minutes,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("claimed"):
            logger.info("Reclamada factura %s para contabilidad", data["invoice_id"])
            return data
        return None

    def _process_accounting(self, claim: dict) -> None:
        """Procesa la importacion contable de una factura reclamada."""
        invoice_id = claim["invoice_id"]
        try:
            payload = self._apply_issued_snapshot(claim.get("payload") or {})
            desktop_invoice_id = self._import_to_desktop(invoice_id, payload)
            self._confirm_accounting(invoice_id, payload, desktop_invoice_id)
            logger.info("Factura %s importada a contabilidad", invoice_id)
        except Exception as exc:
            logger.exception("Error importando a contabilidad la factura %s", invoice_id)
            self._report_accounting_error(invoice_id, str(exc))

    @staticmethod
    def _apply_issued_snapshot(payload: dict) -> dict:
        """Usa los datos inmutables de emision y conserva solo enlaces internos."""
        raw_snapshot = payload.get("issued_snapshot")
        if not raw_snapshot:
            return payload
        try:
            snapshot = json.loads(raw_snapshot)
        except (TypeError, ValueError):
            logger.warning("issued_snapshot no contiene JSON valido")
            return payload
        if not isinstance(snapshot, dict):
            return payload

        result = dict(payload)
        for section in ("organization", "customer", "invoice"):
            live = payload.get(section) or {}
            issued = snapshot.get(section) or {}
            if isinstance(live, dict) and isinstance(issued, dict):
                # El snapshot manda en los datos visibles. Los campos que no
                # existian al emitir (identificadores desktop, destinatario)
                # siguen disponibles para completar el proceso interno.
                result[section] = {**live, **issued}
        if isinstance(snapshot.get("lines"), list):
            result["lines"] = snapshot["lines"]
        return result

    def _import_to_desktop(self, invoice_id: str, payload: dict) -> str:
        """Importa tercero y factura al escritorio PostgreSQL. Devuelve el id interno.

        Idempotente:
        - Exige que el tercero ya haya sido validado por el flujo de altas
        - Usa exclusivamente la subcuenta 430 asignada por el escritorio
        - Registra subcuenta en maestro
        - Guarda factura en facturas_emitidas_docs
        """
        gestor = self._ensure_gestor()
        org = payload.get("organization", {})
        customer = payload.get("customer", {})
        invoice = payload.get("invoice", {})
        lines = payload.get("lines", [])

        codigo_empresa = org.get("company_code", "")
        if not codigo_empresa:
            raise ValueError("company_code no disponible en payload")

        empresa = gestor.get_empresa(codigo_empresa)
        if not empresa:
            raise ValueError(f"Empresa {codigo_empresa} no existe en escritorio")

        ejercicio = invoice.get("fiscal_year", datetime.now().year)
        # -- Tercero --
        nif_raw = customer.get("tax_id", "")
        nif_normalizado = re.sub(r"[^A-Za-z0-9]", "", nif_raw).upper()
        if not nif_normalizado:
            raise ValueError("NIF del cliente vacio")

        tercero = gestor.get_tercero_by_nif_normalizado(nif_normalizado)
        expected_tercero_id = str(customer.get("desktop_tercero_id") or "")
        if not tercero:
            raise ValueError(
                "El cliente no esta integrado en Gest2A3Eco; "
                "sincroniza el alta antes de procesar la factura"
            )
        tercero_id = str(tercero["id"])
        if expected_tercero_id and tercero_id != expected_tercero_id:
            raise ValueError("El tercero sincronizado no coincide con el NIF de la factura")
        logger.info("Tercero existente %s (NIF %s)", tercero_id, nif_normalizado)

        # -- Subcuenta 430 --
        subcuenta_cliente = str(customer.get("desktop_subcuenta") or "")
        if not subcuenta_cliente.startswith("430") or not subcuenta_cliente.isdigit():
            raise ValueError("El cliente no tiene una subcuenta 430 sincronizada")

        # -- Relacion tercero-empresa --
        gestor.upsert_tercero_empresa({
            "codigo_empresa": codigo_empresa,
            "ejercicio": 0,  # empresa-level
            "tercero_id": tercero_id,
            "subcuenta_cliente": subcuenta_cliente,
        })

        # -- Maestro subcuentas --
        existing_sub = gestor.get_maestro_subcuenta_por_subcuenta(
            codigo_empresa, subcuenta_cliente,
        )
        if not existing_sub:
            gestor.upsert_maestro_subcuenta({
                "codigo_empresa": codigo_empresa,
                "tercero_id": tercero_id,
                "subcuenta": subcuenta_cliente,
                "nombre_subcuenta": customer.get("legal_name", ""),
                "tipo_subcuenta": "cliente",
                "nif_snapshot": nif_normalizado,
                "activo": True,
                "origen": "flutter",
                "pendiente_alta_a3": True,
            })

        # -- Factura --
        series = invoice.get("series_code", "WEB")
        numero = invoice.get("invoice_number", 0)
        fac_dict = {
            "id": f"flutter_{invoice_id}",
            "codigo_empresa": codigo_empresa,
            "ejercicio": ejercicio,
            "tercero_id": tercero_id,
            "serie": series,
            "numero": numero,
            "fecha_expedicion": invoice.get("invoice_date", ""),
            "fecha_asiento": invoice.get("invoice_date", ""),
            "nif": nif_raw.upper(),
            "nombre": customer.get("legal_name", ""),
            "descripcion": f"Factura {series}-{numero:06d}",
            "observaciones": invoice.get("notes", ""),
            "subcuenta_cliente": subcuenta_cliente,
            "forma_pago": invoice.get("payment_method", ""),
            "moneda_codigo": invoice.get("currency", "EUR"),
            "moneda_simbolo": "EUR",
            "borrador": False,
            "generada": False,
            "enviado": False,
            "origen_factura": "facturacion",
        }
        # Idempotencia por UUID del backend (seccion 16 del encargo): el id
        # interno es deterministico (``flutter_<uuid>``) y
        # upsert_factura_emitida usa ON CONFLICT(id) DO UPDATE, asi que
        # reprocesar el mismo evento nunca duplica la fila. El prefijo
        # tambien sirve como marca de origen consultable
        # (``WHERE id LIKE 'flutter_%'``); anadir columnas dedicadas
        # source_system/accounting_sync_revision a facturas_emitidas_docs
        # queda fuera de esta etapa (ver docs/adr/0001, seccion 16).

        # Retencion
        wh_rate = Decimal(str(invoice.get("withholding_rate", "0")))
        if wh_rate > 0:
            fac_dict["retencion_aplica"] = True
            fac_dict["retencion_pct"] = float(wh_rate)
            fac_dict["retencion_base"] = float(invoice.get("subtotal", "0"))
            fac_dict["retencion_importe"] = -abs(float(invoice.get("withholding_amount", "0")))
        else:
            fac_dict["retencion_aplica"] = False

        # Lineas
        lineas_json = []
        for ln in lines:
            lineas_json.append({
                "concepto": ln.get("description", ""),
                "unidades": float(ln.get("quantity", "1")),
                "precio": float(ln.get("unit_price", "0")),
                "base": float(ln.get("line_total", "0")),
                "pct_iva": float(ln.get("vat_rate", "21")),
                "cuota_iva": float(ln.get("vat_amount", "0")),
            })
        fac_dict["lineas"] = lineas_json

        factura_desktop_id = gestor.upsert_factura_emitida(fac_dict)
        gestor.enviar_facturas_emitidas_a_contabilidad(
            codigo_empresa, ejercicio, [factura_desktop_id],
        )
        logger.info(
            "Factura importada %s-%06d (empresa %s)",
            series, numero, codigo_empresa,
        )
        return str(factura_desktop_id)

    def _confirm_accounting(
        self, invoice_id: str, payload: dict, desktop_invoice_id: str,
    ) -> None:
        customer = payload.get("customer", {})
        resp = self._session.post(
            f"{self.config.api_base_url}/worker/accounting/{invoice_id}/confirm",
            json={
                "desktop_tercero_id": str(customer.get("desktop_tercero_id") or ""),
                "desktop_subcuenta": str(customer.get("desktop_subcuenta") or ""),
                "desktop_invoice_ref": desktop_invoice_id,
            },
        )
        resp.raise_for_status()

    def _report_accounting_error(self, invoice_id: str, error: str) -> None:
        try:
            self._session.post(
                f"{self.config.api_base_url}/worker/accounting/{invoice_id}/error",
                json={"error": error[:2000]},
            )
        except Exception:
            logger.exception("No se pudo reportar el error contable de %s", invoice_id)
