from io import BytesIO
from pathlib import Path

from PIL import Image

from services.profile_change_request_service import ProfileChangeRequestService


class _Backend:
    def __init__(self, image_bytes):
        self.image_bytes = image_bytes
        self.reviews = []

    def download_profile_change_logo(self, request_id):
        assert request_id == "request-1"
        return self.image_bytes, "marca.png", "image/png"

    def review_profile_change_request(self, request_id, *, status, note):
        self.reviews.append((request_id, status, note))
        return {"id": request_id, "status": status}


class _BackendConBlobPerdido(_Backend):
    def download_profile_change_logo(self, request_id):
        raise RuntimeError("BlobNotFound")


class _GestorCambios:
    def __init__(self, local_logo=None):
        self.calls = []
        self.local_logo = local_logo
        self.discarded = []

    def aplicar_cambios_empresa_solicitados(self, codigo, cambios, logo_path):
        self.calls.append((codigo, cambios, logo_path))
        return 1

    def get_adjunto_mensajeria_por_mensaje(self, message_id):
        assert message_id == "message-1"
        return self.local_logo

    def no_guardar_adjunto_mensajeria(self, attachment_id, revisado_por):
        self.discarded.append((attachment_id, revisado_por))


def _png_bytes():
    stream = BytesIO()
    Image.new("RGB", (12, 8), "navy").save(stream, format="PNG")
    return stream.getvalue()


def test_aprobar_solicitud_guarda_logo_antes_de_confirmar_backend(
    monkeypatch, tmp_path,
):
    backend = _Backend(_png_bytes())
    gestor = _GestorCambios()
    monkeypatch.setattr(
        "services.company_logo_service.get_document_repository_dir",
        lambda: tmp_path,
    )
    service = ProfileChangeRequestService(gestor, backend=backend)

    result = service.apply({
        "id": "request-1",
        "company_code": "e00006",
        "changes": {"legal_name": "Empresa Demo SL"},
        "has_logo": True,
    })

    expected = (
        tmp_path / "assets" / "logos" / "E00006.png"
    )
    assert expected.read_bytes() == backend.image_bytes
    assert gestor.calls == [(
        "E00006", {"legal_name": "Empresa Demo SL"}, str(expected),
    )]
    assert backend.reviews == [(
        "request-1", "applied",
        "Actualizado manualmente en A3 y aplicado desde Gest2A3Eco.",
    )]
    assert result["status"] == "applied"


def test_aprobar_usa_copia_del_nas_si_el_blob_ya_no_existe(
    monkeypatch, tmp_path,
):
    content = _png_bytes()
    source = tmp_path / "entrada" / "logo.png"
    source.parent.mkdir()
    source.write_bytes(content)
    backend = _BackendConBlobPerdido(content)
    gestor = _GestorCambios({
        "id": "attachment-1",
        "ruta_entrada": str(source),
        "nombre_original": "marca.png",
        "mime_type": "image/png",
    })
    monkeypatch.setattr(
        "services.company_logo_service.get_document_repository_dir",
        lambda: tmp_path / "repositorio",
    )

    result = ProfileChangeRequestService(gestor, backend=backend).apply({
        "id": "request-1",
        "message_id": "message-1",
        "company_code": "E00006",
        "changes": {},
        "has_logo": True,
    })

    assert result["status"] == "applied"
    saved_path = Path(gestor.calls[0][2])
    assert saved_path.read_bytes() == content
    assert gestor.discarded == [("attachment-1", "sistema")]
    assert not source.exists()
