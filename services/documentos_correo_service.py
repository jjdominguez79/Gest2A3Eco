"""Entrada manual de adjuntos de Microsoft 365 a la captura documental."""
from __future__ import annotations

import base64
import hashlib
import re
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from services.graph_mail_service import GraphMailService
from services.ocr.ocr_service import OcrService
from utils.utilidades import get_default_received_documents_dir


SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
PREVIEW_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff",
    ".txt", ".xml", ".csv",
    # Documentos de oficina y libros Excel. Los abre la aplicacion asociada;
    # los formatos con macros siguen sujetos a la configuracion de Office.
    ".xls", ".xlsx", ".xlsm", ".xlsb",
    # Comprimidos: se abren con el explorador/gestor de archivos asociado,
    # nunca se ejecutan desde la aplicacion.
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".tgz",
}
MAX_PREVIEW_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 500
MAX_ARCHIVE_UNPACK_BYTES = 200 * 1024 * 1024


@dataclass
class ImportSummary:
    imported: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class DocumentosCorreoService:
    def __init__(self, gestor, graph: GraphMailService | None = None):
        self._gestor = gestor
        self._graph = graph or GraphMailService()

    def listar_adjuntos(self, *, mailbox: str, graph_message_id: str) -> list[dict]:
        return self._graph.list_attachments(
            mailbox=mailbox, message_id=graph_message_id,
        )

    def descargar_adjunto_temporal(
        self, *, mailbox: str, graph_message_id: str, attachment_id: str,
    ) -> Path:
        """Descarga un adjunto seguro a una carpeta temporal para revisarlo."""
        item = self._graph.download_attachment(
            mailbox=mailbox, message_id=graph_message_id,
            attachment_id=attachment_id,
        )
        name = str(item.get("name") or "adjunto").strip() or "adjunto"
        suffix = Path(name).suffix.lower()
        if suffix not in PREVIEW_EXTENSIONS:
            raise ValueError(
                f"El formato {suffix or '(sin extension)'} no se abre por seguridad. "
                "Puedes revisarlo desde Microsoft 365."
            )
        content = base64.b64decode(item.get("contentBytes") or "", validate=True)
        if len(content) > MAX_PREVIEW_BYTES:
            raise ValueError("El adjunto supera el limite de vista previa de 50 MB.")
        directory = Path(tempfile.gettempdir()) / "Gest2A3Eco" / "adjuntos_preview"
        directory.mkdir(parents=True, exist_ok=True)
        self._limpiar_vistas_previas(directory)
        safe = self._safe_filename(name)
        token = hashlib.sha256(
            f"{graph_message_id}:{attachment_id}".encode("utf-8")
        ).hexdigest()[:12]
        destination = directory / f"{token}_{safe}"
        destination.write_bytes(content)
        return destination

    @staticmethod
    def listar_contenido_zip(archive: str | Path) -> list[dict]:
        """Lista un ZIP sin extraerlo ni ejecutar ninguno de sus contenidos."""
        archive = Path(archive)
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise ValueError("El ZIP contiene demasiados archivos para revisarlo.")
            result = []
            total = 0
            for info in members:
                name = info.filename.replace("\\", "/")
                if not name or name.endswith("/"):
                    continue
                DocumentosCorreoService._validar_ruta_zip(name)
                total += int(info.file_size or 0)
                if total > MAX_ARCHIVE_UNPACK_BYTES:
                    raise ValueError("El contenido del ZIP supera el limite de 200 MB.")
                result.append({"name": name, "size": int(info.file_size or 0)})
            return result

    @staticmethod
    def extraer_zip_temporal(archive: str | Path, member_name: str) -> Path:
        """Extrae un único miembro a la carpeta temporal, validando su ruta."""
        archive = Path(archive)
        DocumentosCorreoService._validar_ruta_zip(member_name)
        with zipfile.ZipFile(archive) as bundle:
            try:
                info = bundle.getinfo(member_name)
            except KeyError as exc:
                raise ValueError("El documento ya no existe dentro del ZIP.") from exc
            if info.is_dir() or int(info.file_size or 0) > MAX_PREVIEW_BYTES:
                raise ValueError("El documento supera el limite de vista previa de 50 MB.")
            directory = Path(tempfile.gettempdir()) / "Gest2A3Eco" / "adjuntos_preview"
            directory.mkdir(parents=True, exist_ok=True)
            safe = DocumentosCorreoService._safe_filename(Path(member_name).name)
            token = hashlib.sha256(f"{archive}:{member_name}".encode("utf-8")).hexdigest()[:12]
            destination = directory / f"{token}_{safe}"
            destination.write_bytes(bundle.read(info))
            return destination

    @staticmethod
    def _validar_ruta_zip(name: str) -> None:
        path = Path(name)
        if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
            raise ValueError("El ZIP contiene una ruta no segura y no se puede abrir.")

    def importar_adjuntos(
        self, *, codigo_empresa: str, ejercicio: int, mensaje_id: str,
        mailbox: str, graph_message_id: str, attachment_ids: list[str], usuario: str = "",
    ) -> ImportSummary:
        summary = ImportSummary()
        ocr = OcrService(self._gestor, codigo_empresa, ejercicio, usuario=usuario)
        for attachment_id in dict.fromkeys(attachment_ids):
            try:
                item = self._graph.download_attachment(
                    mailbox=mailbox, message_id=graph_message_id,
                    attachment_id=attachment_id,
                )
                name = str(item.get("name") or "adjunto").strip() or "adjunto"
                suffix = Path(name).suffix.lower()
                if suffix not in SUPPORTED_EXTENSIONS:
                    summary.unsupported.append(name)
                    continue
                content = base64.b64decode(item["contentBytes"], validate=True)
                digest = hashlib.sha256(content).hexdigest()
                if self._gestor.buscar_documento_ocr_por_hash(codigo_empresa, digest):
                    summary.duplicates.append(name)
                    continue
                destination = self._destination(codigo_empresa, ejercicio, name)
                destination.write_bytes(content)
                result = ocr.procesar_archivo(str(destination))
                if result.get("estado") == "duplicado":
                    destination.unlink(missing_ok=True)
                    summary.duplicates.append(name)
                    continue
                self._gestor.registrar_adjunto_comunicacion(
                    mensaje_id, destination, int(item.get("size") or len(content)),
                )
                summary.imported.append(name)
            except Exception as exc:
                summary.errors.append(f"{attachment_id}: {exc}")
        return summary

    @staticmethod
    def _destination(codigo_empresa: str, ejercicio: int, filename: str) -> Path:
        safe = DocumentosCorreoService._safe_filename(filename)
        digits = "".join(ch for ch in str(codigo_empresa) if ch.isdigit())
        company = f"E{digits.zfill(5)[:5]}"
        directory = (
            get_default_received_documents_dir() / company
            / str(ejercicio) / "Facturas_recibidas"
        )
        directory.mkdir(parents=True, exist_ok=True)
        candidate = directory / safe
        index = 2
        while candidate.exists():
            candidate = directory / f"{Path(safe).stem}_{index}{Path(safe).suffix}"
            index += 1
        return candidate

    @staticmethod
    def _safe_filename(filename: str) -> str:
        safe = re.sub(
            r'[<>:"/\\|?*\x00-\x1f]', "_", Path(filename).name,
        ).strip(". ")
        return safe or "adjunto"

    @staticmethod
    def _limpiar_vistas_previas(directory: Path) -> None:
        limit = time.time() - 24 * 60 * 60
        for path in directory.iterdir():
            try:
                if path.is_file() and path.stat().st_mtime < limit:
                    path.unlink()
            except OSError:
                pass
