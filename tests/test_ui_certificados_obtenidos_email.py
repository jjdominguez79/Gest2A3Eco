from types import SimpleNamespace

from views.ui_certificados_obtenidos import UICertificadosObtenidos


class _Gestor:
    def __init__(self):
        self.registros = []

    def get_empresa(self, codigo):
        assert codigo == "E00001"
        return {"email": "cliente@ejemplo.es"}

    def registrar_envio_comunicacion(self, datos):
        self.registros.append(datos)


def _vista(tmp_path, *, admin, sender_mode):
    pdf = tmp_path / "certificado.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    gestor = _Gestor()
    vista = UICertificadosObtenidos.__new__(UICertificadosObtenidos)
    vista._gestor = gestor
    vista._session = SimpleNamespace(
        is_admin=lambda: admin,
        user=SimpleNamespace(
            id="u1", nombre="Usuario Prueba",
            email_corporativo="jjdominguez@gestinem.es",
        ),
    )
    solicitud = {
        "id": "sol-1",
        "document_id": "doc-1",
        "company_code": "E00001",
        "company_name": "Cliente Uno",
        "certificate_type": "AEAT_CORRIENTE",
        "completed_at": "2026-09-24",
    }
    vista._fila = lambda: solicitud
    vista._descargar_pdf = lambda _solicitud: str(pdf)
    vista._ask_email_compose = lambda *_args: {
        "emails": ["cliente@ejemplo.es", "otro@ejemplo.es"],
        "cc": "copia@ejemplo.es",
        "bcc": "oculta@ejemplo.es",
        "asunto": "Certificado solicitado",
        "cuerpo": "Adjunto el certificado.",
        "sender_mode": sender_mode,
    }
    vista.winfo_toplevel = lambda: None
    return vista, gestor


def test_certificado_se_envia_por_backend_desde_oficina_y_se_registra(
    tmp_path, monkeypatch,
):
    vista, gestor = _vista(tmp_path, admin=False, sender_mode="personal")
    enviados = []

    class _Backend:
        def send(self, **kwargs):
            enviados.append(kwargs)
            return SimpleNamespace(
                sender="oficina@gestinem.es", message_id="msg-1",
                internet_message_id="internet-1",
            )

    monkeypatch.setattr("services.backend_mail_service.BackendMailService", _Backend)
    monkeypatch.setattr("views.ui_certificados_obtenidos.messagebox.showinfo", lambda *_a, **_k: None)

    vista._on_email()

    assert enviados[0]["to"] == ["cliente@ejemplo.es", "otro@ejemplo.es"]
    assert enviados[0]["cc"] == ["copia@ejemplo.es"]
    assert enviados[0]["bcc"] == ["oculta@ejemplo.es"]
    assert enviados[0]["sender_mode"] == "office"
    assert "Asesoria Gestinem SL" in enviados[0]["body"]
    assert gestor.registros[0]["remitente"] == "oficina@gestinem.es"
    assert gestor.registros[0]["estado_envio"] == "aceptado_backend"


def test_administrador_puede_elegir_su_cuenta_para_enviar_certificado(
    tmp_path, monkeypatch,
):
    vista, gestor = _vista(tmp_path, admin=True, sender_mode="personal")
    enviados = []

    class _Backend:
        def send(self, **kwargs):
            enviados.append(kwargs)
            return SimpleNamespace(
                sender="jjdominguez@gestinem.es", message_id="msg-2",
                internet_message_id="internet-2",
            )

    monkeypatch.setattr("services.backend_mail_service.BackendMailService", _Backend)
    monkeypatch.setattr("views.ui_certificados_obtenidos.messagebox.showinfo", lambda *_a, **_k: None)

    vista._on_email()

    assert enviados[0]["sender_mode"] == "personal"
    assert "Asesoria Gestinem SL" in enviados[0]["body"]
    assert gestor.registros[0]["remitente"] == "jjdominguez@gestinem.es"
    assert gestor.registros[0]["estado_envio"] == "aceptado_backend"
