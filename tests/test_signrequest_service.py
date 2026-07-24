from pathlib import Path

from services.signrequest_service import SignRequestClient


class _Response:
    status_code = 201

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
