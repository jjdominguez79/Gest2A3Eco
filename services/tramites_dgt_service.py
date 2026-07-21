from __future__ import annotations

import hashlib
import json
import os
import secrets
import uuid
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from xml.sax.saxutils import escape as xml_escape
from zipfile import ZIP_DEFLATED, ZipFile

from services.tramites_dgt_repository import DgtRepository, SQLiteDgtRepository
from utils.utilidades import get_app_data_dir, get_word_templates_dir
from utils.validaciones import normalizar_nif_cif, validar_nif_cif_nie


TIPO_COMPRAVENTA = "compraventa_cambio_titularidad"
DOCUMENTOS_BASE = (
    ("contrato_compraventa", "Contrato de compraventa"),
    ("mandato_dgt_comprador", "Mandato DGT comprador"),
    ("mandato_dgt_vendedor", "Mandato DGT vendedor"),
)
ROLES_PARTE = {"vendedor", "comprador"}
TEMPLATE_FILENAMES = {
    "contrato_compraventa": "dgt_contrato_compraventa.docx",
    "mandato_dgt_comprador": "dgt_mandato_comprador.docx",
    "mandato_dgt_vendedor": "dgt_mandato_vendedor.docx",
}


def get_protocol_url_from_argv(argv: list[str]) -> str:
    for arg in argv[1:] or []:
        raw = str(arg or "").strip()
        if raw.lower().startswith("gest2a3eco://tramites-dgt/"):
            return raw
    return ""


@dataclass(slots=True)
class LinkSeguro:
    rol: str
    token: str
    url: str


class TramitesDgtService:
    def __init__(self, gestor=None, session=None, repository: DgtRepository | None = None):
        if repository is None and gestor is None:
            raise ValueError("TramitesDgtService necesita un gestor SQLite o un DgtRepository.")
        self._repo = repository or SQLiteDgtRepository(gestor)
        self._session = session

    def crear_expediente_minimo(self, payload: dict) -> str:
        expediente_id = str(uuid.uuid4())
        vendedor = self._crear_link("vendedor")
        comprador = self._crear_link("comprador")
        referencia = self._siguiente_referencia()
        expediente = {
            "id": expediente_id,
            "referencia": referencia,
            "tipo": TIPO_COMPRAVENTA,
            "estado": "borrador",
            "titulo": str(payload.get("titulo") or "").strip() or referencia,
            "vendedor_nombre": str(payload.get("vendedor_nombre") or "").strip(),
            "vendedor_email": str(payload.get("vendedor_email") or "").strip(),
            "vendedor_telefono": self._normalizar_telefono(payload.get("vendedor_telefono")),
            "comprador_nombre": str(payload.get("comprador_nombre") or "").strip(),
            "comprador_email": str(payload.get("comprador_email") or "").strip(),
            "comprador_telefono": self._normalizar_telefono(payload.get("comprador_telefono")),
            "vehiculo_matricula": self._normalizar_matricula(payload.get("vehiculo_matricula")),
            "vehiculo_bastidor": str(payload.get("vehiculo_bastidor") or "").strip().upper(),
            "precio_venta": self._parse_float(payload.get("precio_venta")),
            "fecha_operacion": str(payload.get("fecha_operacion") or "").strip(),
            "observaciones": str(payload.get("observaciones") or "").strip(),
            "vendedor_token_hash": self._hash_token(vendedor.token),
            "comprador_token_hash": self._hash_token(comprador.token),
            "vendedor_token_created_at": self._now(),
            "comprador_token_created_at": self._now(),
            "firma_estado": "pendiente",
            "created_by": getattr(getattr(self._session, "user", None), "id", None),
        }
        self._repo.upsert_expediente(expediente)
        return expediente_id

    def guardar_expediente(self, expediente_id: str, payload: dict) -> None:
        actual = self._repo.get_expediente(expediente_id)
        if not actual:
            raise ValueError("Expediente DGT no encontrado.")
        actualizado = dict(actual)
        for key in (
            "titulo",
            "vendedor_nombre",
            "vendedor_email",
            "comprador_nombre",
            "comprador_email",
            "vehiculo_bastidor",
            "fecha_operacion",
            "observaciones",
        ):
            actualizado[key] = str(payload.get(key) or "").strip()
        actualizado["vendedor_telefono"] = self._normalizar_telefono(payload.get("vendedor_telefono"))
        actualizado["comprador_telefono"] = self._normalizar_telefono(payload.get("comprador_telefono"))
        actualizado["vehiculo_matricula"] = self._normalizar_matricula(payload.get("vehiculo_matricula"))
        actualizado["precio_venta"] = self._parse_float(payload.get("precio_venta"))
        if actualizado.get("estado") == "validado":
            actualizado["estado"] = "revision"
            actualizado["validado_por"] = None
            actualizado["validado_at"] = None
        self._repo.upsert_expediente(actualizado)

    def listar_expedientes(self) -> list[dict]:
        return self._repo.listar_expedientes()

    def get_expediente(self, expediente_id: str) -> dict | None:
        return self._repo.get_expediente(expediente_id)

    def get_links(self, expediente: dict) -> dict[str, str]:
        ref = expediente.get("referencia") or expediente.get("id")
        return {
            "vendedor": self._build_url("vendedor", ref),
            "comprador": self._build_url("comprador", ref),
        }

    def regenerar_links(self, expediente_id: str) -> dict[str, str]:
        expediente = self._repo.get_expediente(expediente_id)
        if not expediente:
            raise ValueError("Expediente DGT no encontrado.")
        vendedor = self._crear_link("vendedor")
        comprador = self._crear_link("comprador")
        expediente["vendedor_token_hash"] = self._hash_token(vendedor.token)
        expediente["comprador_token_hash"] = self._hash_token(comprador.token)
        expediente["vendedor_token_created_at"] = self._now()
        expediente["comprador_token_created_at"] = self._now()
        self._repo.upsert_expediente(expediente)
        ref = expediente.get("referencia") or expediente_id
        return {
            "vendedor": self._build_url("vendedor", ref, vendedor.token),
            "comprador": self._build_url("comprador", ref, comprador.token),
        }

    def verificar_token(self, referencia: str, rol: str, token: str) -> dict:
        rol = self._validar_rol(rol)
        expediente = self._repo.get_expediente_por_referencia(referencia)
        if not expediente:
            raise ValueError("Expediente DGT no encontrado.")
        stored_hash = str(expediente.get(f"{rol}_token_hash") or "")
        if not stored_hash or not secrets.compare_digest(stored_hash, self._hash_token(token)):
            raise PermissionError("Enlace DGT no valido o caducado.")
        return expediente

    def completar_desde_link(self, referencia: str, rol: str, token: str, payload: dict) -> None:
        expediente = self.verificar_token(referencia, rol, token)
        self.guardar_datos_parte(expediente["id"], rol, payload)

    def parse_link_seguro(self, url: str) -> dict:
        parsed = urlparse(str(url or "").strip())
        if parsed.scheme != "gest2a3eco" or parsed.netloc != "tramites-dgt":
            raise ValueError("El enlace no corresponde a Trámites DGT.")
        parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
        if len(parts) < 2:
            raise ValueError("El enlace DGT no contiene rol y referencia.")
        rol = self._validar_rol(parts[0])
        referencia = parts[1]
        token = (parse_qs(parsed.query).get("token") or [""])[0]
        if not token:
            raise ValueError("El enlace DGT no contiene token. Regenera el enlace antes de abrir el formulario.")
        return {"rol": rol, "referencia": referencia, "token": token}

    def guardar_datos_parte(self, expediente_id: str, rol: str, payload: dict) -> None:
        rol = self._validar_rol(rol)
        expediente = self._repo.get_expediente(expediente_id)
        if not expediente:
            raise ValueError("Expediente DGT no encontrado.")
        datos = self._normalizar_payload_parte(payload)
        expediente[f"{rol}_payload"] = datos
        if datos.get("nombre"):
            expediente[f"{rol}_nombre"] = datos["nombre"]
        if datos.get("email"):
            expediente[f"{rol}_email"] = datos["email"]
        if datos.get("telefono"):
            expediente[f"{rol}_telefono"] = datos["telefono"]
        if rol == "vendedor":
            if datos.get("vehiculo_matricula"):
                expediente["vehiculo_matricula"] = datos["vehiculo_matricula"]
            if datos.get("vehiculo_bastidor"):
                expediente["vehiculo_bastidor"] = datos["vehiculo_bastidor"]
            if datos.get("precio_venta") is not None:
                expediente["precio_venta"] = datos["precio_venta"]
            if datos.get("fecha_operacion"):
                expediente["fecha_operacion"] = datos["fecha_operacion"]
        if expediente.get("estado") in ("borrador", ""):
            expediente["estado"] = "pendiente_revision"
        if expediente.get("estado") == "validado":
            expediente["estado"] = "revision"
            expediente["validado_por"] = None
            expediente["validado_at"] = None
        self._repo.upsert_expediente(expediente)

    def adjuntar_documento(self, expediente_id: str, rol: str, file_path: str, tipo: str = "", descripcion: str = "") -> dict:
        rol = self._validar_rol(rol)
        expediente = self._repo.get_expediente(expediente_id)
        if not expediente:
            raise ValueError("Expediente DGT no encontrado.")
        path = Path(file_path).expanduser()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"No existe el documento adjunto: {path}")
        digest = self._hash_file(path)
        item = {
            "id": str(uuid.uuid4()),
            "rol": rol,
            "tipo": str(tipo or "").strip() or "documentacion",
            "descripcion": str(descripcion or "").strip(),
            "nombre_archivo": path.name,
            "ruta": str(path.resolve()),
            "sha256": digest,
            "added_at": self._now(),
        }
        documentos = list(expediente.get("documentos") or [])
        documentos.append(item)
        expediente["documentos"] = documentos
        if expediente.get("estado") == "validado":
            expediente["estado"] = "revision"
            expediente["validado_por"] = None
            expediente["validado_at"] = None
        self._repo.upsert_expediente(expediente)
        return item

    def validar_expediente(self, expediente_id: str) -> None:
        expediente = self._repo.get_expediente(expediente_id)
        if not expediente:
            raise ValueError("Expediente DGT no encontrado.")
        errors = self.validar_datos(expediente)
        if errors:
            raise ValueError("\n".join(errors))
        user_id = getattr(getattr(self._session, "user", None), "id", 0) or 0
        self._repo.validar_expediente(expediente_id, user_id)

    def validar_datos(self, expediente: dict) -> list[str]:
        errors = []
        if not str(expediente.get("vehiculo_matricula") or "").strip():
            errors.append("La matricula del vehiculo es obligatoria.")
        if not str(expediente.get("vendedor_nombre") or "").strip():
            errors.append("El nombre del vendedor es obligatorio.")
        if not str(expediente.get("comprador_nombre") or "").strip():
            errors.append("El nombre del comprador es obligatorio.")
        for rol in ("vendedor", "comprador"):
            payload = expediente.get(f"{rol}_payload") or {}
            nif = normalizar_nif_cif(payload.get("nif") or payload.get("dni") or "")
            if not nif:
                errors.append(f"El NIF/NIE/CIF del {rol} es obligatorio.")
            elif not validar_nif_cif_nie(nif):
                errors.append(f"El NIF/NIE/CIF del {rol} no es valido.")
            if not payload.get("direccion"):
                errors.append(f"La direccion del {rol} es obligatoria.")
        if not expediente.get("documentos"):
            errors.append("Debe existir al menos un documento adjunto.")
        return errors

    def generar_documentos(self, expediente_id: str) -> list[dict]:
        expediente = self._repo.get_expediente(expediente_id)
        if not expediente:
            raise ValueError("Expediente DGT no encontrado.")
        if expediente.get("estado") != "validado":
            raise ValueError("Valida expresamente el expediente antes de generar documentos.")
        out = []
        for tipo, titulo in DOCUMENTOS_BASE:
            generated = self._generar_documento(expediente, tipo, titulo)
            doc_id = self._repo.insertar_documento_generado(
                {
                    "expediente_id": expediente_id,
                    "tipo_documento": tipo,
                    "titulo": titulo,
                    "ruta_docx": generated.get("ruta_docx"),
                    "ruta_pdf": generated.get("ruta_pdf"),
                    "ruta_txt": generated.get("ruta_txt"),
                    "json_datos_generacion": self._document_context(expediente),
                    "hash_contenido": generated.get("hash_contenido"),
                    "estado": generated.get("estado"),
                }
            )
            out.append({"id": doc_id, "tipo_documento": tipo, "titulo": titulo, **generated})
        return out

    def preparar_paquete_firma(self, expediente_id: str, provider: str = "") -> dict:
        expediente = self._repo.get_expediente(expediente_id)
        if not expediente:
            raise ValueError("Expediente DGT no encontrado.")
        documentos = self._repo.listar_documentos_generados(expediente_id)
        rutas = []
        for doc in documentos:
            ruta = doc.get("ruta_pdf") or doc.get("ruta_docx") or doc.get("ruta_txt")
            if ruta:
                rutas.append(ruta)
        if not rutas:
            raise ValueError("Genera los documentos antes de preparar la firma.")
        expediente["firma_estado"] = "preparado"
        expediente["firma_provider"] = str(provider or "").strip()
        expediente["firma_request_id"] = ""
        self._repo.upsert_expediente(expediente)
        return {"expediente_id": expediente_id, "provider": expediente["firma_provider"], "documentos": rutas}

    def listar_documentos(self, expediente_id: str) -> list[dict]:
        return self._repo.listar_documentos_generados(expediente_id)

    def get_templates_dir(self) -> Path:
        path = Path(get_word_templates_dir()) / "tramites_dgt"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def listar_plantillas_editables(self) -> list[dict]:
        base = self.get_templates_dir()
        out = []
        for tipo, titulo in DOCUMENTOS_BASE:
            filename = TEMPLATE_FILENAMES[tipo]
            path = base / filename
            out.append(
                {
                    "tipo_documento": tipo,
                    "titulo": titulo,
                    "filename": filename,
                    "path": str(path),
                    "exists": path.exists(),
                }
            )
        return out

    def ensure_plantillas_editables(self, overwrite: bool = False) -> list[dict]:
        base = self.get_templates_dir()
        created = []
        for tipo, titulo in DOCUMENTOS_BASE:
            path = base / TEMPLATE_FILENAMES[tipo]
            if path.exists() and not overwrite:
                continue
            ok = self._create_editable_template(tipo, titulo, path)
            created.append(
                {
                    "tipo_documento": tipo,
                    "titulo": titulo,
                    "path": str(path),
                    "created": ok,
                }
            )
        return created

    def abrir_carpeta_plantillas(self) -> Path:
        path = self.get_templates_dir()
        self._open_path(path)
        return path

    def abrir_plantilla(self, tipo: str) -> Path:
        info = {item["tipo_documento"]: item for item in self.listar_plantillas_editables()}
        item = info.get(str(tipo or "").strip())
        if not item:
            raise ValueError("Tipo de plantilla DGT no valido.")
        path = Path(item["path"])
        if not path.exists():
            self._create_editable_template(item["tipo_documento"], item["titulo"], path)
        self._open_path(path)
        return path

    def abrir_whatsapp(self, telefono: str, mensaje: str) -> None:
        phone = self._normalizar_telefono(telefono)
        if not phone:
            raise ValueError("No hay telefono para WhatsApp.")
        webbrowser.open(f"https://wa.me/{phone}?text={quote(mensaje)}")

    def _crear_link(self, rol: str) -> LinkSeguro:
        token = secrets.token_urlsafe(32)
        return LinkSeguro(rol=rol, token=token, url="")

    def _build_url(self, rol: str, referencia: str, token: str = "") -> str:
        base = f"gest2a3eco://tramites-dgt/{rol}/{quote(str(referencia))}"
        return f"{base}?token={quote(token)}" if token else base

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(str(token).encode("utf-8")).hexdigest()

    def _siguiente_referencia(self) -> str:
        prefix = f"DGT-{datetime.now().year}-"
        rows = self._repo.listar_expedientes()
        nums = []
        for row in rows:
            ref = str(row.get("referencia") or "")
            if ref.startswith(prefix):
                try:
                    nums.append(int(ref.rsplit("-", 1)[1]))
                except Exception:
                    pass
        return f"{prefix}{(max(nums) + 1) if nums else 1:04d}"

    def _output_dir(self, expediente: dict) -> Path:
        ref = str(expediente.get("referencia") or expediente.get("id") or "sin_ref").replace("/", "_")
        path = get_app_data_dir() / "tramites_dgt" / ref
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _generar_documento(self, expediente: dict, tipo: str, titulo: str) -> dict:
        output_dir = self._output_dir(expediente)
        txt_path = output_dir / f"{tipo}.txt"
        contenido = self._render_documento_texto(expediente, titulo)
        txt_path.write_text(contenido, encoding="utf-8")
        result = {
            "ruta_txt": str(txt_path),
            "ruta_docx": None,
            "ruta_pdf": None,
            "hash_contenido": hashlib.sha256(contenido.encode("utf-8")).hexdigest(),
            "estado": "generado_txt",
        }
        docx_path = output_dir / f"{tipo}.docx"
        if self._render_docx(expediente, tipo, titulo, docx_path):
            result["ruta_docx"] = str(docx_path)
            result["hash_contenido"] = self._hash_file(docx_path)
            result["estado"] = "generado_docx"
            pdf_path = output_dir / f"{tipo}.pdf"
            if self._convertir_pdf(docx_path, pdf_path):
                result["ruta_pdf"] = str(pdf_path)
                result["hash_contenido"] = self._hash_file(pdf_path)
                result["estado"] = "generado_pdf"
        return result

    def _render_docx(self, expediente: dict, tipo: str, titulo: str, out_docx_path: Path) -> bool:
        template_path = self._buscar_template(tipo)
        context = self._document_context(expediente)
        context["titulo_documento"] = titulo
        if template_path:
            try:
                from procesos.facturas_word import render_docx

                render_docx(str(template_path), context, str(out_docx_path))
                return out_docx_path.exists()
            except Exception:
                pass
        return self._render_basic_docx(context, titulo, out_docx_path)

    def _buscar_template(self, tipo: str) -> Path | None:
        filename = TEMPLATE_FILENAMES.get(tipo)
        if not filename:
            return None
        base = Path(get_word_templates_dir())
        candidates = [
            base / "tramites_dgt" / filename,
            base / filename,
        ]
        for path in candidates:
            if path.exists() and path.is_file():
                return path
        return None

    def _render_basic_docx(self, context: dict, titulo: str, out_docx_path: Path) -> bool:
        try:
            from docx import Document
        except Exception:
            return self._render_minimal_docx(context, titulo, out_docx_path)
        try:
            doc = Document()
            doc.add_heading(titulo, level=1)
            rows = self._document_rows(context)
            table = doc.add_table(rows=0, cols=2)
            for label, value in rows:
                cells = table.add_row().cells
                cells[0].text = str(label)
                cells[1].text = "" if value is None else str(value)
            doc.add_paragraph("")
            doc.add_paragraph(
                "Documento generado por Gest2A3Eco. Sustituir por plantilla oficial antes de firma electronica."
            )
            out_docx_path.parent.mkdir(parents=True, exist_ok=True)
            doc.save(str(out_docx_path))
            return out_docx_path.exists()
        except Exception:
            return self._render_minimal_docx(context, titulo, out_docx_path)

    def _create_editable_template(self, tipo: str, titulo: str, path: Path) -> bool:
        context = self._empty_template_context()
        context["titulo_documento"] = titulo
        return self._render_basic_docx(context, titulo, path)

    def _empty_template_context(self) -> dict:
        return {
            "id": "",
            "referencia": "{{ referencia }}",
            "estado": "{{ estado }}",
            "titulo": "{{ titulo }}",
            "titulo_documento": "{{ titulo_documento }}",
            "vendedor_nombre": "{{ vendedor_nombre }}",
            "vendedor_nif": "{{ vendedor_nif }}",
            "comprador_nombre": "{{ comprador_nombre }}",
            "comprador_nif": "{{ comprador_nif }}",
            "vehiculo_matricula": "{{ vehiculo_matricula }}",
            "vehiculo_bastidor": "{{ vehiculo_bastidor }}",
            "precio_venta": "{{ precio_venta }}",
            "fecha_operacion": "{{ fecha_operacion }}",
            "observaciones": "{{ observaciones }}",
            "documentos_count": "{{ documentos_count }}",
            "documentos": [],
        }

    def _document_rows(self, context: dict) -> list[tuple[str, object]]:
        return [
            ("Referencia", context.get("referencia")),
            ("Vendedor", context.get("vendedor_nombre")),
            ("NIF vendedor", context.get("vendedor_nif")),
            ("Comprador", context.get("comprador_nombre")),
            ("NIF comprador", context.get("comprador_nif")),
            ("Matricula", context.get("vehiculo_matricula")),
            ("Bastidor", context.get("vehiculo_bastidor")),
            ("Precio venta", context.get("precio_venta")),
            ("Fecha operacion", context.get("fecha_operacion")),
            ("Documentos adjuntos", context.get("documentos_count")),
        ]

    def _render_minimal_docx(self, context: dict, titulo: str, out_docx_path: Path) -> bool:
        paragraphs = [titulo]
        paragraphs.extend(f"{label}: {'' if value is None else value}" for label, value in self._document_rows(context))
        paragraphs.append("Documento generado por Gest2A3Eco. Sustituir por plantilla oficial antes de firma electronica.")
        body = "".join(f"<w:p><w:r><w:t>{xml_escape(str(text))}</w:t></w:r></w:p>" for text in paragraphs)
        document_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{body}<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/>"
            '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body>'
            "</w:document>"
        )
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>"
        )
        rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/>'
            "</Relationships>"
        )
        try:
            out_docx_path.parent.mkdir(parents=True, exist_ok=True)
            with ZipFile(out_docx_path, "w", ZIP_DEFLATED) as zf:
                zf.writestr("[Content_Types].xml", content_types)
                zf.writestr("_rels/.rels", rels)
                zf.writestr("word/document.xml", document_xml)
            return out_docx_path.exists()
        except Exception:
            return False

    def _convertir_pdf(self, docx_path: Path, pdf_path: Path) -> bool:
        try:
            from procesos.facturas_word import convert_docx_to_pdf

            convert_docx_to_pdf(str(docx_path), str(pdf_path))
            return pdf_path.exists()
        except Exception:
            return False

    def _render_documento_texto(self, expediente: dict, titulo: str) -> str:
        ctx = self._document_context(expediente)
        return (
            f"{titulo}\n"
            f"Referencia: {ctx['referencia']}\n"
            f"Estado: {ctx['estado']}\n\n"
            f"Vendedor: {ctx['vendedor_nombre']}\n"
            f"NIF vendedor: {ctx['vendedor_nif']}\n"
            f"Comprador: {ctx['comprador_nombre']}\n"
            f"NIF comprador: {ctx['comprador_nif']}\n"
            f"Vehiculo: {ctx['vehiculo_matricula']} / {ctx['vehiculo_bastidor']}\n"
            f"Precio: {ctx['precio_venta']}\n"
            f"Fecha operacion: {ctx['fecha_operacion']}\n\n"
            f"Documentos adjuntos: {ctx['documentos_count']}\n\n"
            "Documento preliminar generado por Gest2A3Eco. Pendiente de plantilla DOCX/PDF y firma electronica.\n"
        )

    def _document_context(self, expediente: dict) -> dict:
        keys = (
            "id",
            "referencia",
            "estado",
            "titulo",
            "vendedor_nombre",
            "comprador_nombre",
            "vehiculo_matricula",
            "vehiculo_bastidor",
            "precio_venta",
            "fecha_operacion",
            "observaciones",
        )
        ctx = {key: expediente.get(key) for key in keys}
        vendedor_payload = expediente.get("vendedor_payload") or {}
        comprador_payload = expediente.get("comprador_payload") or {}
        ctx["vendedor_nif"] = vendedor_payload.get("nif") or ""
        ctx["comprador_nif"] = comprador_payload.get("nif") or ""
        ctx["documentos"] = expediente.get("documentos") or []
        ctx["documentos_count"] = len(ctx["documentos"])
        return ctx

    def _parse_float(self, value):
        raw = str(value or "").strip().replace(".", "").replace(",", ".")
        if not raw:
            return None
        try:
            return float(raw)
        except Exception:
            return None

    def _normalizar_matricula(self, value) -> str:
        return "".join(ch for ch in str(value or "").upper() if ch.isalnum())

    def _normalizar_telefono(self, value) -> str:
        raw = "".join(ch for ch in str(value or "") if ch.isdigit() or ch == "+")
        if raw.startswith("+"):
            return raw[1:]
        return raw

    def _now(self) -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat()

    def _validar_rol(self, rol: str) -> str:
        rol = str(rol or "").strip().lower()
        if rol not in ROLES_PARTE:
            raise ValueError("Rol DGT no valido.")
        return rol

    def _normalizar_payload_parte(self, payload: dict) -> dict:
        out = {
            "nombre": str(payload.get("nombre") or "").strip(),
            "nif": normalizar_nif_cif(payload.get("nif") or payload.get("dni") or ""),
            "email": str(payload.get("email") or "").strip(),
            "telefono": self._normalizar_telefono(payload.get("telefono")),
            "direccion": str(payload.get("direccion") or "").strip(),
            "cp": str(payload.get("cp") or "").strip(),
            "poblacion": str(payload.get("poblacion") or "").strip(),
            "provincia": str(payload.get("provincia") or "").strip(),
            "representante": str(payload.get("representante") or "").strip(),
            "observaciones": str(payload.get("observaciones") or "").strip(),
        }
        out["vehiculo_matricula"] = self._normalizar_matricula(payload.get("vehiculo_matricula"))
        out["vehiculo_bastidor"] = str(payload.get("vehiculo_bastidor") or "").strip().upper()
        out["precio_venta"] = self._parse_float(payload.get("precio_venta"))
        out["fecha_operacion"] = str(payload.get("fecha_operacion") or "").strip()
        return out

    def _hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _open_path(self, path: Path) -> None:
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except AttributeError:
            webbrowser.open(path.resolve().as_uri())
