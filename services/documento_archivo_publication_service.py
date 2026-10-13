"""Publicacion trazable del archivo documental en el area del cliente."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from services.backend_client_service import BackendClientService


@dataclass(frozen=True)
class ResultadoPublicacionDocumento:
    documento_id: str
    estado: str
    client_document_id: str = ""
    version: int = 0
    error: str = ""


class DocumentoArchivoPublicationService:
    """Publica una copia del documento conservando el vinculo con el archivo."""

    def __init__(self, gestor, backend: BackendClientService | None = None):
        self._gestor = gestor
        self._backend = backend or BackendClientService()

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def publicar(self, documento_id: str) -> ResultadoPublicacionDocumento:
        documento = self._gestor.get_documento_archivo(str(documento_id))
        if not documento:
            raise ValueError("Documento no encontrado.")
        path = Path(str(documento.get("ruta") or ""))
        if not path.is_file():
            raise FileNotFoundError(f"El archivo no se encuentra en: {path}")

        digest = self._sha256(path)
        archived_hash = str(documento.get("hash_archivo") or "")
        if archived_hash and archived_hash != digest:
            raise ValueError(
                "El archivo ha cambiado desde que se incorporo a Gestion documental."
            )

        queued = self._gestor.encolar_publicacion_documento_archivo(
            str(documento_id), digest,
        )
        if not queued:
            return ResultadoPublicacionDocumento(
                documento_id=str(documento_id),
                estado="publicado",
                client_document_id=str(
                    documento.get("area_cliente_documento_id") or ""
                ),
                version=int(documento.get("area_cliente_version") or 0),
            )

        try:
            if not self._backend.configured:
                raise ValueError(
                    "La plataforma de clientes no esta configurada en este puesto."
                )
            response = self._backend.publish_document(
                source_type=str(documento.get("categoria_id") or "documento"),
                source_system="desktop_archive",
                source_id=str(documento_id),
                source_version=max(
                    1, int(documento.get("area_cliente_version") or 1),
                ),
                display_name=str(
                    documento.get("nombre_original") or path.name
                ),
                file_path=str(path),
                company_code=str(documento.get("codigo_empresa") or "").strip(),
                previous_document_id=str(
                    documento.get("area_cliente_documento_id") or ""
                ),
                fiscal_year=int(documento.get("ejercicio") or 0),
                document_date=str(documento.get("created_at") or ""),
                description=(
                    "Documento compartido por el despacho desde Gestion documental"
                ),
                expected_sha256=digest,
            )
            client_document_id = str(
                response.get("id") or response.get("document_id") or ""
            )
            if not client_document_id:
                raise ValueError(
                    "El backend no devolvio el identificador del documento."
                )
            version = int(response.get("source_version") or 1)
            self._gestor.marcar_publicacion_documento_archivo_exitosa(
                str(documento_id), client_document_id, version,
            )
            return ResultadoPublicacionDocumento(
                documento_id=str(documento_id),
                estado="publicado",
                client_document_id=client_document_id,
                version=version,
            )
        except Exception as exc:
            error = self._error_message(exc)
            self._gestor.marcar_publicacion_documento_archivo_fallida(
                str(documento_id), error,
            )
            return ResultadoPublicacionDocumento(
                documento_id=str(documento_id), estado="error", error=error,
            )

    @staticmethod
    def _error_message(exc: Exception) -> str:
        response = getattr(exc, "response", None)
        if response is not None:
            try:
                detail = response.json().get("detail")
                if detail:
                    return str(detail)
            except Exception:
                pass
        return str(exc) or exc.__class__.__name__
