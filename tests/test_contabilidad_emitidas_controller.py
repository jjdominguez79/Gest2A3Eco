from types import SimpleNamespace

from controllers.ui_contabilidad_emitidas_controller import (
    UIContabilidadEmitidasController,
)


def test_eliminar_asiento_y_reiniciar_exige_confirmacion_motivo_y_password(
    monkeypatch,
):
    llamadas = []

    class GestorStub:
        def reiniciar_facturas_emitidas_con_asiento(
            self, codigo, ejercicio, ids, motivo,
        ):
            llamadas.append((codigo, ejercicio, ids, motivo))
            return {"facturacion": 1, "ocr": 0, "sin_asiento": []}

    avisos = []
    view = SimpleNamespace(
        _emitidas_docs=[
            {"id": "fac-1", "numero_asiento": "08/00042"},
            {"id": "fac-2", "numero_asiento": ""},
        ],
        get_selected_emitida_ids=lambda: ["fac-1", "fac-2"],
        ask_yes_no=lambda *_args: True,
        ask_return_reason=lambda *_args: "Correccion de conceptos",
        ask_admin_password=lambda *_args: "secreta",
        show_warning=lambda *args: avisos.append(("warning", args)),
        show_error=lambda *args: avisos.append(("error", args)),
        show_info=lambda *args: avisos.append(("info", args)),
    )
    controller = UIContabilidadEmitidasController(
        GestorStub(), "E00001", 2026, view,
    )
    controller.refresh = lambda: llamadas.append(("refresh",))
    monkeypatch.setattr(
        "utils.credential_store.get_desmarcar_password",
        lambda: "secreta",
    )

    controller.eliminar_asiento_y_reiniciar()

    assert llamadas == [
        ("E00001", 2026, ["fac-1"], "Correccion de conceptos"),
        ("refresh",),
    ]
    assert any(tipo == "info" for tipo, _args in avisos)


def test_eliminar_asiento_y_reiniciar_rechaza_password_incorrecta(monkeypatch):
    llamadas = []
    view = SimpleNamespace(
        _emitidas_docs=[{"id": "fac-1", "numero_asiento": "08/00042"}],
        get_selected_emitida_ids=lambda: ["fac-1"],
        ask_yes_no=lambda *_args: True,
        ask_return_reason=lambda *_args: "Correccion de conceptos",
        ask_admin_password=lambda *_args: "incorrecta",
        show_warning=lambda *_args: None,
        show_error=lambda *args: llamadas.append(("error", args)),
        show_info=lambda *_args: None,
    )
    gestor = SimpleNamespace(
        reiniciar_facturas_emitidas_con_asiento=lambda *_args: llamadas.append(
            ("reiniciar",)
        )
    )
    controller = UIContabilidadEmitidasController(
        gestor, "E00001", 2026, view,
    )
    monkeypatch.setattr(
        "utils.credential_store.get_desmarcar_password",
        lambda: "secreta",
    )

    controller.eliminar_asiento_y_reiniciar()

    assert llamadas and llamadas[0][0] == "error"
    assert not any(item[0] == "reiniciar" for item in llamadas)
