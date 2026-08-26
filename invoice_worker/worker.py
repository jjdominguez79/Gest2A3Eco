"""Worker principal de procesamiento de facturas online.

Flujo por factura:
1. Reclamar factura numerada (lease)
2. Descargar payload
3. Importar tercero y factura idempotentemente al escritorio
4. Generar PDF con Word COM
5. Subir PDF y SHA-256
6. Publicar en area documental
7. Enviar email via Graph
8. Enviar FCM al emisor
9. Confirmar cada transicion de estado

Cada paso es idempotente. Las caidas no duplican datos.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

import requests

from invoice_worker.config import WorkerConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocolos para inyeccion de dependencias (tests usan adaptadores simulados)
# ---------------------------------------------------------------------------

class DesktopGestor(Protocol):
    """Interfaz minima del gestor de datos del escritorio."""

    def get_tercero_by_nif_normalizado(self, nif: str) -> dict | None: ...
    def upsert_tercero(self, tercero: dict) -> str: ...
    def upsert_tercero_empresa(self, rel: dict) -> None: ...
    def upsert_maestro_subcuenta(self, datos: dict) -> int: ...
    def get_maestro_subcuenta_por_subcuenta(self, codigo: str, sub: str) -> dict | None: ...
    def listar_maestro_subcuentas_empresa(self, codigo: str, tipo: str | None = None, activo: bool = True) -> list: ...
    def upsert_factura_emitida(self, factura: dict) -> str: ...
    def get_empresa(self, codigo: str) -> dict | None: ...


class PdfRenderer(Protocol):
    """Interfaz para generacion de PDF."""

    def render(
        self, empresa_conf: dict, fac: dict, cliente: dict,
        totales: dict, template_path: str, pdf_path: str,
    ) -> str: ...


class EmailSender(Protocol):
    """Interfaz para envio de email."""

    def send(
        self, *, sender: str, to: str, subject: str, body: str,
        attachments: list | None = None,
    ) -> dict: ...


class FcmSender(Protocol):
    """Interfaz para notificacion push."""

    def send(self, push_token: str, payload: dict, *, platform: str) -> bool: ...


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


class RealEmailSender:
    """Envia email via Microsoft Graph."""

    def __init__(self) -> None:
        from services.graph_mail_service import GraphMailService
        self._service = GraphMailService()

    def send(
        self, *, sender: str, to: str, subject: str, body: str,
        attachments: list | None = None,
    ) -> dict:
        result = self._service.send(
            sender=sender,
            to=[to],
            subject=subject,
            body=body,
            attachments=[str(item["path"]) for item in attachments or []],
        )
        return {"message_id": result.internet_message_id}


class RealFcmSender:
    """Envia notificacion push FCM via firebase_admin."""

    def send(self, push_token: str, payload: dict, *, platform: str = "android") -> bool:
        from backend.api.messaging_firebase import send_fcm
        result = send_fcm(push_token, payload, platform=platform)
        return result.success


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
        email_sender: EmailSender | None = None,
        fcm_sender: FcmSender | None = None,
    ) -> None:
        self.config = config
        self._session = requests.Session()
        self._session.headers["x-api-key"] = config.api_token

        # Adaptadores inyectables (produccion usa los reales)
        self._gestor = gestor
        self._renderer = renderer
        self._email_sender = email_sender
        self._fcm_sender = fcm_sender

    def _ensure_gestor(self) -> DesktopGestor:
        if self._gestor is None:
            if not self.config.desktop_dsn:
                raise RuntimeError(
                    "INVOICE_WORKER_DESKTOP_DSN no configurado; "
                    "no se puede importar al escritorio"
                )
            self._gestor = RealDesktopGestor(self.config.desktop_dsn)
        return self._gestor

    def _ensure_renderer(self) -> PdfRenderer:
        if self._renderer is None:
            self._renderer = RealPdfRenderer()
        return self._renderer

    def _ensure_email_sender(self) -> EmailSender:
        if self._email_sender is None:
            self._email_sender = RealEmailSender()
        return self._email_sender

    def _ensure_fcm_sender(self) -> FcmSender:
        if self._fcm_sender is None:
            self._fcm_sender = RealFcmSender()
        return self._fcm_sender

    def run_forever(self) -> None:
        """Bucle principal del worker."""
        logger.info("Worker %s iniciado", self.config.worker_id)
        while True:
            try:
                claimed = self._claim()
                if claimed:
                    self._process(claimed)
                else:
                    time.sleep(self.config.poll_interval_seconds)
            except KeyboardInterrupt:
                logger.info("Worker detenido por usuario")
                break
            except Exception:
                logger.exception("Error en bucle principal")
                time.sleep(self.config.poll_interval_seconds)

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
            # 1. Descargar payload
            payload = self._get_payload(invoice_id)

            # 2. Importar al escritorio (idempotente)
            self._import_to_desktop(invoice_id, payload)
            self._confirm_import(invoice_id)

            # 3. Generar PDF con Word
            pdf_path = self._render_pdf(invoice_id, payload)

            # 4. Subir PDF al backend (Azure)
            self._upload_pdf(invoice_id, pdf_path)

            # 5. Publicar en area documental (idempotente)
            self._publish_document(invoice_id, payload)

            # 6. Enviar email (unico)
            self._send_email(invoice_id, payload, pdf_path)

            # 7. Notificacion FCM (best-effort)
            self._send_fcm(invoice_id, payload)

            logger.info("Factura %s procesada con exito", invoice_id)

        except Exception as e:
            logger.exception("Error procesando factura %s", invoice_id)
            self._report_error(invoice_id, str(e))

    def _get_payload(self, invoice_id: str) -> dict:
        resp = self._session.get(
            f"{self.config.api_base_url}/worker/invoice/{invoice_id}/payload",
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Paso 2: Importacion idempotente al escritorio
    # ------------------------------------------------------------------

    def _import_to_desktop(self, invoice_id: str, payload: dict) -> None:
        """Importa tercero y factura al escritorio PostgreSQL.

        Idempotente:
        - Busca tercero por NIF normalizado; crea si no existe
        - Vincula tercero a empresa con subcuenta 430xxx
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
        digitos_plan = int(empresa.get("digitos_plan") or 8)

        # -- Tercero --
        nif_raw = customer.get("tax_id", "")
        nif_normalizado = re.sub(r"[^A-Za-z0-9]", "", nif_raw).upper()
        if not nif_normalizado:
            raise ValueError("NIF del cliente vacio")

        tercero = gestor.get_tercero_by_nif_normalizado(nif_normalizado)
        if tercero:
            tercero_id = tercero["id"]
            logger.info("Tercero existente %s (NIF %s)", tercero_id, nif_normalizado)
        else:
            tercero_id = gestor.upsert_tercero({
                "nif": nif_raw.upper(),
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
            })
            logger.info("Tercero creado %s (NIF %s)", tercero_id, nif_normalizado)

        # -- Subcuenta 430 --
        subcuenta_cliente = self._resolve_subcuenta_430(
            gestor, codigo_empresa, nif_normalizado, digitos_plan,
        )

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

        gestor.upsert_factura_emitida(fac_dict)
        logger.info(
            "Factura importada %s-%06d (empresa %s)",
            series, numero, codigo_empresa,
        )

    def _resolve_subcuenta_430(
        self, gestor: DesktopGestor, codigo: str, nif: str, digitos: int,
    ) -> str:
        """Busca subcuenta 430 existente para el NIF o asigna la siguiente."""
        # Buscar por NIF en subcuentas existentes
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
            # Buscar cualquier .docx en el directorio
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
    # Paso 6: Envio de email (unico, idempotente por estado)
    # ------------------------------------------------------------------

    def _send_email(self, invoice_id: str, payload: dict, pdf_path: Path) -> None:
        """Envia email con la factura PDF adjunta via Graph."""
        invoice = payload.get("invoice", {})
        recipient = invoice.get("recipient_email", "")
        if not recipient:
            logger.info("Sin email destinatario, omitiendo envio para %s", invoice_id)
            # Marcar como emailed igualmente para completar el flujo
            self._mark_emailed(invoice_id, "")
            return

        series = invoice.get("series_code", "WEB")
        number = invoice.get("invoice_number", 0)
        org_name = payload.get("organization", {}).get("name", "")

        subject = f"Factura {series}-{number:06d} - {org_name}"
        body = (
            f"Estimado cliente,\n\n"
            f"Adjuntamos la factura {series}-{number:06d}.\n\n"
            f"Un saludo,\n{org_name}"
        )

        pdf_content = pdf_path.read_bytes()
        attachments = [{
            "path": str(pdf_path),
            "name": pdf_path.name,
            "content": pdf_content,
        }]

        try:
            sender = self._ensure_email_sender()
            result = sender.send(
                sender=self.config.graph_sender_mailbox,
                to=recipient,
                subject=subject,
                body=body,
                attachments=attachments,
            )
        except Exception:
            logger.exception("Error enviando email a %s", recipient)
            raise

        message_id = result.get("message_id", "")
        logger.info("Email enviado a %s (msg %s)", recipient, message_id)

        self._mark_emailed(invoice_id, message_id)

    def _mark_emailed(self, invoice_id: str, message_id: str) -> None:
        resp = self._session.post(
            f"{self.config.api_base_url}/worker/invoice/{invoice_id}/emailed",
            json={"message_id": message_id},
        )
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # Paso 7: FCM (best-effort, no bloquea el flujo)
    # ------------------------------------------------------------------

    def _send_fcm(self, invoice_id: str, payload: dict) -> None:
        """Envia notificacion push al cliente emisor."""
        push_tokens = payload.get("push_tokens", [])
        if not push_tokens:
            logger.info("Sin tokens FCM para %s", invoice_id)
            return

        invoice = payload.get("invoice", {})
        series = invoice.get("series_code", "WEB")
        number = invoice.get("invoice_number", 0)

        fcm_payload = {
            "title": "Factura procesada",
            "body": f"Tu factura {series}-{number:06d} ha sido procesada.",
            "invoice_id": invoice_id,
            "type": "invoice_processed",
        }

        try:
            fcm = self._ensure_fcm_sender()
            for token_info in push_tokens:
                token = token_info if isinstance(token_info, str) else token_info.get("token", "")
                platform = "web" if isinstance(token_info, dict) and token_info.get("platform") == "web" else "android"
                if token:
                    fcm.send(token, fcm_payload, platform=platform)
        except Exception:
            logger.exception("Error enviando FCM para %s (no bloqueante)", invoice_id)

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
