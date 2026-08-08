"""Archivo documental por cliente y puente selectivo hacia OCR."""
from __future__ import annotations

import base64
import hashlib
import mimetypes
import re
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from services.graph_mail_service import GraphMailService
from services.ocr.ocr_service import OcrService
from utils.utilidades import get_document_repository_dir


# Estructura documental unica para todos los puestos. Los valores historicos
# de ``categorias_documentales.carpeta`` se conservan en la BD, pero nunca
# determinan por si solos la ruta fisica.
CARPETAS_DOCUMENTALES = {
    "FACTURAS_RECIBIDAS": "Facturas_recibidas",
    "FACTURAS_EMITIDAS": "Facturas_emitidas",
    "FISCAL": "Fiscal",
    "CONTABLE": "Contable",
    "LABORAL": "Laboral",
    "BANCARIA": "Bancaria",
    "MERCANTIL": "Mercantil",
    "CONTRATOS": "Contratos",
    "FIRMAS": "Firmas",
    "NOTIFICACIONES": "Notificaciones",
    "OTROS": "Otros",
}


@dataclass
class ArchiveSummary:
    saved: list[str] = field(default_factory=list)
    ocr_document_ids: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class GestionDocumentalService:
    def __init__(self, gestor, graph: GraphMailService | None = None):
        self._gestor = gestor
        self._graph = graph or GraphMailService()

    def categorias(self) -> list[dict]:
        return self._gestor.listar_categorias_documentales()

    def archivar_adjuntos_correo(
        self, *, codigo_empresa: str, ejercicio: int, mailbox: str,
        graph_message_id: str, remitente: str, asunto: str,
        decisiones: list[dict], usuario: str = "",
    ) -> ArchiveSummary:
        summary = ArchiveSummary()
        categorias = {item["id"]: item for item in self.categorias()}
        for decision in decisiones:
            attachment_id = str(decision.get("attachment_id") or "")
            name = str(decision.get("name") or "Adjunto")
            category_id = str(decision.get("categoria_id") or "")
            if not category_id:
                self._gestor.registrar_decision_adjunto({
                    "graph_message_id": graph_message_id,
                    "graph_attachment_id": attachment_id,
                    "nombre": name, "accion": "no_guardar",
                })
                summary.ignored.append(name)
                continue
            category = categorias.get(category_id)
            if not category:
                summary.errors.append(f"{name}: categoria no valida")
                continue
            try:
                item = self._graph.download_attachment(
                    mailbox=mailbox, message_id=graph_message_id,
                    attachment_id=attachment_id,
                )
                content = base64.b64decode(item.get("contentBytes") or "", validate=True)
                digest = hashlib.sha256(content).hexdigest()
                duplicate = self._gestor.conn.execute(
                    "SELECT id FROM documentos_archivo WHERE codigo_empresa=? "
                    "AND hash_archivo=? LIMIT 1", (codigo_empresa, digest),
                ).fetchone()
                if duplicate:
                    summary.duplicates.append(name)
                    self._gestor.registrar_decision_adjunto({
                        "graph_message_id": graph_message_id,
                        "graph_attachment_id": attachment_id, "nombre": name,
                        "accion": "duplicado", "categoria_id": category_id,
                        "documento_id": duplicate["id"],
                    })
                    continue
                folder = self._category_directory(
                    codigo_empresa, ejercicio, category["carpeta"],
                )
                filename = self._available_filename(folder, name)
                destination = folder / filename
                destination.write_bytes(content)
                try:
                    document_id = self._gestor.registrar_documento_archivo({
                        "id": str(uuid.uuid4()), "codigo_empresa": codigo_empresa,
                        "ejercicio": ejercicio, "categoria_id": category_id,
                        "nombre_original": name, "nombre_archivo": filename,
                        "ruta": str(destination), "hash_archivo": digest,
                        "tamano": len(content),
                        "mime_type": item.get("contentType") or mimetypes.guess_type(name)[0],
                        "origen": "correo", "graph_message_id": graph_message_id,
                        "graph_attachment_id": attachment_id,
                        "correo_remitente": remitente, "correo_asunto": asunto,
                        "creado_por": usuario,
                    })
                except Exception:
                    destination.unlink(missing_ok=True)
                    raise
                self._gestor.registrar_decision_adjunto({
                    "graph_message_id": graph_message_id,
                    "graph_attachment_id": attachment_id, "nombre": name,
                    "accion": "guardado", "categoria_id": category_id,
                    "documento_id": document_id,
                })
                summary.saved.append(name)
                if bool(category.get("permite_ocr")):
                    summary.ocr_document_ids.append(document_id)
            except Exception as exc:
                summary.errors.append(f"{name}: {exc}")
        return summary

    def importar_archivo(
        self, *, codigo_empresa: str, ejercicio: int, categoria_id: str,
        source: str | Path, usuario: str = "",
    ) -> str:
        source = Path(source)
        category = next(
            (item for item in self.categorias() if item["id"] == categoria_id), None,
        )
        if not source.is_file() or not category:
            raise ValueError("Archivo o categoria no validos.")
        content = source.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        duplicate = self._gestor.conn.execute(
            "SELECT id FROM documentos_archivo WHERE codigo_empresa=? AND hash_archivo=?",
            (codigo_empresa, digest),
        ).fetchone()
        if duplicate:
            raise ValueError("El documento ya existe para este cliente.")
        folder = self._category_directory(codigo_empresa, ejercicio, category["carpeta"])
        filename = self._available_filename(folder, source.name)
        destination = folder / filename
        shutil.copy2(source, destination)
        try:
            return self._gestor.registrar_documento_archivo({
                "codigo_empresa": codigo_empresa, "ejercicio": ejercicio,
                "categoria_id": categoria_id, "nombre_original": source.name,
                "nombre_archivo": filename, "ruta": str(destination),
                "hash_archivo": digest, "tamano": len(content),
                "mime_type": mimetypes.guess_type(source.name)[0],
                "origen": "manual", "creado_por": usuario,
            })
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    def archivar_adjunto_mensajeria(
        self, adjunto: dict, *, ejercicio: int, categoria_id: str,
        usuario: str = "",
    ) -> str:
        """Clasifica una descarga de chat usando el mismo repositorio documental."""
        source = Path(str(adjunto.get("ruta_entrada") or ""))
        category = next(
            (item for item in self.categorias() if item["id"] == categoria_id), None,
        )
        if not source.is_file() or not category:
            raise ValueError("El adjunto de mensajeria o la categoria no son validos.")
        content = source.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != str(adjunto.get("hash_archivo") or ""):
            raise ValueError("El adjunto local no supera la comprobacion de integridad.")
        duplicate = self._gestor.conn.execute(
            "SELECT id FROM documentos_archivo WHERE codigo_empresa=? AND hash_archivo=?",
            (adjunto["codigo_empresa"], digest),
        ).fetchone()
        if duplicate:
            source.unlink(missing_ok=True)
            return str(duplicate["id"])
        folder = self._category_directory(
            adjunto["codigo_empresa"], int(ejercicio), category["carpeta"],
        )
        filename = self._available_filename(folder, adjunto["nombre_original"])
        destination = folder / filename
        shutil.copy2(source, destination)
        try:
            document_id = self._gestor.registrar_documento_archivo({
                "codigo_empresa": adjunto["codigo_empresa"], "ejercicio": int(ejercicio),
                "categoria_id": categoria_id, "nombre_original": adjunto["nombre_original"],
                "nombre_archivo": filename, "ruta": str(destination), "hash_archivo": digest,
                "tamano": len(content), "mime_type": adjunto.get("mime_type"), "origen": "chat",
                "mensaje_id": adjunto.get("mensaje_remoto_id"),
                "correo_remitente": adjunto.get("remitente"), "correo_asunto": "Mensajeria cliente",
                "creado_por": usuario,
            })
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        source.unlink(missing_ok=True)
        return document_id

    def enviar_a_ocr(self, documento_id: str, usuario: str = "") -> dict:
        document = self._gestor.get_documento_archivo(documento_id)
        if not document:
            raise ValueError("Documento no encontrado.")
        if not bool(document.get("permite_ocr")):
            raise ValueError("La categoria del documento no permite enviarlo a OCR.")
        if document.get("ocr_documento_id"):
            raise ValueError("El documento ya fue enviado a OCR.")
        result = OcrService(
            self._gestor, document["codigo_empresa"], int(document["ejercicio"]),
            usuario=usuario,
        ).procesar_archivo(document["ruta"])
        ocr_id = str(result.get("documento_id") or "")
        if ocr_id:
            self._gestor.vincular_documento_archivo_ocr(documento_id, ocr_id)
        return result

    def eliminar_documento(self, documento_id: str) -> None:
        document = self._gestor.get_documento_archivo(documento_id)
        if not document:
            raise ValueError("Documento no encontrado.")
        if document.get("ocr_documento_id"):
            if self._gestor.get_documento_ocr(document["ocr_documento_id"]):
                raise ValueError(
                    "El documento ya fue enviado a OCR y no se puede eliminar desde aqui."
                )
            self._gestor.reconciliar_documentos_archivo_ocr(
                document["codigo_empresa"]
            )
        path = Path(str(document.get("ruta") or ""))
        temporary = None
        if path.is_file():
            temporary = path.with_name(f".eliminando-{uuid.uuid4().hex}-{path.name}")
            path.replace(temporary)
        try:
            deleted = self._gestor.eliminar_documento_archivo(documento_id)
            if not deleted:
                raise ValueError("Documento no encontrado.")
        except Exception:
            if temporary and temporary.exists():
                temporary.replace(path)
            raise
        if temporary:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _safe_name(value: str) -> str:
        return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(value).name).strip(". ") or "Documento"

    def _category_directory(self, codigo: str, ejercicio: int, folder: str) -> Path:
        digits = "".join(ch for ch in str(codigo) if ch.isdigit())
        company = f"E{digits.zfill(5)[:5]}"
        category_folder = CARPETAS_DOCUMENTALES.get(
            str(folder or "").strip().upper(), self._safe_name(folder),
        )
        destination = (
            get_document_repository_dir() / "Empresas" / company
            / str(int(ejercicio)) / category_folder
        )
        destination.mkdir(parents=True, exist_ok=True)
        return destination

    def _available_filename(self, folder: Path, name: str) -> str:
        safe = self._safe_name(name)
        candidate = folder / safe
        index = 2
        while candidate.exists():
            candidate = folder / f"{Path(safe).stem}_{index}{Path(safe).suffix}"
            index += 1
        return candidate.name
