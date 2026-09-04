from io import BytesIO

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


class _GestorCambios:
    def __init__(self):
        self.calls = []

    def aplicar_cambios_empresa_solicitados(self, codigo, cambios, logo_path):
        self.calls.append((codigo, cambios, logo_path))
        return 1


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
        "services.profile_change_request_service.get_document_repository_dir",
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
        tmp_path / "Empresas" / "E00006" / "Configuracion"
        / "logotipo_empresa.png"
    )
    assert expected.read_bytes() == backend.image_bytes
    assert gestor.calls == [(
        "E00006", {"legal_name": "Empresa Demo SL"}, str(expected),
    )]
    assert backend.reviews == [(
        "request-1", "applied", "Aplicado y confirmado desde Gest2A3Eco.",
    )]
    assert result["status"] == "applied"
