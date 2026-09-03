import hashlib
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

from sync_worker.messaging_worker import MessagingAttachmentWorker


class Response:
    def __init__(self, *, payload=None, content=b"", status=200):
        self._payload = payload
        self.content = content
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class Session:
    def __init__(self, item, content):
        self.item = item
        self.content = content
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if url.endswith("/pending"):
            return Response(payload=[self.item])
        return Response(content=self.content)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return Response(payload={"ok": True})

    def put(self, url, **kwargs):
        self.calls.append(("PUT", url, kwargs))
        return Response(payload={"ok": True, "synchronized": len(kwargs.get("json") or [])})


def _config(tmp_path):
    return SimpleNamespace(
        api_url="https://api.example.test", sync_token="secret",
        repository_dir=tmp_path, postgres_dsn="unused", worker_id="synology",
        public_repository_dir=PureWindowsPath(r"\\Servidor\Documentos\Gest2A3Eco"),
        interval_seconds=60,
    )


def test_worker_configura_reintentos_y_evitar_conexion_persistente(tmp_path):
    worker = MessagingAttachmentWorker(_config(tmp_path))

    retry = worker.http.get_adapter("https://").max_retries
    assert retry.total == 3
    assert retry.allowed_methods == frozenset({"GET", "PUT"})
    assert worker._headers["Connection"] == "close"


def test_worker_descarga_verifica_guarda_y_confirma(tmp_path, monkeypatch):
    content = b"%PDF-adjunto-chat"
    item = {
        "id": "att-1", "message_id": "msg-1", "conversation_id": "conv-1",
        "company_code": "E00042", "company_name": "Cliente", "name": "factura.pdf",
        "size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
        "content_type": "application/pdf", "author_name": "Ana",
    }
    session = Session(item, content)
    worker = MessagingAttachmentWorker(_config(tmp_path), session=session)
    saved = []
    monkeypatch.setattr(worker, "_existing", lambda _attachment_id: None)
    monkeypatch.setattr(worker, "_save", lambda row, path, digest: saved.append((row, path, digest)))

    assert worker.run_once() == (1, 0)
    destination = tmp_path / "Entrada" / "Mensajeria" / "E00042" / "att-1_factura.pdf"
    assert destination.read_bytes() == content
    assert saved[0][1] == (
        r"\\Servidor\Documentos\Gest2A3Eco\Entrada\Mensajeria"
        r"\E00042\att-1_factura.pdf"
    )
    assert saved[0][2] == item["sha256"]
    assert any(method == "POST" and url.endswith("/confirm") for method, url, _ in session.calls)


def test_worker_de_adjuntos_no_sincroniza_datos_maestros(tmp_path):
    worker = MessagingAttachmentWorker(_config(tmp_path), session=Session({}, b""))
    assert not hasattr(worker, "sync_organizations")
