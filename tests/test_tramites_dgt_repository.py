from pathlib import Path

import pytest

from services.tramites_dgt_repository import ApiDgtRepository
from services.tramites_dgt_service import TramitesDgtService


@pytest.mark.parametrize(
    ("filename", "mime_type"),
    (
        ("archivo.pdf", "application/pdf"),
        ("MODELO620.PDF", "application/pdf"),
        ("archivo.jpg", "image/jpeg"),
        ("archivo.jpeg", "image/jpeg"),
        ("archivo.png", "image/png"),
    ),
)
def test_upload_documento_incluye_mime_en_multipart(tmp_path: Path, monkeypatch, filename, mime_type):
    path = tmp_path / filename
    path.write_bytes(b"contenido")
    repository = ApiDgtRepository("https://dgt.example.test", "token")
    llamada = {}

    def request(method, endpoint, **kwargs):
        llamada.update(method=method, endpoint=endpoint, **kwargs)
        multipart = kwargs["files"]["file"]
        assert multipart[0] == filename
        assert multipart[1].read() == b"contenido"
        assert multipart[2] == mime_type
        return {"id": "doc-1"}

    monkeypatch.setattr(repository, "_request", request)

    assert repository.upload_documento("exp-1", "gestor", "documentacion", str(path))["id"] == "doc-1"
    assert llamada["method"] == "POST"


def test_upload_documento_rechaza_extension_antes_de_peticion_http(tmp_path: Path, monkeypatch):
    path = tmp_path / "documento.docx"
    path.write_bytes(b"contenido")
    repository = ApiDgtRepository("https://dgt.example.test", "token")
    monkeypatch.setattr(
        repository,
        "_request",
        lambda *args, **kwargs: pytest.fail("No debe realizar la peticion HTTP"),
    )

    with pytest.raises(ValueError, match="PDF, JPG, JPEG y PNG"):
        repository.upload_documento("exp-1", "gestor", "documentacion", str(path))


class _RepositorioLocal:
    def __init__(self):
        self.expediente = {"id": "exp-1", "estado": "borrador", "documentos": []}

    def get_expediente(self, expediente_id):
        return self.expediente if expediente_id == "exp-1" else None

    def upsert_expediente(self, expediente):
        self.expediente = expediente
        return expediente["id"]


@pytest.mark.parametrize("rol", ("gestor", "comprador", "vendedor"))
def test_servicio_admite_roles_documentales(rol, tmp_path: Path):
    path = tmp_path / f"{rol}.PDF"
    path.write_bytes(b"%PDF-1.4")
    repository = _RepositorioLocal()
    service = TramitesDgtService(repository=repository)

    item = service.adjuntar_documento("exp-1", rol, str(path), tipo="documentacion")

    assert item["rol"] == rol


def test_servicio_rechaza_rol_arbitrario(tmp_path: Path):
    path = tmp_path / "documento.pdf"
    path.write_bytes(b"%PDF-1.4")
    service = TramitesDgtService(repository=_RepositorioLocal())

    with pytest.raises(ValueError, match="Rol DGT no valido"):
        service.adjuntar_documento("exp-1", "tercero", str(path))


def test_servicio_marca_modelo_620_en_repositorio_local(tmp_path: Path):
    path = tmp_path / "modelo.pdf"
    path.write_bytes(b"%PDF-1.4")
    repository = _RepositorioLocal()
    service = TramitesDgtService(repository=repository)

    service.adjuntar_documento("exp-1", "gestor", str(path), tipo="modelo_620")

    assert repository.expediente["modelo_620_presentado"] is True
