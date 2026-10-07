from unittest.mock import MagicMock

from views.ui_adjuntos_mensajeria import (
    UIAdjuntosMensajeria,
    _opciones_origen,
    _resumen_pendientes_por_origen,
)


def _vista_sin_tk(item):
    vista = object.__new__(UIAdjuntosMensajeria)
    vista._item_seleccionado = MagicMock(return_value=item)
    vista._revisar_adjuntos_correo = MagicMock()
    return vista


def test_revisar_entrada_de_correo_abre_sus_adjuntos():
    item = {
        "id": "correo:mensaje-1",
        "canal": "correo",
        "mailbox": "documentacion@gestinem.es",
        "graph_message_id": "mensaje-1",
    }
    vista = _vista_sin_tk(item)

    UIAdjuntosMensajeria._abrir_archivo(vista)

    vista._revisar_adjuntos_correo.assert_called_once_with(item)


def test_revisar_adjunto_de_mensajeria_mantiene_apertura_directa(
    monkeypatch, tmp_path,
):
    archivo = tmp_path / "factura.pdf"
    archivo.write_bytes(b"PDF")
    vista = _vista_sin_tk({
        "id": "mensajeria:adjunto-1",
        "canal": "mensajeria",
        "ruta_entrada": str(archivo),
    })
    abrir = MagicMock()
    monkeypatch.setattr("views.ui_adjuntos_mensajeria.os.startfile", abrir)

    UIAdjuntosMensajeria._abrir_archivo(vista)

    abrir.assert_called_once_with(str(archivo))
    vista._revisar_adjuntos_correo.assert_not_called()


def test_filtro_por_origen_separa_correo_y_mensajeria():
    datos = [
        {"id": "1", "origen_label": "Correo Oficina", "canal": "correo"},
        {
            "id": "2",
            "origen_label": "Correo Documentacion",
            "canal": "correo",
        },
        {"id": "3", "origen_label": "Mensajeria de clientes"},
    ]

    filtrados = UIAdjuntosMensajeria._filtrar_por_origen(
        datos, "Correo Documentacion",
    )

    assert [item["id"] for item in filtrados] == ["2"]
    assert UIAdjuntosMensajeria._filtrar_por_origen(datos, "Todos") == datos


def test_filtro_incluye_mensajeria_aunque_no_haya_entradas():
    assert "Mensajeria" in _opciones_origen([])


def test_filtro_mensajeria_agrupa_etiquetas_nuevas_y_antiguas():
    datos = [
        {"id": "nuevo", "origen_label": "Mensajeria de clientes"},
        {"id": "antiguo", "canal": "mensajeria"},
        {"id": "correo", "origen_label": "Correo Oficina"},
    ]

    filtrados = UIAdjuntosMensajeria._filtrar_por_origen(
        datos, "Mensajeria",
    )

    assert [item["id"] for item in filtrados] == ["nuevo", "antiguo"]


def test_resumen_pendientes_muestra_cada_buzon_y_mensajeria():
    datos = [
        {"origen_label": "Correo Oficina", "canal": "correo"},
        {"origen_label": "Correo Documentacion", "canal": "correo"},
        {"origen_label": "Correo Documentacion", "canal": "correo"},
        {"origen_label": "Mensajeria de clientes", "canal": "mensajeria"},
    ]

    assert _resumen_pendientes_por_origen(datos) == {
        "Correo Oficina": 1,
        "Correo Documentacion": 2,
        "Mensajeria": 1,
    }
