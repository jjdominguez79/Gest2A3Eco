from __future__ import annotations

import hashlib
import json
import secrets
import uuid
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from utils.utilidades import get_app_data_dir
from utils.validaciones import normalizar_nif_cif, validar_nif_cif_nie


TIPO_COMPRAVENTA = "compraventa_cambio_titularidad"
DOCUMENTOS_BASE = (
    ("contrato_compraventa", "Contrato de compraventa"),
    ("mandato_dgt_comprador", "Mandato DGT comprador"),
    ("mandato_dgt_vendedor", "Mandato DGT vendedor"),
)
ROLES_PARTE = {"vendedor", "comprador"}


@dataclass(slots=True)
class LinkSeguro:
    rol: str
    token: str
    url: str


class TramitesDgtService:
    def __init__(self, gestor, session=None):
        self._gestor = gestor
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
        self._gestor.upsert_dgt_expediente(expediente)
        return expediente_id

    def guardar_expediente(self, expediente_id: str, payload: dict) -> None:
        actual = self._gestor.get_dgt_expediente(expediente_id)
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
        self._gestor.upsert_dgt_expediente(actualizado)

    def listar_expedientes(self) -> list[dict]:
        return self._gestor.listar_dgt_expedientes()

    def get_expediente(self, expediente_id: str) -> dict | None:
        return self._gestor.get_dgt_expediente(expediente_id)

    def get_links(self, expediente: dict) -> dict[str, str]:
        ref = expediente.get("referencia") or expediente.get("id")
        return {
            "vendedor": self._build_url("vendedor", ref),
            "comprador": self._build_url("comprador", ref),
        }

    def regenerar_links(self, expediente_id: str) -> dict[str, str]:
        expediente = self._gestor.get_dgt_expediente(expediente_id)
        if not expediente:
            raise ValueError("Expediente DGT no encontrado.")
        vendedor = self._crear_link("vendedor")
        comprador = self._crear_link("comprador")
        expediente["vendedor_token_hash"] = self._hash_token(vendedor.token)
        expediente["comprador_token_hash"] = self._hash_token(comprador.token)
        expediente["vendedor_token_created_at"] = self._now()
        expediente["comprador_token_created_at"] = self._now()
        self._gestor.upsert_dgt_expediente(expediente)
        ref = expediente.get("referencia") or expediente_id
        return {
            "vendedor": self._build_url("vendedor", ref, vendedor.token),
            "comprador": self._build_url("comprador", ref, comprador.token),
        }

    def verificar_token(self, referencia: str, rol: str, token: str) -> dict:
        rol = self._validar_rol(rol)
        expediente = self._gestor.get_dgt_expediente_por_referencia(referencia)
        if not expediente:
            raise ValueError("Expediente DGT no encontrado.")
        stored_hash = str(expediente.get(f"{rol}_token_hash") or "")
        if not stored_hash or not secrets.compare_digest(stored_hash, self._hash_token(token)):
            raise PermissionError("Enlace DGT no valido o caducado.")
        return expediente

    def completar_desde_link(self, referencia: str, rol: str, token: str, payload: dict) -> None:
        expediente = self.verificar_token(referencia, rol, token)
        self.guardar_datos_parte(expediente["id"], rol, payload)

    def guardar_datos_parte(self, expediente_id: str, rol: str, payload: dict) -> None:
        rol = self._validar_rol(rol)
        expediente = self._gestor.get_dgt_expediente(expediente_id)
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
        self._gestor.upsert_dgt_expediente(expediente)

    def adjuntar_documento(self, expediente_id: str, rol: str, file_path: str, tipo: str = "", descripcion: str = "") -> dict:
        rol = self._validar_rol(rol)
        expediente = self._gestor.get_dgt_expediente(expediente_id)
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
        self._gestor.upsert_dgt_expediente(expediente)
        return item

    def validar_expediente(self, expediente_id: str) -> None:
        expediente = self._gestor.get_dgt_expediente(expediente_id)
        if not expediente:
            raise ValueError("Expediente DGT no encontrado.")
        errors = self.validar_datos(expediente)
        if errors:
            raise ValueError("\n".join(errors))
        user_id = getattr(getattr(self._session, "user", None), "id", 0) or 0
        self._gestor.validar_dgt_expediente(expediente_id, user_id)

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
        expediente = self._gestor.get_dgt_expediente(expediente_id)
        if not expediente:
            raise ValueError("Expediente DGT no encontrado.")
        if expediente.get("estado") != "validado":
            raise ValueError("Valida expresamente el expediente antes de generar documentos.")
        out = []
        for tipo, titulo in DOCUMENTOS_BASE:
            contenido = self._render_documento_texto(expediente, titulo)
            path = self._output_dir(expediente) / f"{tipo}.txt"
            path.write_text(contenido, encoding="utf-8")
            digest = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
            doc_id = self._gestor.insertar_dgt_documento_generado(
                {
                    "expediente_id": expediente_id,
                    "tipo_documento": tipo,
                    "titulo": titulo,
                    "ruta_txt": str(path),
                    "json_datos_generacion": self._document_context(expediente),
                    "hash_contenido": digest,
                }
            )
            out.append({"id": doc_id, "tipo_documento": tipo, "titulo": titulo, "ruta_txt": str(path)})
        return out

    def listar_documentos(self, expediente_id: str) -> list[dict]:
        return self._gestor.listar_dgt_documentos_generados(expediente_id)

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
        rows = self._gestor.listar_dgt_expedientes()
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
