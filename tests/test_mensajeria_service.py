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


def test_edita_y_consulta_versiones_con_autenticacion_de_puesto(monkeypatch):
    monkeypatch.setattr("utils.credential_store.get_workstation_token", lambda: "g2a3_wks_test")
    monkeypatch.setattr("utils.credential_store.get_messaging_device_token", lambda: None)
    peticiones = []

    class Sesion:
        def patch(self, url, **kwargs):
            peticiones.append((url, kwargs))
            return ResponseStub({"id": "m1", "body": "Actual"})

        def get(self, url, **kwargs):
            peticiones.append((url, kwargs))
            return ResponseStub([{"body": "Original"}])

    cliente = MensajeriaRemoteClient(user_id=1, user_name="Admin",
        config={"messaging_api_url": "https://example.test"}, session=Sesion())
    assert cliente.editar_mensaje("m1", "Actual", "Original")["body"] == "Actual"
    assert cliente.versiones_mensaje("m1") == [{"body": "Original"}]
    assert peticiones[0][0].endswith("/staff/messages/m1")
    assert peticiones[0][1]["json"] == {"body": "Actual", "original_body": "Original"}
    assert peticiones[1][0].endswith("/staff/messages/m1/history")
    for _, parametros in peticiones:
        assert parametros["headers"]["X-API-Key"] == "g2a3_wks_test"
        assert parametros["headers"]["X-Staff-Id"] == "1"


def test_busca_conversacion_por_empresa_y_canal_sin_confundir_clientes(monkeypatch):
    monkeypatch.setattr("utils.credential_store.get_workstation_token", lambda: "g2a3_wks_test")
    monkeypatch.setattr("utils.credential_store.get_messaging_device_token", lambda: None)

    conversations = [
        {"id": "a", "company_code": "E00041", "kind": "general"},
        {"id": "b", "company_code": "E00042", "kind": "private"},
        {"id": "c", "company_code": "E00042", "kind": "general"},
    ]
    client = MensajeriaRemoteClient(
        user_id=1, user_name="Admin",
        config={"messaging_api_url": "https://example.test"},
        session=SessionStub(conversations),
    )

    assert client.company_conversation("e00042", "GENERAL")["id"] == "c"
    assert client.company_conversation("E99999", "general") is None


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
