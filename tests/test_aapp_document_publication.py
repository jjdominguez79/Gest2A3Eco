from __future__ import annotations

from services.aapp.document_publication import PublicadorDocumentosAAPP


class _Gestor:
    def __init__(self):
        self.cert_publicado = []
        self.cert_error = []
        self.notif_publicada = []
        self.notif_error = []

    def get_empresa(self, codigo):
        return {"codigo": codigo, "cif": "B12345678"}

    def marcar_cert_solicitud_publicada(self, *args):
        self.cert_publicado.append(args)

    def marcar_cert_solicitud_publicacion_error(self, *args):
        self.cert_error.append(args)

    def marcar_notif_bandeja_publicada_cliente(self, *args):
        self.notif_publicada.append(args)

    def marcar_notif_bandeja_publicacion_error(self, *args):
        self.notif_error.append(args)


class _Backend:
    def __init__(self):
        self.calls = []

    def publish_document(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": "doc-42", "source_version": 2}


def _pdf(tmp_path):
    path = tmp_path / "documento.pdf"
    path.write_bytes(b"%PDF-1.4 contenido")
    return str(path)


def test_publica_certificado_tgss_en_documentos_flutter(tmp_path):
    gestor = _Gestor()
    backend = _Backend()
    solicitud = {
        "id": "sol-1",
        "codigo_empresa": "E00001",
        "tipo": "TGSS_CORRIENTE",
        "estado": "OBTENIDO",
        "fecha_obtencion": "2026-08-29T10:00:00",
        "pdf_path": _pdf(tmp_path),
    }

    resultado = PublicadorDocumentosAAPP(gestor, backend).publicar_certificado(solicitud)

    assert resultado.ok is True
    assert backend.calls[0]["source_system"] == "desktop_aapp"
    assert backend.calls[0]["source_type"] == "certificado_tgss"
    assert backend.calls[0]["company_code"] == "E00001"
    assert backend.calls[0]["customer_tax_id"] == "B12345678"
    assert gestor.cert_publicado[0][:4] == ("E00001", "sol-1", "doc-42", 2)


def test_publica_notificacion_dehu_en_documentos_flutter(tmp_path):
    gestor = _Gestor()
    backend = _Backend()
    notificacion = {
        "id": "nb-1",
        "codigo_empresa": "E00001",
        "ejercicio": 2026,
        "asunto": "Requerimiento",
        "fecha_puesta_disposicion": "2026-08-28",
        "pdf_path": _pdf(tmp_path),
    }

    resultado = PublicadorDocumentosAAPP(gestor, backend).publicar_notificacion(notificacion)

    assert resultado.ok is True
    assert backend.calls[0]["source_type"] == "notificacion_dehu"
    assert backend.calls[0]["company_code"] == "E00001"
    assert gestor.notif_publicada[0][:4] == ("E00001", "nb-1", "doc-42", 2)


def test_no_marca_como_enviado_si_falta_el_pdf(tmp_path):
    gestor = _Gestor()

    resultado = PublicadorDocumentosAAPP(gestor, _Backend()).publicar_notificacion({
        "id": "nb-2", "codigo_empresa": "E00001", "pdf_path": str(tmp_path / "no.pdf"),
    })

    assert resultado.ok is False
    assert gestor.notif_publicada == []
    assert gestor.notif_error and gestor.notif_error[0][0:2] == ("E00001", "nb-2")
