"""Archivo documental por cliente y puente selectivo hacia OCR."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import mimetypes
import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from services.backend_mail_service import BackendMailService
from services.ocr.ocr_service import OcrService
from services.ocr.background_service import OcrBackgroundService
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

logger = logging.getLogger(__name__)

MAX_MIEMBROS_ZIP = 500
MAX_TAMANO_DESCOMPRIMIDO_ZIP = 200 * 1024 * 1024


@dataclass
class ArchiveSummary:
    saved: list[str] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)
    ocr_document_ids: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class GestionDocumentalService:
    def __init__(self, gestor, graph=None):
        self._gestor = gestor
        # Los adjuntos de correo se consultan mediante el backend, igual que
        # en la vista previa. Las credenciales de Microsoft Graph no deben
        # depender de la configuracion local de cada puesto.
        self._graph = graph or BackendMailService()

    def categorias(self) -> list[dict]:
        return self._gestor.listar_categorias_documentales()

    @staticmethod
    def _mailbox_entrada(entrada: dict) -> str:
        mailbox = str(entrada.get("mailbox") or "").strip().lower()
        if not mailbox:
            try:
                payload = json.loads(entrada.get("payload_json") or "{}")
            except (TypeError, ValueError):
                payload = {}
            mailbox = str(payload.get("mailbox") or "").strip().lower()
        if not mailbox:
            origen = " ".join((
                str(entrada.get("etiqueta") or ""),
                str(entrada.get("origen_label") or ""),
            )).casefold()
            if "documentacion" in origen:
                mailbox = "documentacion@gestinem.es"
            elif "oficina" in origen:
                mailbox = "oficina@gestinem.es"
        if "@" not in mailbox:
            raise ValueError(
                "No se ha podido identificar el buzon de origen del correo. "
                "Pulsa Actualizar y vuelve a intentarlo."
            )
        return mailbox

    def archivar_adjuntos_correo(
        self, *, codigo_empresa: str, ejercicio: int, mailbox: str,
        graph_message_id: str, remitente: str, asunto: str,
        decisiones: list[dict], usuario: str = "", comunicacion_id: str = "",
    ) -> ArchiveSummary:
        summary = ArchiveSummary()
        categorias = {item["id"]: item for item in self.categorias()}
        descargas: dict[str, tuple[dict, bytes]] = {}
        for decision in decisiones:
            attachment_id = str(decision.get("attachment_id") or "")
            name = str(decision.get("name") or "Adjunto")
            member_name = str(decision.get("archive_member") or "")
            decision_attachment_id = str(
                decision.get("decision_attachment_id") or attachment_id
            )
            category_id = str(decision.get("categoria_id") or "")
            if not category_id:
                self._gestor.registrar_decision_adjunto({
                    "graph_message_id": graph_message_id,
                    "graph_attachment_id": decision_attachment_id,
                    "nombre": name, "accion": "no_guardar",
                })
                summary.ignored.append(name)
                continue
            category = categorias.get(category_id)
            if not category:
                summary.errors.append(f"{name}: categoria no valida")
                continue
            try:
                if attachment_id not in descargas:
                    item = self._graph.download_attachment(
                        mailbox=mailbox, message_id=graph_message_id,
                        attachment_id=attachment_id,
                    )
                    contenido_adjunto = base64.b64decode(
                        item.get("contentBytes") or "", validate=True,
                    )
                    descargas[attachment_id] = (item, contenido_adjunto)
                item, contenido_adjunto = descargas[attachment_id]
                content = contenido_adjunto
                if member_name:
                    content = self._extraer_miembro_zip(
                        contenido_adjunto,
                        member_name,
                        int(decision.get("archive_member_index") or 0),
                    )
                digest = hashlib.sha256(content).hexdigest()
                duplicate = self._gestor.conn.execute(
                    "SELECT id FROM documentos_archivo WHERE codigo_empresa=? "
                    "AND hash_archivo=? LIMIT 1", (codigo_empresa, digest),
                ).fetchone()
                if duplicate:
                    summary.duplicates.append(name)
                    summary.document_ids.append(str(duplicate["id"]))
                    self._gestor.registrar_decision_adjunto({
                        "graph_message_id": graph_message_id,
                        "graph_attachment_id": decision_attachment_id, "nombre": name,
                        "accion": "duplicado", "categoria_id": category_id,
                        "documento_id": duplicate["id"],
                    })
                    continue
                folder = self._category_directory(
                    codigo_empresa, ejercicio, category["carpeta"],
                )
                filename = self._available_filename(folder, name)
                destination = folder / filename
                mime_type = (
                    mimetypes.guess_type(name)[0]
                    if member_name else
                    item.get("contentType") or mimetypes.guess_type(name)[0]
                )
                destination.write_bytes(content)
                try:
                    document_id = self._gestor.registrar_documento_archivo({
                        "id": str(uuid.uuid4()), "codigo_empresa": codigo_empresa,
                        "ejercicio": ejercicio, "categoria_id": category_id,
                        "nombre_original": name, "nombre_archivo": filename,
                        "ruta": str(destination), "hash_archivo": digest,
                        "tamano": len(content),
                        "mime_type": mime_type,
                        "origen": "correo", "buzon_origen": mailbox,
                        "comunicacion_id": comunicacion_id or None,
                        "graph_message_id": graph_message_id,
                        "graph_attachment_id": decision_attachment_id,
                        "correo_remitente": remitente, "correo_asunto": asunto,
                        "creado_por": usuario,
                    })
                except Exception:
                    destination.unlink(missing_ok=True)
                    raise
                self._gestor.registrar_decision_adjunto({
                    "graph_message_id": graph_message_id,
                    "graph_attachment_id": decision_attachment_id, "nombre": name,
                    "accion": "guardado", "categoria_id": category_id,
                    "documento_id": document_id,
                })
                summary.saved.append(name)
                summary.document_ids.append(document_id)
                if bool(category.get("permite_ocr")):
                    summary.ocr_document_ids.append(document_id)
                    self._encolar_ocr(document_id, usuario=usuario)
            except Exception as exc:
                summary.errors.append(f"{name}: {exc}")
        return summary

    def clasificar_entrada_documental(
        self, entrada: dict, *, ejercicio: int, categoria_id: str,
        usuario: str = "", usuario_id: int = 0,
        attachment_ids: list[str] | None = None,
        selecciones_adjuntos: list[dict] | None = None,
    ) -> ArchiveSummary:
        """Clasifica una entrada de correo o mensajeria con el mismo flujo."""
        canal = str(entrada.get("canal") or "mensajeria").strip().lower()
        if canal == "correo":
            graph_id = str(
                entrada.get("graph_message_id")
                or entrada.get("entrada_id")
                or ""
            )
            mailbox = self._mailbox_entrada(entrada)
            if selecciones_adjuntos is not None:
                decisions = [
                    {
                        **seleccion,
                        "categoria_id": (
                            categoria_id
                            if seleccion.get("seleccionado", True) else ""
                        ),
                    }
                    for seleccion in selecciones_adjuntos
                ]
            else:
                attachments = self.listar_adjuntos_entrada_correo(entrada)
                seleccionados = (
                    {str(value) for value in attachment_ids}
                    if attachment_ids is not None else None
                )
                decisions = [
                    {
                        "attachment_id": attachment.get("id"),
                        "name": attachment.get("name") or "Adjunto",
                        "categoria_id": categoria_id,
                    }
                    for attachment in attachments
                    if seleccionados is None
                    or str(attachment.get("id") or "") in seleccionados
                ]
            if not decisions:
                raise ValueError("El correo ya no contiene adjuntos disponibles.")
            summary = self.archivar_adjuntos_correo(
                codigo_empresa=str(entrada.get("codigo_empresa") or ""),
                ejercicio=int(ejercicio), mailbox=mailbox,
                graph_message_id=graph_id,
                remitente=str(entrada.get("remitente") or ""),
                asunto=str(entrada.get("asunto") or ""),
                decisiones=decisions, usuario=usuario,
            )
            if summary.errors:
                raise RuntimeError("\n".join(summary.errors))
            assigned = self._gestor.asignar_comunicacion_pendiente(
                graph_id, str(entrada.get("codigo_empresa") or ""),
                int(usuario_id), usuario or "sistema",
            )
            if not assigned:
                raise RuntimeError("El correo ya no esta pendiente de asignacion.")
            self._gestor.vincular_documentos_graph_comunicacion(graph_id)
            # La clasificacion documental completa la gestion funcional del
            # correo. Outlook se actualiza a continuacion, pero un fallo de
            # red no debe volver a dejarlo pendiente en Comunicaciones.
            self._gestor.cambiar_estado_comunicacion(
                assigned[0], "gestionado", int(usuario_id),
            )
            try:
                self._graph.mark_as_read(mailbox=mailbox, message_id=graph_id)
            except Exception as exc:
                logger.warning(
                    "No se pudo marcar como leido el correo %s de %s: %s",
                    graph_id, mailbox, exc,
                )
                summary.warnings.append(
                    "El correo se ha archivado, pero Outlook no pudo marcarlo "
                    f"como leido: {exc}"
                )
            return summary

        entrada_id = str(entrada.get("entrada_id") or entrada.get("id") or "")
        categoria = next(
            (item for item in self.categorias() if item["id"] == categoria_id),
            {"nombre": categoria_id},
        )
        document_id = self.archivar_adjunto_mensajeria(
            entrada, ejercicio=int(ejercicio), categoria_id=categoria_id,
            usuario=usuario,
        )
        self._gestor.actualizar_adjunto_mensajeria_entrada(
            entrada_id, "archivado", documento_id=document_id,
        )
        self._gestor.marcar_adjunto_mensajeria_revisado(
            entrada_id, revisado_por=usuario or "sistema",
            clasificacion=str(categoria.get("nombre") or categoria_id),
            documento_id=document_id,
        )
        return ArchiveSummary(
            saved=[str(entrada.get("nombre_original") or "Documento")],
            document_ids=[document_id],
        )

    def listar_adjuntos_entrada_correo(self, entrada: dict) -> list[dict]:
        return self._graph.list_attachments(
            mailbox=self._mailbox_entrada(entrada),
            message_id=str(
                entrada.get("graph_message_id")
                or entrada.get("entrada_id")
                or ""
            ),
        )

    def no_guardar_entrada_correo(
        self, entrada: dict, *, usuario: str = "", usuario_id: int = 0,
    ) -> ArchiveSummary:
        """Cierra un correo documental sin archivar sus adjuntos."""
        graph_id = str(
            entrada.get("graph_message_id")
            or entrada.get("entrada_id")
            or ""
        )
        mailbox = self._mailbox_entrada(entrada)
        summary = ArchiveSummary()
        for attachment in self.listar_adjuntos_entrada_correo(entrada):
            attachment_id = str(attachment.get("id") or "")
            name = str(attachment.get("name") or "Adjunto")
            self._gestor.registrar_decision_adjunto({
                "graph_message_id": graph_id,
                "graph_attachment_id": attachment_id,
                "nombre": name,
                "accion": "no_guardar",
            })
            summary.ignored.append(name)
        assigned = self._gestor.asignar_comunicacion_pendiente(
            graph_id, str(entrada.get("codigo_empresa") or ""),
            int(usuario_id), usuario or "sistema",
        )
        if not assigned:
            raise RuntimeError("El correo ya no esta pendiente de asignacion.")
        self._gestor.cambiar_estado_comunicacion(
            assigned[0], "gestionado", int(usuario_id),
        )
        try:
            self._graph.mark_as_read(mailbox=mailbox, message_id=graph_id)
        except Exception as exc:
            logger.warning(
                "No se pudo marcar como leido el correo %s de %s: %s",
                graph_id, mailbox, exc,
            )
            summary.warnings.append(
                "El correo se ha cerrado, pero Outlook no pudo marcarlo "
                f"como leido: {exc}"
            )
        return summary

    def listar_opciones_clasificacion_correo(self, entrada: dict) -> list[dict]:
        """Despliega los ZIP para seleccionar documentos, no el contenedor."""
        mailbox = self._mailbox_entrada(entrada)
        graph_id = str(
            entrada.get("graph_message_id")
            or entrada.get("entrada_id")
            or ""
        )
        opciones: list[dict] = []
        for attachment in self.listar_adjuntos_entrada_correo(entrada):
            attachment_id = str(attachment.get("id") or "")
            name = str(attachment.get("name") or "Adjunto").strip() or "Adjunto"
            if Path(name).suffix.lower() != ".zip":
                opciones.append({
                    "key": f"adjunto:{attachment_id}",
                    "attachment_id": attachment_id,
                    "name": name,
                    "size": int(attachment.get("size") or 0),
                    "origen": "Adjunto del correo",
                })
                continue
            item = self._graph.download_attachment(
                mailbox=mailbox, message_id=graph_id,
                attachment_id=attachment_id,
            )
            try:
                content = base64.b64decode(
                    item.get("contentBytes") or "", validate=True,
                )
                members = self._listar_miembros_zip(content)
            except Exception as exc:
                raise ValueError(
                    f"No se pudo revisar el contenido de {name}: {exc}"
                ) from exc
            if not members:
                raise ValueError(f"El archivo {name} no contiene documentos.")
            for member in members:
                member_name = str(member["name"])
                member_index = int(member["index"])
                token = hashlib.sha256(
                    f"{member_index}:{member_name}".encode("utf-8")
                ).hexdigest()[:16]
                opciones.append({
                    "key": f"zip:{attachment_id}:{token}",
                    "attachment_id": attachment_id,
                    "decision_attachment_id": f"{attachment_id}::zip::{token}",
                    "archive_member": member_name,
                    "archive_member_index": member_index,
                    "archive_name": name,
                    "name": PurePosixPath(member_name).name,
                    "display_name": member_name,
                    "size": int(member["size"]),
                    "origen": f"Dentro de {name}",
                })
        return opciones

    @classmethod
    def _listar_miembros_zip(cls, content: bytes) -> list[dict]:
        with zipfile.ZipFile(io.BytesIO(content)) as bundle:
            members = bundle.infolist()
            if len(members) > MAX_MIEMBROS_ZIP:
                raise ValueError("el ZIP contiene mas de 500 elementos")
            total = 0
            result = []
            for index, info in enumerate(members):
                name = str(info.filename or "").replace("\\", "/")
                if not name or name.endswith("/"):
                    continue
                cls._validar_nombre_miembro_zip(name)
                if info.flag_bits & 0x1:
                    raise ValueError("el ZIP contiene archivos protegidos con contrasena")
                total += int(info.file_size or 0)
                if total > MAX_TAMANO_DESCOMPRIMIDO_ZIP:
                    raise ValueError("el contenido del ZIP supera 200 MB")
                result.append({
                    "name": name,
                    "size": int(info.file_size or 0),
                    "index": index,
                })
            return result

    @classmethod
    def _extraer_miembro_zip(
        cls, content: bytes, member_name: str, member_index: int,
    ) -> bytes:
        cls._validar_nombre_miembro_zip(member_name)
        with zipfile.ZipFile(io.BytesIO(content)) as bundle:
            members = bundle.infolist()
            if member_index < 0 or member_index >= len(members):
                raise ValueError("el documento ya no existe dentro del ZIP")
            info = members[member_index]
            current_name = str(info.filename or "").replace("\\", "/")
            if current_name != member_name or info.is_dir():
                raise ValueError("el contenido del ZIP ha cambiado")
            if int(info.file_size or 0) > MAX_TAMANO_DESCOMPRIMIDO_ZIP:
                raise ValueError("el documento del ZIP supera 200 MB")
            return bundle.read(info)

    @staticmethod
    def _validar_nombre_miembro_zip(name: str) -> None:
        normalized = str(name or "").replace("\\", "/")
        parts = normalized.split("/")
        if (
            not normalized
            or normalized.startswith("/")
            or any(part in {"", ".", ".."} for part in parts)
            or (parts and parts[0].endswith(":"))
        ):
            raise ValueError("el ZIP contiene una ruta no segura")

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
            document_id = self._gestor.registrar_documento_archivo({
                "codigo_empresa": codigo_empresa, "ejercicio": ejercicio,
                "categoria_id": categoria_id, "nombre_original": source.name,
                "nombre_archivo": filename, "ruta": str(destination),
                "hash_archivo": digest, "tamano": len(content),
                "mime_type": mimetypes.guess_type(source.name)[0],
                "origen": "manual", "creado_por": usuario,
            })
            if bool(category.get("permite_ocr")):
                self._encolar_ocr(document_id, usuario=usuario)
            return document_id
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    def importar_archivos(
        self, *, codigo_empresa: str, ejercicio: int, categoria_id: str,
        sources: list[str | Path], usuario: str = "",
    ) -> ArchiveSummary:
        """Incorpora un lote y conserva los errores individuales del resto."""
        summary = ArchiveSummary()
        for source in sources:
            path = Path(source)
            try:
                document_id = self.importar_archivo(
                    codigo_empresa=codigo_empresa,
                    ejercicio=ejercicio,
                    categoria_id=categoria_id,
                    source=path,
                    usuario=usuario,
                )
                summary.saved.append(path.name)
                summary.document_ids.append(document_id)
            except Exception as exc:
                summary.errors.append(f"{path.name}: {exc}")
        return summary

    def reclasificar_documento(
        self, documento_id: str, categoria_id: str, *, usuario: str = "",
    ) -> bool:
        documento = self._gestor.get_documento_archivo(str(documento_id))
        if not documento:
            raise ValueError("Documento no encontrado.")
        categoria = next(
            (item for item in self.categorias() if item["id"] == categoria_id),
            None,
        )
        if not categoria:
            raise ValueError("La categoria de destino no existe o no esta activa.")
        if str(documento.get("categoria_id") or "") == str(categoria_id):
            return False

        origen = Path(str(documento.get("ruta") or ""))
        if not origen.is_file():
            raise FileNotFoundError(f"El archivo no se encuentra en: {origen}")
        carpeta = self._category_directory(
            str(documento["codigo_empresa"]), int(documento["ejercicio"]),
            str(categoria["carpeta"]),
        )
        carpeta.mkdir(parents=True, exist_ok=True)
        nombre = self._available_filename(
            carpeta,
            str(documento.get("nombre_archivo") or documento.get("nombre_original")),
        )
        destino = carpeta / nombre
        shutil.move(str(origen), str(destino))
        try:
            cambiado = self._gestor.reclasificar_documento_archivo(
                str(documento_id), str(categoria_id), ruta=str(destino),
                nombre_archivo=nombre,
            )
        except Exception:
            try:
                if destino.exists() and not origen.exists():
                    origen.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(destino), str(origen))
            except OSError:
                logger.exception(
                    "No se pudo devolver %s tras fallar su reclasificacion", destino,
                )
            raise
        if cambiado and bool(categoria.get("permite_ocr")):
            self._encolar_ocr(str(documento_id), usuario=usuario)
        return bool(cambiado)

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
        if bool(category.get("permite_ocr")):
            self._encolar_ocr(document_id, usuario=usuario)
        return document_id

    def _encolar_ocr(self, documento_id: str, *, usuario: str = "") -> bool:
        """Envia facturas al OCR durable desde cualquier canal de entrada."""
        if not hasattr(self._gestor, "encolar_trabajo_ocr"):
            return False
        document = self._gestor.get_documento_archivo(documento_id)
        if not document or document.get("ocr_documento_id"):
            return False
        try:
            _job_id, created = OcrBackgroundService(self._gestor).encolar(
                empresa_id=str(document["codigo_empresa"]),
                ejercicio=int(document["ejercicio"]),
                ruta_origen=str(document["ruta"]),
                documento_archivo_id=str(documento_id),
                usuario=usuario,
            )
            return bool(created)
        except Exception as exc:
            # El documento ya esta a salvo en el archivo. El fallo queda
            # visible y puede reintentarse desde Gestion documental.
            logger.warning("No se pudo encolar %s para OCR: %s", documento_id, exc)
            return False

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
