import hashlib
from pathlib import Path
from unittest.mock import MagicMock

from services.documentos_correo_service import DocumentosCorreoService
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


class _GraphCorreo:
    def list_attachments(self, *, mailbox, message_id):
        self.listado = (mailbox, message_id)
        return [{"id": "adj-1", "name": "factura.pdf"}]

    def download_attachment(self, *, mailbox, message_id, attachment_id):
        self.descarga = (mailbox, message_id, attachment_id)
        return {
            "contentBytes": "JVBERi1jb3JyZW8=",
            "contentType": "application/pdf",
        }

    def mark_as_read(self, *, mailbox, message_id):
        self.marcado_leido = (mailbox, message_id)


class _GestorCorreo(_Gestor):
    def __init__(self):
        super().__init__()
        self.decisiones = []

    def registrar_documento_archivo(self, payload):
        self.saved = payload
        return "doc-correo-1"

    def registrar_decision_adjunto(self, payload):
        self.decisiones.append(payload)

    def asignar_comunicacion_pendiente(
        self, graph_id, codigo_empresa, usuario_id, usuario,
    ):
        self.asignacion = (graph_id, codigo_empresa, usuario_id, usuario)
        return True

    def vincular_documentos_graph_comunicacion(self, graph_id):
        self.vinculado = graph_id


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


def test_gestion_documental_usa_backend_para_adjuntos_de_correo(monkeypatch):
    backend = object()
    monkeypatch.setattr(
        "services.gestion_documental_service.BackendMailService",
        lambda: backend,
    )

    service = GestionDocumentalService(object())

    assert service._graph is backend


def test_clasificar_correo_usa_la_misma_bandeja_y_conserva_el_buzon(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(
        "services.gestion_documental_service.get_document_repository_dir",
        lambda: tmp_path / "repo",
    )
    gestor = _GestorCorreo()
    graph = _GraphCorreo()
    entrada = {
        "canal": "correo",
        "entrada_id": "correo-1",
        "graph_message_id": "graph-1",
        "mailbox": "oficina@gestinem.es",
        "codigo_empresa": "E00001",
        "remitente": "proveedor@example.com",
        "asunto": "Factura septiembre",
    }

    summary = GestionDocumentalService(gestor, graph=graph).clasificar_entrada_documental(
        entrada, ejercicio=2026, categoria_id="facturas_recibidas",
        usuario="Empleado", usuario_id=17,
    )

    assert summary.document_ids == ["doc-correo-1"]
    assert gestor.saved["origen"] == "correo"
    assert gestor.saved["buzon_origen"] == "oficina@gestinem.es"
    assert gestor.asignacion == ("graph-1", "E00001", 17, "Empleado")
    assert gestor.vinculado == "graph-1"
    assert graph.marcado_leido == ("oficina@gestinem.es", "graph-1")
    assert summary.warnings == []


def test_clasificar_correo_no_revierte_el_archivo_si_outlook_falla(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(
        "services.gestion_documental_service.get_document_repository_dir",
        lambda: tmp_path / "repo",
    )
    gestor = _GestorCorreo()
    graph = _GraphCorreo()
    graph.mark_as_read = MagicMock(side_effect=RuntimeError("Graph no disponible"))

    summary = GestionDocumentalService(gestor, graph=graph).clasificar_entrada_documental(
        {
            "canal": "correo", "graph_message_id": "graph-1",
            "mailbox": "documentacion@gestinem.es", "codigo_empresa": "E00001",
            "remitente": "proveedor@example.com", "asunto": "Factura",
        },
        ejercicio=2026, categoria_id="facturas_recibidas",
        usuario="Empleado", usuario_id=17,
    )

    assert summary.document_ids == ["doc-correo-1"]
    assert summary.warnings == [
        "El correo se ha archivado, pero Outlook no pudo marcarlo como leido: "
        "Graph no disponible"
    ]


def test_importacion_desde_comunicaciones_reutiliza_el_archivo_documental(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(
        "services.gestion_documental_service.get_document_repository_dir",
        lambda: tmp_path / "repo",
    )
    gestor = _GestorCorreo()
    summary = DocumentosCorreoService(
        gestor, graph=_GraphCorreo(),
    ).importar_adjuntos(
        codigo_empresa="E00001", ejercicio=2026, mensaje_id="mensaje-1",
        mailbox="documentacion@gestinem.es", graph_message_id="graph-1",
        attachment_ids=["adj-1"], usuario="Empleado",
    )

    assert summary.imported == ["factura.pdf"]
    assert gestor.saved["comunicacion_id"] == "mensaje-1"
    assert gestor.saved["buzon_origen"] == "documentacion@gestinem.es"


def test_importacion_multiple_conserva_exitos_y_errores_individuales(tmp_path):
    first = tmp_path / "primero.pdf"
    second = tmp_path / "segundo.pdf"
    first.write_bytes(b"primero")
    second.write_bytes(b"segundo")
    service = object.__new__(GestionDocumentalService)
    service.importar_archivo = MagicMock(
        side_effect=["doc-1", ValueError("documento duplicado")],
    )

    summary = service.importar_archivos(
        codigo_empresa="E00001",
        ejercicio=2026,
        categoria_id="fiscal",
        sources=[first, second],
        usuario="Empleado",
    )

    assert summary.saved == ["primero.pdf"]
    assert summary.document_ids == ["doc-1"]
    assert summary.errors == ["segundo.pdf: documento duplicado"]
    assert service.importar_archivo.call_count == 2
