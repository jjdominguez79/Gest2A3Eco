"""Publicacion de documentos AAPP en el area documental del cliente.

Los PDF se envian al backend por multipart. Flutter los consume mediante el
mismo contrato de documentos que las facturas, sin acceder a rutas del puesto.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from services.aapp.certificados import TIPOS
from services.backend_client_service import BackendClientService


@dataclass(frozen=True)
class ResultadoPublicacionAAPP:
    ok: bool
    documento_id: str = ""
    version: int = 0
    mensaje: str = ""


class PublicadorDocumentosAAPP:
    def __init__(self, gestor, backend: BackendClientService | None = None):
        self._gestor = gestor
        self._backend = backend or BackendClientService()

    @staticmethod
    def _sha256(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def publicar_certificado(self, solicitud: dict) -> ResultadoPublicacionAAPP:
        codigo = str(solicitud.get("codigo_empresa") or "")
        sid = str(solicitud.get("id") or "")
        pdf_path = str(solicitud.get("pdf_path") or "")
        try:
            if solicitud.get("estado") != "OBTENIDO":
                raise ValueError("Solo se pueden publicar certificados obtenidos")
            self._validar_pdf(pdf_path)
            empresa = self._gestor.get_empresa(codigo) or {}
            tipo = str(solicitud.get("tipo") or "CERTIFICADO")
            organismo, descripcion, _url = TIPOS.get(tipo, ("AAPP", tipo, ""))
            fecha = str(
                solicitud.get("fecha_obtencion")
                or solicitud.get("fecha_solicitud")
                or ""
            )
            result = self._backend.publish_document(
                source_type=f"certificado_{organismo.lower()}",
                source_system="desktop_aapp",
                source_id=sid,
                source_version=max(1, int(solicitud.get("area_cliente_version") or 1)),
                display_name=descripcion,
                description=f"Certificado obtenido de {organismo}",
                pdf_path=pdf_path,
                company_code=codigo,
                customer_tax_id=str(empresa.get("cif") or solicitud.get("empresa_cif") or ""),
                fiscal_year=self._ejercicio(fecha),
                document_date=fecha[:10] or None,
                expected_sha256=self._sha256(pdf_path),
            )
            documento_id = str(result.get("id") or result.get("document_id") or "")
            version = int(result.get("source_version") or 1)
            ahora = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            self._gestor.marcar_cert_solicitud_publicada(
                codigo, sid, documento_id, version, ahora,
            )
            return ResultadoPublicacionAAPP(True, documento_id, version, "Publicado")
        except Exception as exc:
            mensaje = str(exc) or exc.__class__.__name__
            if codigo and sid:
                try:
                    self._gestor.marcar_cert_solicitud_publicacion_error(codigo, sid, mensaje)
                except Exception:
                    pass
            return ResultadoPublicacionAAPP(False, mensaje=mensaje)

    def publicar_notificacion(self, notificacion: dict) -> ResultadoPublicacionAAPP:
        codigo = str(notificacion.get("codigo_empresa") or "")
        item_id = str(notificacion.get("id") or "")
        pdf_path = str(notificacion.get("pdf_path") or "")
        try:
            self._validar_pdf(pdf_path)
            empresa = self._gestor.get_empresa(codigo) or {}
            fecha = str(notificacion.get("fecha_puesta_disposicion") or "")
            asunto = str(notificacion.get("asunto") or "Notificacion electronica")
            result = self._backend.publish_document(
                source_type="notificacion_dehu",
                source_system="desktop_aapp",
                source_id=item_id,
                source_version=max(1, int(notificacion.get("area_cliente_version") or 1)),
                display_name=asunto,
                description="Notificacion electronica recibida en DEHu",
                pdf_path=pdf_path,
                company_code=codigo,
                customer_tax_id=str(empresa.get("cif") or ""),
                fiscal_year=int(notificacion.get("ejercicio") or self._ejercicio(fecha)),
                document_date=fecha[:10] or None,
                expected_sha256=self._sha256(pdf_path),
            )
            documento_id = str(result.get("id") or result.get("document_id") or "")
            version = int(result.get("source_version") or 1)
            ahora = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            self._gestor.marcar_notif_bandeja_publicada_cliente(
                codigo, item_id, documento_id, version, ahora,
            )
            return ResultadoPublicacionAAPP(True, documento_id, version, "Publicado")
        except Exception as exc:
            mensaje = str(exc) or exc.__class__.__name__
            if codigo and item_id:
                try:
                    self._gestor.marcar_notif_bandeja_publicacion_error(codigo, item_id, mensaje)
                except Exception:
                    pass
            return ResultadoPublicacionAAPP(False, mensaje=mensaje)

    @staticmethod
    def _validar_pdf(pdf_path: str) -> None:
        path = Path(pdf_path)
        if not path.is_file():
            raise FileNotFoundError(f"PDF no encontrado: {pdf_path or '(ruta vacia)'}")
        with path.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                raise ValueError("El documento no es un PDF valido")

    @staticmethod
    def _ejercicio(fecha: str) -> int:
        try:
            return int(str(fecha)[:4])
        except (TypeError, ValueError):
            return datetime.now().year
