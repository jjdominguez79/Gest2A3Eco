from types import SimpleNamespace

from views.ui_gestion_documental import _MultipleImportDialog


class _Tree:
    def __init__(self):
        self.rows = {}

    def insert(self, _parent, _position, *, iid, values):
        self.rows[iid] = values


class _Label:
    def __init__(self):
        self.text = ""

    def configure(self, **values):
        self.text = values.get("text", self.text)


def test_lista_multiple_ignora_duplicados_y_carpetas(tmp_path):
    document = tmp_path / "factura.pdf"
    document.write_bytes(b"pdf")
    dialog = object.__new__(_MultipleImportDialog)
    dialog._paths = {}
    dialog._path_keys = set()
    dialog._next_id = 1
    dialog._tree = _Tree()
    dialog._summary = _Label()
    dialog._status = _Label()

    added = _MultipleImportDialog._add_paths(
        dialog, [document, document, tmp_path],
    )

    assert added == 1
    assert list(dialog._paths.values()) == [document]
    assert dialog._tree.rows["archivo-1"][0] == "factura.pdf"
    assert dialog._summary.text == "1 documentos · 3 B"
    assert "1 elementos" in dialog._status.text


def test_arrastre_devuelve_la_accion_de_windows(tmp_path):
    document = tmp_path / "informe.pdf"
    document.write_bytes(b"pdf")
    dialog = object.__new__(_MultipleImportDialog)
    dialog._paths = {}
    dialog._path_keys = set()
    dialog._next_id = 1
    dialog._tree = _Tree()
    dialog._summary = _Label()
    dialog._status = _Label()
    dialog._drop_zone = _Label()
    dialog.tk = SimpleNamespace(splitlist=lambda _raw: (str(document),))
    event = SimpleNamespace(data=str(document), action="copy")

    result = _MultipleImportDialog._on_drop(dialog, event)

    assert result == "copy"
    assert list(dialog._paths.values()) == [document]
