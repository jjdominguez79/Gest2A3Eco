"""Worker principal de procesamiento de facturas online.

Flujo por factura:
1. Reclamar factura numerada (lease)
2. Descargar payload
3. Importar tercero y factura idempotentemente al escritorio
4. Generar PDF con Word COM
5. Subir PDF y SHA-256
6. Publicar en area documental
7. Solicitar envio de email al backend (el backend usa Graph)
8. Solicitar envio de FCM al backend (best-effort)
9. Confirmar cada transicion de estado

Cada paso es idempotente. Las caidas no duplican datos.
El worker NO usa Graph ni Firebase directamente. Los secretos de
proveedores permanecen en el backend.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import signal
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

import requests

from invoice_worker.config import WorkerConfig

logger = logging.getLogger(__name__)

# Backoff maximo entre reintentos (5 minutos)
_MAX_BACKOFF_SECONDS = 300


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


class PdfRenderer(Protocol):
    """Interfaz para generacion de PDF."""

    def render(
        self, empresa_conf: dict, fac: dict, cliente: dict,
        totales: dict, template_path: str, pdf_path: str,
    ) -> str: ...


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


class RealPdfRenderer:
    """Genera PDF usando Word COM via procesos/facturas_word.py."""

    def render(
        self, empresa_conf: dict, fac: dict, cliente: dict,
        totales: dict, template_path: str, pdf_path: str,
    ) -> str:
        from procesos.facturas_word import (
            build_context_emitida,
            generar_pdf_desde_plantilla_word,
        )
        context = build_context_emitida(empresa_conf, fac, cliente, totales)
        result_pdf, _ = generar_pdf_desde_plantilla_word(
            template_path, context, pdf_path,
        )
        return result_pdf


# ---------------------------------------------------------------------------
# Worker principal
# ---------------------------------------------------------------------------

class InvoiceWorker:
    def __init__(
        self,
        config: WorkerConfig,
        *,
        gestor: DesktopGestor | None = None,
        renderer: PdfRenderer | None = None,
    ) -> None:
        self.config = config
        self._session = requests.Session()
        self._session.headers["x-api-key"] = config.api_token

        # Adaptadores inyectables (produccion usa los reales)
        self._gestor = gestor
        self._renderer = renderer

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

    def _ensure_renderer(self) -> PdfRenderer:
        if self._renderer is None:
            self._renderer = RealPdfRenderer()
        return self._renderer

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
                customer_claim = self._claim_customer()
                if customer_claim:
                    self._process_customer(customer_claim)
                    self._consecutive_errors = 0
                    continue
                claimed = self._claim()
                if claimed:
                    self._process(claimed)
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

    # ------------------------------------------------------------------
    # Reclamo y procesamiento
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
            subcuenta = subcuenta_existente
        else:
            subcuenta = self._resolve_subcuenta_430(
                gestor, codigo_empresa, nif_normalizado, digitos_plan,
            )
        gestor.upsert_tercero_empresa({
            "codigo_empresa": codigo_empresa,
            "ejercicio": 0,
            "tercero_id": tercero_id,
            "subcuenta_cliente": subcuenta,
        })
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
        return tercero_id, subcuenta

    def _claim(self) -> dict | None:
        """Reclama la siguiente factura pendiente."""
        resp = self._session.post(
            f"{self.config.api_base_url}/worker/claim",
            json={
                "worker_id": self.config.worker_id,
                "lease_minutes": self.config.lease_minutes,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("claimed"):
            logger.info("Reclamada factura %s", data["invoice_id"])
            return data
        return None

    def _process(self, claim: dict) -> None:
        """Procesa una factura reclamada."""
        invoice_id = claim["invoice_id"]
        try:
            # Consultar estado actual (recuperacion tras caida)
            status = self._get_status(invoice_id)

            # 1. Descargar payload
            payload = self._get_payload(invoice_id)

            # 2. Importar al escritorio (idempotente)
            if status.get("invoice_status") not in (
                "imported", "rendered", "emailed",
            ):
                self._import_to_desktop(invoice_id, payload)
                self._confirm_import(invoice_id)
            else:
                logger.info("Importacion ya completada para %s", invoice_id)

            # 3. Generar PDF con Word
            if not status.get("pdf_uploaded"):
                pdf_path = self._render_pdf(invoice_id, payload)
                # 4. Subir PDF al backend (Azure)
                self._upload_pdf(invoice_id, pdf_path)
            else:
                logger.info("PDF ya subido para %s", invoice_id)

            # 5. Publicar en area documental (idempotente)
            if not status.get("document_published"):
                self._publish_document(invoice_id, payload)
            else:
                logger.info("Documento ya publicado para %s", invoice_id)

            # 6. Solicitar envio de email al backend
            if status.get("invoice_status") != "emailed":
                self._request_email(invoice_id, payload)
            else:
                logger.info("Email ya enviado para %s", invoice_id)

            # 7. Solicitar FCM al backend (best-effort)
            self._request_fcm(invoice_id)

            logger.info("Factura %s procesada con exito", invoice_id)

        except Exception as e:
            logger.exception("Error procesando factura %s", invoice_id)
            self._report_error(invoice_id, str(e))

    def _get_status(self, invoice_id: str) -> dict:
        """Consulta el estado actual de procesamiento."""
        try:
            resp = self._session.get(
                f"{self.config.api_base_url}/worker/invoice/{invoice_id}/status",
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning("No se pudo consultar estado de %s", invoice_id)
            return {}

    def _get_payload(self, invoice_id: str) -> dict:
        resp = self._session.get(
            f"{self.config.api_base_url}/worker/invoice/{invoice_id}/payload",
        )
        resp.raise_for_status()
        return self._apply_issued_snapshot(resp.json())

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

    # ------------------------------------------------------------------
    # Paso 2: Importacion idempotente al escritorio
    # ------------------------------------------------------------------

    def _import_to_desktop(self, invoice_id: str, payload: dict) -> None:
        """Importa tercero y factura al escritorio PostgreSQL.

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

    def _resolve_subcuenta_430(
        self, gestor: DesktopGestor, codigo: str, nif: str, digitos: int,
    ) -> str:
        """Busca subcuenta 430 existente para el NIF o asigna la siguiente."""
        existing = gestor.listar_maestro_subcuentas_empresa(
            codigo, tipo="cliente", activo=True,
        )
        for sub in existing:
            snap = (sub.get("nif_snapshot") or "").upper()
            if snap == nif and sub.get("subcuenta", "").startswith("430"):
                return sub["subcuenta"]

        # Asignar siguiente subcuenta 430
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
        return f"{prefix}{next_num:0{suffix_len}d}"

    def _confirm_import(self, invoice_id: str) -> None:
        resp = self._session.post(
            f"{self.config.api_base_url}/worker/invoice/{invoice_id}/import-confirmed",
        )
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # Paso 3: Generacion real de PDF con Word COM
    # ------------------------------------------------------------------

    def _render_pdf(self, invoice_id: str, payload: dict) -> Path:
        """Genera PDF usando Word COM via procesos/facturas_word.py."""
        pdf_dir = Path(self.config.pdf_output_dir)
        pdf_dir.mkdir(parents=True, exist_ok=True)

        series = payload.get("invoice", {}).get("series_code", "WEB")
        number = payload.get("invoice", {}).get("invoice_number", 0)
        pdf_path = pdf_dir / f"{series}-{number:06d}.pdf"

        # Idempotente: si el PDF ya existe y no esta vacio, reutilizar
        if pdf_path.exists() and pdf_path.stat().st_size > 100:
            logger.info("PDF ya existe: %s", pdf_path)
            return pdf_path

        # Construir contextos para build_context_emitida
        org = payload.get("organization", {})
        customer = payload.get("customer", {})
        invoice = payload.get("invoice", {})
        lines = payload.get("lines", [])

        empresa_conf = {
            "nombre": org.get("name", ""),
            "codigo": org.get("company_code", ""),
            "cif": org.get("tax_id", ""),
            "direccion": org.get("address", ""),
            "cp": org.get("postal_code", ""),
            "poblacion": org.get("city", ""),
            "provincia": org.get("province", ""),
            "telefono": org.get("phone", ""),
            "email": org.get("email", ""),
            "logo_path": "",
        }

        fac = {
            "serie": series,
            "numero": number,
            "fecha_expedicion": invoice.get("invoice_date", ""),
            "descripcion": f"Factura {series}-{number:06d}",
            "observaciones": invoice.get("notes", ""),
            "moneda_simbolo": "EUR",
            "retencion_aplica": float(invoice.get("withholding_rate", "0")) > 0,
            "retencion_pct": float(invoice.get("withholding_rate", "0")),
            "retencion_base": float(invoice.get("subtotal", "0")),
            "retencion_importe": -abs(float(invoice.get("withholding_amount", "0"))),
            "lineas": [],
        }
        for ln in lines:
            qty = float(ln.get("quantity", "1"))
            price = float(ln.get("unit_price", "0"))
            discount_pct = float(ln.get("discount_percent", "0"))
            base = qty * price * (1 - discount_pct / 100)
            vat_rate = float(ln.get("vat_rate", "21"))
            cuota = base * vat_rate / 100
            fac["lineas"].append({
                "concepto": ln.get("description", ""),
                "unidades": qty,
                "precio": price,
                "base": base,
                "pct_iva": vat_rate,
                "cuota_iva": cuota,
            })

        cliente = {
            "nombre": customer.get("legal_name", ""),
            "nombre_legal": customer.get("legal_name", ""),
            "nif": customer.get("tax_id", ""),
            "direccion": customer.get("address", ""),
            "cp": customer.get("postal_code", ""),
            "poblacion": customer.get("city", ""),
            "provincia": customer.get("province", ""),
            "pais": customer.get("country", "ES"),
            "email": customer.get("email", ""),
            "telefono": customer.get("phone", ""),
        }

        totales = {
            "base": float(invoice.get("subtotal", "0")),
            "iva": float(invoice.get("total_vat", "0")),
            "suplidos": 0,
            "irpf": -abs(float(invoice.get("withholding_amount", "0"))),
            "total": float(invoice.get("total", "0")),
        }

        # Resolver plantilla Word
        template_dir = Path(self.config.word_template_dir)
        template_path = template_dir / "factura_emitida.docx"
        if not template_path.exists():
            docx_files = list(template_dir.glob("*.docx"))
            if docx_files:
                template_path = docx_files[0]
            else:
                raise FileNotFoundError(
                    f"No se encontro plantilla Word en {template_dir}"
                )

        renderer = self._ensure_renderer()
        result = renderer.render(
            empresa_conf, fac, cliente, totales,
            str(template_path), str(pdf_path),
        )
        logger.info("PDF generado: %s", result)
        return Path(result)

    # ------------------------------------------------------------------
    # Paso 4: Subida del PDF al backend
    # ------------------------------------------------------------------

    def _upload_pdf(self, invoice_id: str, pdf_path: Path) -> None:
        content = pdf_path.read_bytes()
        sha256 = hashlib.sha256(content).hexdigest()

        resp = self._session.post(
            f"{self.config.api_base_url}/worker/invoice/{invoice_id}/pdf",
            files={"file": (pdf_path.name, content, "application/pdf")},
            data={"sha256": sha256},
        )
        resp.raise_for_status()
        logger.info("PDF subido: %s (%d bytes)", pdf_path.name, len(content))

    # ------------------------------------------------------------------
    # Paso 5: Publicacion en area documental
    # ------------------------------------------------------------------

    def _publish_document(self, invoice_id: str, payload: dict) -> None:
        """Publica el PDF en el area documental del cliente."""
        invoice = payload.get("invoice", {})
        series = invoice.get("series_code", "WEB")
        number = invoice.get("invoice_number", 0)

        resp = self._session.post(
            f"{self.config.api_base_url}/worker/invoice/{invoice_id}/publish-document",
            json={
                "description": f"Factura {series}-{number:06d}",
            },
        )
        resp.raise_for_status()
        doc_id = resp.json().get("document_id")
        logger.info("Documento publicado: %s", doc_id)

    # ------------------------------------------------------------------
    # Paso 6: Email (delegado al backend)
    # ------------------------------------------------------------------

    def _request_email(self, invoice_id: str, payload: dict) -> None:
        """Solicita al backend el envio del email con el PDF adjunto."""
        invoice = payload.get("invoice", {})
        recipient = invoice.get("recipient_email", "")

        resp = self._session.post(
            f"{self.config.api_base_url}/worker/invoice/{invoice_id}/send-email",
            json={
                "recipient_email": recipient,
                "sender_mailbox": self.config.sender_mailbox,
            },
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("already_sent"):
            logger.info("Email ya enviado para %s", invoice_id)
        elif result.get("skipped"):
            logger.info("Email omitido para %s: %s", invoice_id, result.get("reason"))
        else:
            logger.info(
                "Email enviado para %s (msg_id: %s)",
                invoice_id, result.get("message_id", ""),
            )

    # ------------------------------------------------------------------
    # Paso 7: FCM (delegado al backend, best-effort)
    # ------------------------------------------------------------------

    def _request_fcm(self, invoice_id: str) -> None:
        """Solicita al backend el envio de notificacion push."""
        try:
            resp = self._session.post(
                f"{self.config.api_base_url}/worker/invoice/{invoice_id}/send-fcm",
            )
            resp.raise_for_status()
            result = resp.json()
            logger.info(
                "FCM para %s: enviados=%s errores=%s",
                invoice_id, result.get("sent", 0), result.get("errors", 0),
            )
        except Exception:
            logger.exception("Error solicitando FCM para %s (no bloqueante)", invoice_id)

    # ------------------------------------------------------------------
    # Error reporting
    # ------------------------------------------------------------------

    def _report_error(self, invoice_id: str, error: str) -> None:
        try:
            self._session.post(
                f"{self.config.api_base_url}/worker/invoice/{invoice_id}/error",
                json={"error": error[:500]},
            )
        except Exception:
            logger.exception("No se pudo reportar error para %s", invoice_id)
