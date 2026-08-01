from types import SimpleNamespace

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
