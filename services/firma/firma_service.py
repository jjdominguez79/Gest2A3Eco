from __future__ import annotations

import hashlib
import json
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from .firma_repository import FirmaRepository
from .zonas import preparar_pdf_con_zonas

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class FirmaService:
    def __init__(self, gestor, provider=None, max_mb: int = 15, repository=None):
        self.gestor = gestor
        self.provider = provider
        self.max_mb = max(1, int(max_mb or 15))
        self.repository = repository or FirmaRepository(gestor)

    def crear_solicitud(self, codigo_empresa: str, ejercicio: int, ruta: str,
                        firmantes: list[dict], *, origen: str = "archivo",
                        documento_archivo_id: str = "", asunto: str = "",
                        mensaje: str = "", usar_sms: bool = False,
                        zonas: list[dict] | None = None, creado_por: str = "") -> str:
        path = Path(ruta)
        self._validar_pdf(path)
        self._validar_firmantes(firmantes, usar_sms)
        zonas = list(zonas or [])
        remitente = bool(firmantes and firmantes[0].get("es_remitente"))
        self._validar_zonas(zonas, len(firmantes), remitente)
        solicitud_id = str(uuid.uuid4())
        envio = str(path)
        if zonas:
            zonas_envio = [
                {**zona, "firmante": int(zona["firmante"]) + (0 if remitente else 1)}
                for zona in zonas
            ]
            envio = preparar_pdf_con_zonas(str(path), zonas_envio)
        datos = {
            "id": solicitud_id,
            "codigo_empresa": codigo_empresa,
            "ejercicio": int(ejercicio),
            "origen": origen,
            "documento_archivo_id": documento_archivo_id or None,
            "nombre_documento": path.name,
            "ruta_origen": str(path),
            "ruta_envio": envio,
            "hash_origen": self._sha256(path),
            "external_id": f"gd:{solicitud_id}",
            "asunto": asunto.strip(),
            "mensaje": mensaje.strip(),
            "usar_sms": usar_sms,
            "creado_por": creado_por,
        }
        self.repository.crear(datos, firmantes, zonas)
        self.repository.evento(solicitud_id, "creada", json.dumps({"zonas": len(zonas)}), creado_por)
        return solicitud_id

    def enviar(self, solicitud_id: str) -> dict:
        if self.provider is None:
            raise RuntimeError("Firma electronica no disponible: configure el backend.")
        solicitud = self._require(solicitud_id)
        if solicitud.get("estado") not in {"borrador", "incidencia"}:
            raise ValueError("La solicitud ya ha sido enviada o cerrada.")
        result = self.provider.enviar_documento(
            solicitud["ruta_envio"] or solicitud["ruta_origen"],
            solicitud["firmantes"], solicitud.get("asunto") or solicitud["nombre_documento"],
            solicitud.get("mensaje") or "", solicitud["external_id"],
            usar_sms=bool(solicitud.get("usar_sms")),
        )
        request_id = result.get("uuid") or result.get("request_id") or ""
        if not request_id:
            raise RuntimeError("El proveedor no devolvio el identificador de firma.")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        self.repository.actualizar(solicitud_id, {
            "request_id": request_id, "estado": "enviado", "enviado_at": now,
        })
        self.repository.evento(solicitud_id, "enviada", json.dumps({"request_id": request_id}), "")
        return {**solicitud, "request_id": request_id, "estado": "enviado"}

    def actualizar_estado(self, solicitud_id: str, destino_evidencias: str = "") -> dict:
        if self.provider is None:
            raise RuntimeError("Firma electronica no disponible: configure el backend.")
        solicitud = self._require(solicitud_id)
        if not solicitud.get("request_id"):
            raise ValueError("La solicitud aun no se ha enviado.")
        estado_raw = self.provider.consultar(solicitud["request_id"])
        estado = self._normalizar_estado(estado_raw)
        cambios = {"estado": estado}
        if estado == "firmado" and destino_evidencias:
            evidencia = self.provider.descargar_evidencias(
                solicitud["request_id"], destino_evidencias,
                Path(solicitud["nombre_documento"]).stem,
            )
            cambios.update({
                "ruta_firmado": evidencia.get("ruta_firmado"),
                "ruta_registro_firma": evidencia.get("ruta_registro_firma"),
                "sha256_firmado": evidencia.get("sha256_firmado"),
                "sha256_registro_firma": evidencia.get("sha256_registro_firma"),
                "security_hash": evidencia.get("security_hash"),
                "signing_log_security_hash": evidencia.get("signing_log_security_hash"),
                "firmado_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            })
        self.repository.actualizar(solicitud_id, cambios)
        self.repository.evento(solicitud_id, "consultada", json.dumps({"estado": estado}), "")
        return {**solicitud, **cambios, "proveedor": estado_raw}

    def cancelar(self, solicitud_id: str) -> dict:
        if self.provider is None:
            raise RuntimeError("Firma electronica no disponible: configure el backend.")
        solicitud = self._require(solicitud_id)
        if solicitud.get("estado") == "firmado":
            raise ValueError("No se puede cancelar una solicitud ya firmada.")
        result = self.provider.cancelar(solicitud["request_id"])
        self.repository.actualizar(solicitud_id, {"estado": "cancelado"})
        self.repository.evento(solicitud_id, "cancelada", json.dumps(result), "")
        return result

    def reenviar(self, solicitud_id: str) -> dict:
        if self.provider is None:
            raise RuntimeError("Firma electronica no disponible: configure el backend.")
        solicitud = self._require(solicitud_id)
        if solicitud.get("estado") not in {"enviado", "parcialmente_firmado"}:
            raise ValueError("Solo se puede reenviar una solicitud activa.")
        return self.provider.reenviar(solicitud["request_id"])

    def listar(self, codigo_empresa, ejercicio, estado="", texto=""):
        return self.repository.listar(codigo_empresa, ejercicio, estado, texto)

    def _require(self, solicitud_id):
        solicitud = self.repository.get(solicitud_id)
        if not solicitud:
            raise ValueError("No existe la solicitud de firma.")
        return solicitud

    def _validar_pdf(self, path: Path):
        if not path.is_file() or path.suffix.lower() != ".pdf":
            raise ValueError("Solo se pueden enviar documentos PDF a firma.")
        if path.stat().st_size > self.max_mb * 1024 * 1024:
            raise ValueError(f"El PDF supera el limite de {self.max_mb} MB.")

    @staticmethod
    def _validar_firmantes(firmantes, usar_sms):
        if not firmantes:
            raise ValueError("Debes indicar al menos un firmante.")
        emails = []
        for indice, firmante in enumerate(firmantes):
            email = str(firmante.get("email") or "").strip().lower()
            if not _EMAIL.match(email):
                raise ValueError(f"El email del firmante {indice + 1} no es valido.")
            if email in emails:
                raise ValueError("No puede haber emails de firmantes duplicados.")
            emails.append(email)
            if int(firmante.get("orden") or 0) != indice + 1:
                raise ValueError("El orden de firma debe ser correlativo desde 1.")
            if usar_sms and firmante.get("telefono") and not str(firmante["telefono"]).strip().startswith("+"):
                raise ValueError("Los telefonos SMS deben estar en formato internacional (+...).")

    @staticmethod
    def _validar_zonas(zonas, num_firmantes, remitente):
        for zona in zonas:
            firmante = int(zona.get("firmante", -1))
            if firmante < 0 or firmante >= num_firmantes:
                raise ValueError("Una zona apunta a un firmante inexistente.")
            for key in ("x", "y", "ancho", "alto"):
                value = float(zona.get(key, 0))
                if key in {"x", "y"} and not 0 <= value < 1:
                    raise ValueError("Las coordenadas de firma deben estar entre 0 y 1.")
                if key in {"ancho", "alto"} and not 0 < value <= 1:
                    raise ValueError("El tamano de una zona de firma no es valido.")

    @staticmethod
    def _sha256(path: Path):
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _normalizar_estado(raw):
        status = str(raw.get("status") or raw.get("estado") or "").lower()
        if status in {"signed", "completed", "firmado"}:
            return "firmado"
        if status in {"declined", "rejected", "rechazado"}:
            return "rechazado"
        if status in {"cancelled", "canceled", "cancelado"}:
            return "cancelado"
        if status in {"expired", "incidence", "incidencia"}:
            return "incidencia"
        return "enviado"
