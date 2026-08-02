import base64
from pathlib import Path

import pytest

from models.gestor_sqlite import GestorSQLite
from services.gestion_documental_service import GestionDocumentalService


class _GraphFalso:
    def __init__(self, contenidos):
        self.contenidos = contenidos

    def download_attachment(self, *, mailbox, message_id, attachment_id):
        contenido, tipo = self.contenidos[attachment_id]
        return {
            "contentBytes": base64.b64encode(contenido).decode("ascii"),
            "contentType": tipo,
        }


def _servicio(tmp_path, monkeypatch, contenidos=None):
    gestor = GestorSQLite(tmp_path / "documentos.db")
    raiz = tmp_path / "Doc_Compartidos" / "Gest2A3Eco"
    monkeypatch.setattr(
        "services.gestion_documental_service.get_document_repository_dir",
        lambda: raiz,
    )
    return gestor, GestionDocumentalService(
        gestor, graph=_GraphFalso(contenidos or {}),
    ), raiz


def test_categorias_documentales_iniciales(tmp_path, monkeypatch):
    gestor, servicio, _raiz = _servicio(tmp_path, monkeypatch)

    categorias = servicio.categorias()

    assert any(item["id"] == "facturas_recibidas" for item in categorias)
    assert [item["id"] for item in categorias if item["permite_ocr"]] == [
        "facturas_recibidas"
    ]
    gestor.conn.close()


def test_clasifica_guarda_e_ignora_adjuntos(tmp_path, monkeypatch):
    gestor, servicio, raiz = _servicio(
        tmp_path, monkeypatch,
        {
            "adj-1": (b"contenido factura", "application/pdf"),
            "adj-2": (b"no debe descargarse", "text/plain"),
        },
    )

    resumen = servicio.archivar_adjuntos_correo(
        codigo_empresa="E00001", ejercicio=2026,
        mailbox="oficina@gestinem.es", graph_message_id="msg-1",
        remitente="proveedor@example.com", asunto="Factura",
        decisiones=[
            {"attachment_id": "adj-1", "name": "Factura 01.pdf",
             "categoria_id": "facturas_recibidas"},
            {"attachment_id": "adj-2", "name": "logo.png",
             "categoria_id": ""},
        ],
        usuario="admin",
    )

    destino = (
        raiz / "Empresas" / "E00001" / "2026"
        / "FACTURAS_RECIBIDAS" / "Factura 01.pdf"
    )
    assert destino.read_bytes() == b"contenido factura"
    assert resumen.saved == ["Factura 01.pdf"]
    assert resumen.ignored == ["logo.png"]
    documentos = gestor.listar_documentos_archivo("E00001", 2026)
    assert len(documentos) == 1
    assert documentos[0]["graph_message_id"] == "msg-1"
    decisiones = gestor.conn.execute(
        "SELECT graph_attachment_id,accion FROM comunicaciones_adjuntos_decisiones "
        "ORDER BY graph_attachment_id"
    ).fetchall()
    assert [(row["graph_attachment_id"], row["accion"]) for row in decisiones] == [
        ("adj-1", "guardado"), ("adj-2", "no_guardar")
    ]
    gestor.conn.close()


def test_no_duplica_el_mismo_documento_del_cliente(tmp_path, monkeypatch):
    gestor, servicio, _raiz = _servicio(
        tmp_path, monkeypatch,
        {"adj-1": (b"mismo documento", "application/pdf"),
         "adj-2": (b"mismo documento", "application/pdf")},
    )
    comunes = dict(
        codigo_empresa="E00001", ejercicio=2026,
        mailbox="oficina@gestinem.es", remitente="proveedor@example.com",
        asunto="Factura", usuario="admin",
    )

    primero = servicio.archivar_adjuntos_correo(
        graph_message_id="msg-1",
        decisiones=[{"attachment_id": "adj-1", "name": "uno.pdf",
                     "categoria_id": "facturas_recibidas"}], **comunes,
    )
    segundo = servicio.archivar_adjuntos_correo(
        graph_message_id="msg-2",
        decisiones=[{"attachment_id": "adj-2", "name": "dos.pdf",
                     "categoria_id": "facturas_recibidas"}], **comunes,
    )

    assert primero.saved == ["uno.pdf"]
    assert segundo.duplicates == ["dos.pdf"]
    assert len(gestor.listar_documentos_archivo("E00001", 2026)) == 1
    gestor.conn.close()


def test_importacion_manual_rechaza_duplicados(tmp_path, monkeypatch):
    gestor, servicio, _raiz = _servicio(tmp_path, monkeypatch)
    origen = tmp_path / "contrato.pdf"
    origen.write_bytes(b"contrato")

    documento_id = servicio.importar_archivo(
        codigo_empresa="E00002", ejercicio=2026,
        categoria_id="contratos", source=origen, usuario="admin",
    )

    assert gestor.get_documento_archivo(documento_id)["origen"] == "manual"
    with pytest.raises(ValueError, match="ya existe"):
        servicio.importar_archivo(
            codigo_empresa="E00002", ejercicio=2026,
            categoria_id="contratos", source=origen, usuario="admin",
        )
    gestor.conn.close()


def test_archiva_en_repositorio_compartido_y_no_en_a3(tmp_path, monkeypatch):
    gestor, servicio, raiz_compartida = _servicio(tmp_path, monkeypatch)

    destino = servicio._category_directory("00724", 2026, "FACTURAS_RECIBIDAS")

    assert destino == (
        raiz_compartida / "Empresas" / "E00724" / "2026"
        / "FACTURAS_RECIBIDAS"
    )
    gestor.conn.close()
