from unittest.mock import Mock

import views.ui_certificados_obtenidos as modulo
from views.ui_certificados_obtenidos import (
    UICertificadosObtenidos,
    _combinar_solicitudes,
    _label_area_cliente,
    _label_cliente,
    _normalizar_busqueda,
)


def test_label_cliente_prioriza_nombre_y_permite_identificarlo():
    empresa = {"codigo": "E00006", "nombre": "Dominguez Barrero", "cif": "72044071K"}

    assert _label_cliente(empresa) == "Dominguez Barrero - 72044071K - E00006"


def test_busqueda_ignora_mayusculas_y_acentos():
    label = "Álvarez Gestión - B12345678 - E00001"

    assert "alvarez" in _normalizar_busqueda(label)
    assert "b12345678" in _normalizar_busqueda(label)


def test_label_area_cliente_distingue_activa_inactiva_y_backend_antiguo():
    assert _label_area_cliente({"client_documents_enabled": True}) == "Activa"
    assert _label_area_cliente({"client_documents_enabled": False}) == "No activa"
    assert _label_area_cliente({}) == "Sin datos"


def test_combina_listado_general_con_solicitudes_del_cliente_sin_duplicar():
    general = [{"id": "reciente"}, {"id": "compartida"}]
    cliente = [{"id": "compartida"}, {"id": "antigua-oculta"}]

    assert _combinar_solicitudes(general, cliente) == [
        {"id": "reciente"},
        {"id": "compartida"},
        {"id": "antigua-oculta"},
    ]


def test_preparacion_recupera_solicitud_antigua_que_requiere_revision(monkeypatch):
    vista = object.__new__(UICertificadosObtenidos)
    vista._btn_solicitar = Mock()
    vista.winfo_toplevel = Mock(return_value=None)
    vista.refresh = Mock()
    dialogo = {}

    def _cancelar(titulo, mensaje, **_kwargs):
        dialogo.update(titulo=titulo, mensaje=mensaje)
        return False

    monkeypatch.setattr(modulo.messagebox, "askyesno", _cancelar)

    vista._preparar_solicitud_fin(
        "E00686",
        "AEAT_CONTRATISTAS",
        {"configured": True, "status": "valid"},
        [{
            "id": "sol-anterior",
            "company_code": "E00686",
            "certificate_type": "AEAT_CONTRATISTAS",
            "status": "needs_action",
            "submitted_at": None,
        }],
    )

    assert dialogo["titulo"] == "Reintentar certificado"
    assert "mismo registro" in dialogo["mensaje"]
    vista._btn_solicitar.configure.assert_called_with(state="normal")


def test_preparacion_no_duplica_una_solicitud_en_curso(monkeypatch):
    vista = object.__new__(UICertificadosObtenidos)
    vista._btn_solicitar = Mock()
    vista.winfo_toplevel = Mock(return_value=None)
    vista.refresh = Mock()
    aviso = Mock()
    monkeypatch.setattr(modulo.messagebox, "showinfo", aviso)

    vista._preparar_solicitud_fin(
        "E00686",
        "AEAT_CONTRATISTAS",
        {"configured": True, "status": "valid"},
        [{
            "id": "sol-activa",
            "company_code": "E00686",
            "certificate_type": "AEAT_CONTRATISTAS",
            "status": "processing",
        }],
    )

    assert aviso.call_args.args[0] == "Solicitud ya en curso"
    vista.refresh.assert_called_once_with()
