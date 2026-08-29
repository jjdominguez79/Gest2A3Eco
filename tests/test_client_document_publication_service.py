"""Pruebas de la cola local de facturas para el area del cliente."""

from __future__ import annotations

import requests

from services.client_document_publication_service import (
    ClientDocumentPublicationService,
)


class _GestorStub:
    def __init__(self, *, enqueue=True):
        self.enqueue = enqueue
        self.queued = []
        self.success = []
        self.failed = []

    def encolar_publicacion_area_cliente(self, *args):
        self.queued.append(args)
        return self.enqueue

    def marcar_publicacion_area_cliente_exitosa(self, *args):
        self.success.append(args)

    def marcar_publicacion_area_cliente_fallida(self, *args, **kwargs):
        self.failed.append((args, kwargs))


class _BackendStub:
    configured = True

    def __init__(self, *, result=None, error=None):
        self.result = result or {"id": "doc-1", "source_version": 1}
        self.error = error
        self.calls = []

    def publish_document(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


def _factura():
    return {
        "id": "fac-1",
        "serie": "A",
        "numero": "42",
        "codigo_empresa": "E00006",
        "nif": "B12345678",
        "ejercicio": 2026,
        "fecha_expedicion": "2026-08-29",
    }


def test_encola_antes_de_publicar_y_confirma_resultado(tmp_path):
    pdf = tmp_path / "factura.pdf"
    pdf.write_bytes(b"%PDF-1.4 factura")
    gestor = _GestorStub()
    backend = _BackendStub(result={"id": "doc-8", "source_version": 2})

    result = ClientDocumentPublicationService(
        gestor, backend,
    ).enqueue_and_publish(_factura(), str(pdf), amount=121.0)

    assert result.status == "publicada"
    assert gestor.queued
    assert gestor.success == [("fac-1", "doc-8", 2)]
    assert backend.calls[0]["source_type"] == "factura"
    assert backend.calls[0]["company_code"] == "E00006"
    assert backend.calls[0]["customer_tax_id"] == "B12345678"
    assert backend.calls[0]["expected_sha256"] == gestor.queued[0][2]


def test_fallo_transitorio_queda_pendiente_con_reintento(tmp_path):
    pdf = tmp_path / "factura.pdf"
    pdf.write_bytes(b"%PDF-1.4 factura")
    gestor = _GestorStub()
    backend = _BackendStub(error=requests.ConnectionError("sin red"))

    result = ClientDocumentPublicationService(
        gestor, backend,
    ).enqueue_and_publish(_factura(), str(pdf), amount=121.0)

    assert result.status == "error"
    assert gestor.failed[0][1]["blocked"] is False
    assert gestor.failed[0][1]["next_retry_at"]


def test_error_de_datos_bloquea_hasta_revision(tmp_path):
    pdf = tmp_path / "factura.pdf"
    pdf.write_bytes(b"%PDF-1.4 factura")
    response = requests.Response()
    response.status_code = 404
    response._content = b'{"detail":"Cliente no encontrado"}'
    error = requests.HTTPError(response=response)
    gestor = _GestorStub()

    result = ClientDocumentPublicationService(
        gestor, _BackendStub(error=error),
    ).enqueue_and_publish(_factura(), str(pdf), amount=121.0)

    assert result.status == "bloqueada"
    assert result.error == "Cliente no encontrado"
    assert gestor.failed[0][1]["blocked"] is True
    assert gestor.failed[0][1]["next_retry_at"] is None


def test_pdf_ya_publicado_no_se_vuelve_a_enviar(tmp_path):
    pdf = tmp_path / "factura.pdf"
    pdf.write_bytes(b"%PDF-1.4 factura")
    gestor = _GestorStub(enqueue=False)
    backend = _BackendStub()
    factura = _factura() | {
        "area_cliente_documento_id": "doc-previo",
        "area_cliente_version": 3,
    }

    result = ClientDocumentPublicationService(
        gestor, backend,
    ).enqueue_and_publish(factura, str(pdf), amount=121.0)

    assert result.status == "publicada"
    assert result.document_id == "doc-previo"
    assert backend.calls == []
