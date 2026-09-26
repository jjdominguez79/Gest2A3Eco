from types import SimpleNamespace

from sync_worker.config import MailSource
from sync_worker.worker import MailSyncWorker


class RepositoryStub:
    def __init__(self, delta=""):
        self.delta = delta
        self.saved_messages = None

    def get_delta(self, _mailbox):
        return self.delta

    def sync_messages(self, _mailbox, messages, _delta):
        self.saved_messages = messages
        return len(messages), 0


class GraphStub:
    def sync_inbox(self, **_kwargs):
        return SimpleNamespace(messages=[{"id": "old"}], delta_link="delta-1")


def worker_stub(*, delta="", import_existing=False):
    worker = object.__new__(MailSyncWorker)
    worker.config = SimpleNamespace(
        mailbox="oficina@gestinem.es",
        import_existing_on_first_run=import_existing,
    )
    worker.repository = RepositoryStub(delta)
    worker.graph = GraphStub()
    return worker


def test_primera_ejecucion_establece_delta_sin_importar_historico():
    worker = worker_stub()
    worker.run_once()
    assert worker.repository.saved_messages == []


def test_ejecuciones_incrementales_guardan_mensajes():
    worker = worker_stub(delta="delta-anterior")
    worker.run_once()
    assert worker.repository.saved_messages == [{"id": "old"}]


def test_importacion_historica_se_puede_habilitar():
    worker = worker_stub(import_existing=True)
    worker.run_once()
    assert worker.repository.saved_messages == [{"id": "old"}]


class MultiRepositoryStub:
    def __init__(self):
        self.calls = []

    def get_delta(self, _mailbox):
        return "delta-anterior"

    def sync_messages(self, mailbox, messages, _delta, **kwargs):
        self.calls.append((mailbox, messages, kwargs))
        return len(messages), 0

    def record_error(self, *_args):
        raise AssertionError("No se esperaba un error de sincronizacion")


class MultiGraphStub:
    def sync_inbox(self, *, mailbox, **_kwargs):
        if mailbox == "oficina@gestinem.es":
            messages = [{
                "id": "office-1",
                "toRecipients": [{"emailAddress": {"address": mailbox}}],
            }]
        else:
            messages = [
                {
                    "id": "docs-1",
                    "toRecipients": [{
                        "emailAddress": {"address": "documentacion@gestinem.es"},
                    }],
                },
                {
                    "id": "personal-1",
                    "toRecipients": [{"emailAddress": {"address": mailbox}}],
                },
            ]
        return SimpleNamespace(messages=messages, delta_link=f"delta-{mailbox}")


def test_sincroniza_documentacion_sin_importar_correo_personal():
    worker = object.__new__(MailSyncWorker)
    worker.config = SimpleNamespace(
        mailbox="oficina@gestinem.es",
        mail_sources=(
            MailSource("oficina@gestinem.es", label="Oficina"),
            MailSource(
                "jjdominguez@gestinem.es",
                recipient_filter="documentacion@gestinem.es",
                label="Documentacion",
            ),
        ),
        import_existing_on_first_run=False,
    )
    worker.repository = MultiRepositoryStub()
    worker.graph = MultiGraphStub()

    worker.run_once()

    assert [call[0] for call in worker.repository.calls] == [
        "oficina@gestinem.es", "jjdominguez@gestinem.es",
    ]
    assert [item["id"] for item in worker.repository.calls[1][1]] == ["docs-1"]
    assert worker.repository.calls[1][2] == {"label": "Documentacion"}
