from pathlib import Path

from services.signrequest_service import SignRequestClient


class _Response:
    status_code = 201
    content = b""

    def json(self):
        return {"uuid": "firma-123", "status": "sent", "document": "doc-url"}


class _Session:
    def __init__(self):
        self.call = None

    def request(self, method, url, **kwargs):
        self.call = (method, url, kwargs)
        return _Response()


def test_envia_documento_con_token_y_contenido_base64(tmp_path: Path):
    pdf = tmp_path / "contrato.pdf"
    pdf.write_bytes(b"%PDF-1.4 prueba")
    session = _Session()
    client = SignRequestClient("token-secreto", "gestoria@example.com", session=session)

    result = client.enviar_documento(
        str(pdf),
        [{"email": "cliente@example.com", "telefono": "+34600000000", "order": 1}],
        "Contrato",
        "Firma el contrato",
        "DGT-1:doc-1",
        usar_sms=True,
    )

    assert result["uuid"] == "firma-123"
    method, url, kwargs = session.call
    assert method == "POST"
    assert url.endswith("/signrequest-quick-create/")
    assert kwargs["headers"]["Authorization"] == "Token token-secreto"
    assert kwargs["json"]["signers"][0]["verify_phone_number"] == "+34600000000"
    assert kwargs["json"]["file_from_content"]
    assert "events_callback_url" not in kwargs["json"]


class _RouteResponse:
    def __init__(self, data=None, content=b"", status=200):
        self._data = data or {}
        self.content = content
        self.status_code = status

    def json(self):
        return self._data


class _RouteSession:
    def request(self, method, url, **kwargs):
        if "/signrequests/" in url:
            return _RouteResponse({"document": "https://signrequest.com/api/v1/documents/doc-1/"})
        if "/documents/doc-1/" in url:
            return _RouteResponse(
                {
                    "uuid": "doc-1",
                    "pdf": "https://files.example/firmado.pdf",
                    "security_hash": "seguridad",
                    "signing_log": {
                        "pdf": "https://files.example/log.pdf",
                        "security_hash": "registro",
                    },
                }
            )
        return _RouteResponse(content=b"%PDF evidencia")


def test_descarga_documento_firmado_y_registro(tmp_path: Path):
    client = SignRequestClient(
        "token-secreto", "gestoria@example.com", session=_RouteSession()
    )

    result = client.descargar_evidencias("firma-1", str(tmp_path), "contrato")

    assert Path(result["ruta_firmado"]).read_bytes() == b"%PDF evidencia"
    assert Path(result["ruta_registro_firma"]).read_bytes() == b"%PDF evidencia"
    assert len(result["sha256_firmado"]) == 64
