from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from requests import Timeout

from services.aapp.notification_communication import (
    ComunicadorNotificacionesCliente, render_email_notificaciones,
)


def _item(codigo, numero, **extra):
    return {
        "id": numero, "codigo_empresa": codigo, "asunto": f"Aviso {numero}",
        "pdf_path": f"{numero}.pdf", **extra,
    }


def _servicio(avisar=True):
    gestor = SimpleNamespace(
        get_notif_config_global=Mock(return_value={"avisar_cliente_email": avisar}),
        get_empresa=Mock(side_effect=lambda codigo: {
            "nombre": codigo, "email": f"{codigo}@cliente.test",
        }),
        marcar_notif_bandeja_email_cliente=Mock(),
    )
    publicador = Mock()
    publicador.publicar_notificacion.return_value = SimpleNamespace(ok=True)
    correo = Mock()
    return ComunicadorNotificacionesCliente(gestor, publicador, correo), gestor, publicador, correo


def test_comunicar_multiple_agrupa_adjuntos_sin_mezclar_clientes():
    servicio, gestor, publicador, correo = _servicio()
    result = servicio.comunicar([_item("E00001", "1"), _item("E00002", "2"), _item("E00001", "3")])
    assert result.publicadas == 3
    assert result.emails_enviados == 2
    assert result.errores == []
    assert publicador.publicar_notificacion.call_count == 3
    assert correo.send.call_args_list[0].kwargs["to"] == ["E00001@cliente.test"]
    assert correo.send.call_args_list[0].kwargs["attachments"] == ["1.pdf", "3.pdf"]
    assert "Aviso 2" not in correo.send.call_args_list[0].kwargs["body"]
    assert correo.send.call_args_list[1].kwargs["attachments"] == ["2.pdf"]
    assert [call.args[2] for call in gestor.marcar_notif_bandeja_email_cliente.call_args_list].count("ENVIADO") == 3


def test_no_envia_email_si_politica_global_lo_desactiva():
    servicio, _, publicador, correo = _servicio(False)
    result = servicio.comunicar([_item("E00001", "1")])
    assert result.publicadas == 1
    assert result.emails_enviados == 0
    publicador.publicar_notificacion.assert_called_once()
    correo.send.assert_not_called()


def test_no_adjunta_documentos_cuya_publicacion_falla():
    servicio, _, publicador, correo = _servicio()
    publicador.publicar_notificacion.side_effect = [SimpleNamespace(ok=False, mensaje="Fallo"), SimpleNamespace(ok=True)]
    result = servicio.comunicar([_item("E00001", "1"), _item("E00001", "2")])
    assert result.publicadas == 1
    assert len(result.errores) == 1
    assert correo.send.call_args.kwargs["attachments"] == ["2.pdf"]


def test_reintenta_email_fallido_sin_republicar_pdf():
    servicio, _, publicador, correo = _servicio()
    result = servicio.comunicar([_item("E00001", "1", enviada_cliente=1, email_cliente_estado="ERROR")])
    assert result.emails_enviados == 1
    publicador.publicar_notificacion.assert_not_called()
    correo.send.assert_called_once()


@pytest.mark.parametrize("estado", ["ENVIADO", "ENVIANDO", "DESCONOCIDO"])
def test_no_reenvia_email_confirmado_o_incierto(estado):
    servicio, _, _, correo = _servicio()
    servicio.comunicar([_item("E00001", "1", enviada_cliente=1, email_cliente_estado=estado)])
    correo.send.assert_not_called()


def test_email_invalido_ficha_registra_error():
    servicio, gestor, _, correo = _servicio()
    gestor.get_empresa.side_effect = None
    gestor.get_empresa.return_value = {"email": ""}
    result = servicio.comunicar([_item("E00001", "1")])
    assert "email valido" in result.errores[0]
    correo.send.assert_not_called()
    assert gestor.marcar_notif_bandeja_email_cliente.call_args.args[2] == "ERROR"


def test_timeout_no_se_considera_fallo_seguro_para_reenviar():
    servicio, gestor, _, correo = _servicio()
    correo.send.side_effect = Timeout("Tiempo agotado")
    servicio.comunicar([_item("E00001", "1")])
    assert gestor.marcar_notif_bandeja_email_cliente.call_args.args[2] == "DESCONOCIDO"


def test_permisos_se_comprueban_antes_de_enviar_documentos():
    servicio, gestor, publicador, correo = _servicio()
    gestor.security = Mock()
    gestor.security.ensure_company_write.side_effect = PermissionError("Solo lectura")
    result = servicio.comunicar([_item("E00001", "1")])
    assert result.publicadas == 0
    publicador.publicar_notificacion.assert_not_called()
    correo.send.assert_not_called()


def test_plantilla_especifica_escapa_html_pero_no_asunto():
    asunto, html = render_email_notificaciones(
        {"email_asunto": "{nombre_cliente}: {asunto}", "email_html": "<p>{nombre_cliente}</p>{notificaciones}"},
        {"nombre": "A & B <Cliente>"},
        [_item("E00001", "1", asunto="<Aviso> & datos")],
    )
    assert asunto == "A & B <Cliente>: <Aviso> & datos"
    assert "A &amp; B &lt;Cliente&gt;" in html
    assert "&lt;Aviso&gt; &amp; datos" in html
    with pytest.raises(ValueError, match="desconocido"):
        render_email_notificaciones({"email_html": "{campo_inexistente}"}, {}, [_item("E00001", "1")])
