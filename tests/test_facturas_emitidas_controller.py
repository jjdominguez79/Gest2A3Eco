from controllers.ui_facturas_emitidas_controller import FacturasEmitidasController
from controllers import ui_facturas_emitidas_controller as module
from types import SimpleNamespace


def test_numero_factura_contable_concatena_serie_y_numero():
    controller = FacturasEmitidasController.__new__(FacturasEmitidasController)

    assert controller._numero_factura_contable({"serie": "A", "numero": "123"}) == "A123"


def test_numero_factura_contable_tolera_campos_vacios():
    controller = FacturasEmitidasController.__new__(FacturasEmitidasController)

    assert controller._numero_factura_contable({"serie": "", "numero": "123"}) == "123"
    assert controller._numero_factura_contable({"serie": "A", "numero": ""}) == "A"


def test_observacion_rectificativa_referencia_factura_y_fecha_originales():
    controller = FacturasEmitidasController.__new__(FacturasEmitidasController)

    assert controller._observacion_rectificativa({
        "serie": "A", "numero": "000123", "fecha_expedicion": "2026-05-08",
    }) == "Rectifica la factura A000123 con fecha 08/05/2026."


def test_totales_separan_suplidos_de_base_imponible():
    controller = FacturasEmitidasController.__new__(FacturasEmitidasController)
    factura = {
        "lineas": [
            {"base": 100, "cuota_iva": 21, "cuota_re": 0, "tipo": "honorario"},
            {"base": 55.70, "cuota_iva": 0, "cuota_re": 0, "tipo": "suplido"},
        ],
        "retencion_aplica": False,
    }

    totales = controller._totales_factura(factura)

    assert totales == {
        "base": 100.0,
        "iva": 21.0,
        "re": 0.0,
        "suplidos": 55.7,
        "ret": 0.0,
        "total": 176.7,
    }


def test_resuelve_facturas_y_albaranes_en_subcarpetas_distintas(monkeypatch, tmp_path):
    controller = FacturasEmitidasController.__new__(FacturasEmitidasController)
    monkeypatch.setattr(module, "get_word_templates_subdir", lambda tipo: tmp_path / tipo)

    factura = controller._docx_template_path(default_filename="factura_emitida_template.docx")
    albaran = controller._docx_template_path(default_filename="albaran_template.docx")

    assert factura == str(tmp_path / "facturas" / "factura_emitida_template.docx")
    assert albaran == str(tmp_path / "albaranes" / "albaran_template.docx")


def test_compartir_factura_por_mensajeria_usa_cliente_por_nif(monkeypatch, tmp_path):
    sent = []

    class RemoteStub:
        configured = True

        def __init__(self, **kwargs):
            sent.append(("user", kwargs))

        def sync_staff(self, **kwargs):
            sent.append(("staff", kwargs))

        def sync_organization(self, **kwargs):
            sent.append(("organization", kwargs))

        def company_conversation(self, code, kind):
            sent.append(("conversation", code, kind))
            return {"id": "conv-fiscal", "active_client_count": 1}

        def send_message(self, conversation_id, body, paths):
            sent.append(("message", conversation_id, body, paths))

    monkeypatch.setattr("services.mensajeria_service.MensajeriaRemoteClient", RemoteStub)
    pdf = tmp_path / "factura.pdf"
    pdf.write_bytes(b"%PDF")
    view = SimpleNamespace(
        session=SimpleNamespace(user=SimpleNamespace(id=7, nombre="Administrador")),
        get_selected_ids=lambda: ["fac-1"], ask_share_channel=lambda: "mensajeria",
        ask_yes_no=lambda *_args: False, show_info=lambda *args: sent.append(("info", args)),
        show_warning=lambda *args: sent.append(("warning", args)),
        show_error=lambda *args: sent.append(("error", args)),
    )
    gestor = SimpleNamespace(
        buscar_empresa_por_nif=lambda nif: {
            "codigo": "E00042", "nombre": "Cliente Mensajeria",
        } if nif == "B12345678" else None,
    )
    controller = FacturasEmitidasController.__new__(FacturasEmitidasController)
    controller._view = view
    controller._gestor = gestor
    controller._codigo = "E00001"
    controller._ejercicio = 2026
    controller._get_factura_by_id = lambda _id: {"id": _id, "numero": "F-42"}
    controller._ensure_write = lambda *_args: True
    controller._resolve_app_pdf = lambda _fac: str(pdf)
    controller._albaranes_de_factura = lambda _fac: []
    controller._cliente_factura = lambda _fac: {"nif": "B12345678"}
    controller._is_admin = lambda: True

    controller.compartir_pdf()

    message = next(row for row in sent if row[0] == "message")
    assert message[1] == "conv-fiscal"
    assert message[2] == "Le enviamos la factura F-42."
    assert message[3] == [str(pdf)]


def test_compartir_factura_email_muestra_factura_y_albaran_en_adjuntos(monkeypatch, tmp_path):
    recibidos = {}
    factura_pdf = tmp_path / "factura.pdf"
    albaran_pdf = tmp_path / "albaran.pdf"
    factura_pdf.write_bytes(b"%PDF factura")
    albaran_pdf.write_bytes(b"%PDF albaran")

    def ask_email_compose(*args, **kwargs):
        recibidos.update(kwargs)
        return None

    view = SimpleNamespace(
        get_selected_ids=lambda: ["fac-1"],
        ask_share_channel=lambda: "email",
        ask_yes_no=lambda *_args: True,
        ask_email_compose=ask_email_compose,
        show_info=lambda *_args: None,
        show_warning=lambda *_args: None,
    )
    controller = FacturasEmitidasController.__new__(FacturasEmitidasController)
    controller._view = view
    controller._codigo = "E00701"
    controller._empresa_conf = {}
    controller._get_factura_by_id = lambda _id: {"id": _id, "numero": "000058"}
    controller._ensure_write = lambda *_args: True
    controller._resolve_app_pdf = lambda _fac: str(factura_pdf)
    controller._albaranes_de_factura = lambda _fac: [{"id": "alb-1"}]
    controller._resolve_albaran_pdf = lambda _alb: str(albaran_pdf)
    controller._cliente_factura = lambda _fac: {}
    controller._totales_factura = lambda _fac: {}

    monkeypatch.setattr("services.email_service.build_invoice_email_text", lambda *_args: "Texto")
    controller.compartir_pdf()

    assert recibidos["attachment_paths"] == [str(factura_pdf), str(albaran_pdf)]


def test_eliminar_factura_refresca_albaranes_para_que_queden_editables():
    llamadas = []
    view = SimpleNamespace(
        get_selected_ids=lambda: ["fac-58"],
        ask_yes_no=lambda *_args: True,
    )
    gestor = SimpleNamespace(
        eliminar_factura_emitida=lambda *args: llamadas.append(("eliminar", args)),
    )
    controller = FacturasEmitidasController.__new__(FacturasEmitidasController)
    controller._view = view
    controller._gestor = gestor
    controller._codigo = "E00701"
    controller._ejercicio = 2026
    controller._ensure_write = lambda *_args: True
    controller._get_factura_by_id = lambda _id: {
        "id": "fac-58", "ejercicio": 2026, "generada": False,
    }
    controller.refresh_facturas = lambda: llamadas.append(("refresh_facturas",))
    controller.refresh_albaranes = lambda: llamadas.append(("refresh_albaranes",))

    controller.eliminar()

    assert llamadas == [
        ("eliminar", ("E00701", "fac-58", 2026)),
        ("refresh_facturas",),
        ("refresh_albaranes",),
    ]


def test_resolver_pdf_albaran_regenera_si_fue_modificado(tmp_path):
    pdf = tmp_path / "albaran.pdf"
    pdf.write_bytes(b"PDF antiguo")
    controller = FacturasEmitidasController.__new__(FacturasEmitidasController)
    controller._albaran_app_pdf_path = lambda _alb: str(pdf)
    controller._can_write = lambda: False
    controller._log_pdf_error = lambda *args: None
    controller._generar_pdf_word = lambda _doc, _path, **_kwargs: pdf.write_bytes(b"PDF nuevo")
    albaran = {
        "updated_at": "2026-08-10T13:30:00",
        "pdf_generated_at": "2026-08-10T13:20:00",
    }

    result = controller._resolve_albaran_pdf(albaran)

    assert result == str(pdf)
    assert pdf.read_bytes() == b"PDF nuevo"
