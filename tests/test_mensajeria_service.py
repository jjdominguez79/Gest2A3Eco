from services.mensajeria_service import MensajeriaRemoteClient


class ResponseStub:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class SessionStub:
    def __init__(self, conversations):
        self.conversations = conversations

    def get(self, _url, **_kwargs):
        return ResponseStub(self.conversations)


def test_busca_conversacion_por_empresa_y_canal_sin_confundir_clientes():
    conversations = [
        {"id": "a", "company_code": "E00041", "kind": "fiscal"},
        {"id": "b", "company_code": "E00042", "kind": "laboral"},
        {"id": "c", "company_code": "E00042", "kind": "fiscal"},
    ]
    client = MensajeriaRemoteClient(
        user_id=1, user_name="Admin",
        config={"messaging_api_url": "https://example.test", "messaging_api_key": "secret"},
        session=SessionStub(conversations),
    )

    assert client.company_conversation("e00042", "FISCAL")["id"] == "c"
    assert client.company_conversation("E99999", "fiscal") is None
