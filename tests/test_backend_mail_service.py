import json

from services.backend_mail_service import BackendMailService


class Response:
    status_code = 200

    @staticmethod
    def json():
        return {"sent": True, "sender": "oficina@gestinem.es"}


class Session:
    def __init__(self):
        self.call = None

    def post(self, url, **kwargs):
        self.call = (url, kwargs)
        assert kwargs["files"][0][1][1].read() == b"%PDF"
        kwargs["files"][0][1][1].seek(0)
        return Response()


def test_envia_factura_al_backend_con_token_de_puesto(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "utils.credential_store.get_workstation_token", lambda: "g2a3_wks_test",
    )
    pdf = tmp_path / "factura.pdf"
    pdf.write_bytes(b"%PDF")
    session = Session()
    service = BackendMailService(
        {"integrations_api_url": "https://backend.example.test"}, session=session,
    )

    result = service.send(
        to=["cliente@example.test"], cc=["copia@example.test"],
        subject="Factura", body="<p>Adjunta</p>", attachments=[str(pdf)],
    )

    url, request = session.call
    assert url == "https://backend.example.test/api/v1/mail/send"
    assert request["headers"] == {"X-API-Key": "g2a3_wks_test"}
    assert json.loads(request["data"]["to"]) == ["cliente@example.test"]
    assert request["files"][0][0] == "files"
    assert result.sender == "oficina@gestinem.es"
