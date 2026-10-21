from __future__ import annotations

import hashlib

from services.documento_archivo_publication_service import (
    DocumentoArchivoPublicationService,
)


class _Gestor:
    def __init__(self, documento):
        self.documento = documento
        self.encolado = None
        self.exito = None
        self.error = None

    def get_documento_archivo(self, _documento_id):
        return dict(self.documento)

    def encolar_publicacion_documento_archivo(
        self, documento_id, sha256, categoria_area_cliente="",
    ):
        self.encolado = (documento_id, sha256, categoria_area_cliente)
        return True

    def marcar_publicacion_documento_archivo_exitosa(self, *args):
        self.exito = args

    def marcar_publicacion_documento_archivo_fallida(self, *args):
        self.error = args


class _Backend:
    configured = True

    def __init__(self):
        self.kwargs = None

    def publish_document(self, **kwargs):
        self.kwargs = kwargs
        return {"id": "client-doc-1", "source_version": 2}


def test_publica_documento_archivado_con_identidad_estable(tmp_path):
    path = tmp_path / "informe.docx"
    path.write_bytes(b"PK\x03\x04contenido")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    gestor = _Gestor({
        "id": "archivo-1",
        "codigo_empresa": "E00006",
        "ejercicio": 2026,
        "categoria_id": "laboral",
        "categoria_nombre": "Laboral",
        "nombre_original": "Informe laboral.docx",
        "ruta": str(path),
        "hash_archivo": digest,
        "created_at": "2026-10-13T09:00:00+02:00",
        "area_cliente_version": 1,
    })
    backend = _Backend()

    result = DocumentoArchivoPublicationService(gestor, backend).publicar("archivo-1")

    assert result.estado == "publicado"
    assert result.client_document_id == "client-doc-1"
    assert gestor.encolado == ("archivo-1", digest, "otros")
    assert gestor.exito == ("archivo-1", "client-doc-1", 2)
    assert backend.kwargs["source_system"] == "desktop_archive"
    assert backend.kwargs["source_id"] == "archivo-1"
    assert backend.kwargs["file_path"] == str(path)
    assert backend.kwargs["company_code"] == "E00006"
    assert backend.kwargs["client_folder"] == "otros"


def test_publica_en_la_categoria_flutter_elegida(tmp_path):
    path = tmp_path / "informe.pdf"
    path.write_bytes(b"%PDF-1.4 contenido")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    gestor = _Gestor({
        "id": "archivo-2",
        "codigo_empresa": "E00006",
        "ejercicio": 2026,
        "categoria_id": "laboral",
        "nombre_original": "Nomina.pdf",
        "ruta": str(path),
        "hash_archivo": digest,
    })
    backend = _Backend()

    DocumentoArchivoPublicationService(gestor, backend).publicar(
        "archivo-2", categoria_area_cliente="nominas",
    )

    assert gestor.encolado == ("archivo-2", digest, "nominas")
    assert backend.kwargs["source_type"] == "laboral"
    assert backend.kwargs["client_folder"] == "nominas"


def test_no_publica_si_el_archivo_ya_no_coincide_con_el_archivado(tmp_path):
    path = tmp_path / "informe.pdf"
    path.write_bytes(b"%PDF-1.4 cambiado")
    gestor = _Gestor({
        "id": "archivo-1", "ruta": str(path),
        "hash_archivo": "0" * 64,
    })

    try:
        DocumentoArchivoPublicationService(gestor, _Backend()).publicar("archivo-1")
    except ValueError as exc:
        assert "ha cambiado" in str(exc)
    else:
        raise AssertionError("Se esperaba rechazo por integridad")

    assert gestor.encolado is None
