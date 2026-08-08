import hashlib
from pathlib import Path

from services.gestion_documental_service import GestionDocumentalService


class _Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _Conn:
    def execute(self, _sql, _params=()):
        return _Result()


class _Gestor:
    def __init__(self):
        self.conn = _Conn()
        self.saved = None

    def listar_categorias_documentales(self):
        return [{
            "id": "facturas_recibidas", "nombre": "Facturas recibidas",
            "carpeta": "FACTURAS_RECIBIDAS", "permite_ocr": 1,
        }]

    def registrar_documento_archivo(self, payload):
        self.saved = payload
        return "doc-chat-1"


def test_adjunto_chat_se_archiva_como_factura_y_elimina_entrada(tmp_path, monkeypatch):
    repository = tmp_path / "repo"
    monkeypatch.setattr(
        "services.gestion_documental_service.get_document_repository_dir",
        lambda: repository,
    )
    source = tmp_path / "entrada" / "factura.pdf"
    source.parent.mkdir()
    source.write_bytes(b"%PDF-chat")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    gestor = _Gestor()

    document_id = GestionDocumentalService(gestor).archivar_adjunto_mensajeria(
        {
            "codigo_empresa": "E00001", "ruta_entrada": str(source),
            "nombre_original": "factura.pdf", "hash_archivo": digest,
            "mime_type": "application/pdf", "mensaje_remoto_id": "msg-1",
            "remitente": "Cliente Uno",
        },
        ejercicio=2026, categoria_id="facturas_recibidas", usuario="Empleado",
    )

    assert document_id == "doc-chat-1"
    assert not source.exists()
    assert Path(gestor.saved["ruta"]).read_bytes() == b"%PDF-chat"
    assert gestor.saved["origen"] == "chat"
    assert gestor.saved["categoria_id"] == "facturas_recibidas"
    assert gestor.saved["mensaje_id"] == "msg-1"
