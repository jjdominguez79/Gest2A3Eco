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


def test_busca_conversacion_por_empresa_y_canal_sin_confundir_clientes(monkeypatch):
    monkeypatch.setattr("utils.credential_store.get_workstation_token", lambda: "g2a3_wks_test")
    monkeypatch.setattr("utils.credential_store.get_messaging_device_token", lambda: None)

    conversations = [
        {"id": "a", "company_code": "E00041", "kind": "fiscal"},
        {"id": "b", "company_code": "E00042", "kind": "laboral"},
        {"id": "c", "company_code": "E00042", "kind": "fiscal"},
    ]
    client = MensajeriaRemoteClient(
        user_id=1, user_name="Admin",
        config={"messaging_api_url": "https://example.test"},
        session=SessionStub(conversations),
    )

    assert client.company_conversation("e00042", "FISCAL")["id"] == "c"
    assert client.company_conversation("E99999", "fiscal") is None


def test_privacidad_lecturas_envia_preferencias_independientes(monkeypatch):
    monkeypatch.setattr("utils.credential_store.get_workstation_token", lambda: "g2a3_wks_test")
    monkeypatch.setattr("utils.credential_store.get_messaging_device_token", lambda: None)
    peticiones = []
    class Sesion:
        def patch(self, url, **kwargs):
            peticiones.append((url, kwargs))
            return ResponseStub({"ok": True})
    cliente = MensajeriaRemoteClient(user_id=1, user_name="Admin",
        config={"messaging_api_url": "https://example.test"}, session=Sesion())
    cliente.configurar_privacidad_lecturas(False, True)
    assert peticiones[0][0].endswith("/staff/me")
    assert peticiones[0][1]["json"] == {"mostrar_lecturas_clientes": False,
                                      "mostrar_lecturas_empleados": True}
