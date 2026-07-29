import base64
from pathlib import Path

from models.gestor_sqlite import GestorSQLite
from services.documentos_correo_service import DocumentosCorreoService


class FakeGraph:
    def __init__(self, attachments):
        self.attachments = attachments

    def download_attachment(self, **kwargs):
        return self.attachments[kwargs["attachment_id"]]


class FakeOcr:
    def __init__(self, gestor, empresa, ejercicio, usuario=""):
        self.gestor = gestor
        self.empresa = empresa

    def procesar_archivo(self, path):
        data = Path(path).read_bytes()
        import hashlib
        self.gestor.upsert_documento_ocr({
            "id": f"doc-{Path(path).stem}", "empresa_id": self.empresa,
            "ruta_original": path, "nombre_archivo": Path(path).name,
            "hash_archivo": hashlib.sha256(data).hexdigest(), "estado": "pendiente_revision",
        })
        return {"estado": "pendiente_revision"}


def test_importa_varios_adjuntos_a_carpeta_recibidas_y_registra_trazabilidad(tmp_path, monkeypatch):
    import services.documentos_correo_service as module
    monkeypatch.setattr(module, "OcrService", FakeOcr)
    monkeypatch.setattr(module, "get_default_received_documents_dir", lambda: tmp_path / "pdfs_recibidas")
    gestor = GestorSQLite(tmp_path / "test.db")
    _, mensaje_id = gestor.registrar_envio_comunicacion({
        "codigo_empresa": "E00001", "asunto": "Factura", "remitente": "oficina@example.com",
        "destinatarios": ["cliente@example.com"], "cc": [], "cuerpo_html": "", "estado_envio": "aceptado",
    })
    graph = FakeGraph({
        "a": {"id": "a", "name": "F-1.pdf", "size": 3, "contentBytes": base64.b64encode(b"uno").decode()},
        "b": {"id": "b", "name": "foto.JPG", "size": 3, "contentBytes": base64.b64encode(b"dos").decode()},
    })

    summary = DocumentosCorreoService(gestor, graph).importar_adjuntos(
        codigo_empresa="E00001", ejercicio=2026, mensaje_id=mensaje_id,
        mailbox="oficina@example.com", graph_message_id="graph-1",
        attachment_ids=["a", "b"], usuario="Ana",
    )

    assert summary.imported == ["F-1.pdf", "foto.JPG"]
    assert (tmp_path / "pdfs_recibidas" / "E00001" / "2026" / "F-1.pdf").read_bytes() == b"uno"
    rows = gestor.conn.execute("SELECT nombre FROM comunicaciones_adjuntos WHERE mensaje_id=?", (mensaje_id,)).fetchall()
    assert {row["nombre"] for row in rows} == {"F-1.pdf", "foto.JPG"}


def test_no_copia_un_adjunto_duplicado_ni_archivo_no_compatible(tmp_path, monkeypatch):
    import services.documentos_correo_service as module
    monkeypatch.setattr(module, "OcrService", FakeOcr)
    monkeypatch.setattr(module, "get_default_received_documents_dir", lambda: tmp_path / "pdfs_recibidas")
    gestor = GestorSQLite(tmp_path / "test.db")
    content = b"ya existe"
    import hashlib
    gestor.upsert_documento_ocr({"id": "existente", "empresa_id": "E00001", "hash_archivo": hashlib.sha256(content).hexdigest()})
    graph = FakeGraph({
        "same": {"name": "repetida.pdf", "contentBytes": base64.b64encode(content).decode()},
        "word": {"name": "nota.docx", "contentBytes": base64.b64encode(b"x").decode()},
    })

    summary = DocumentosCorreoService(gestor, graph).importar_adjuntos(
        codigo_empresa="E00001", ejercicio=2026, mensaje_id="m", mailbox="x",
        graph_message_id="g", attachment_ids=["same", "word"],
    )

    assert summary.duplicates == ["repetida.pdf"]
    assert summary.unsupported == ["nota.docx"]
    assert not (tmp_path / "pdfs_recibidas").exists()
