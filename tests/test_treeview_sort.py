from datetime import datetime
from decimal import Decimal

from views.treeview_sort import OrdenadorTreeview, clave_orden_treeview


class _Tree:
    def __init__(self, rows):
        self.rows = dict(rows)
        self.order = list(self.rows)
        self.headings = {}

    def heading(self, column, **kwargs):
        self.headings[column] = kwargs

    def get_children(self, _parent=""):
        return tuple(self.order)

    def set(self, item_id, column):
        return self.rows[item_id].get(column, "")

    def move(self, item_id, _parent, position):
        self.order.remove(item_id)
        self.order.insert(position, item_id)


def test_clave_ordena_fechas_numeros_y_texto_sin_acentos():
    assert clave_orden_treeview("01/10/2026")[1] == datetime(2026, 10, 1)
    assert clave_orden_treeview("01/10/2026 (5d)")[1] == datetime(2026, 10, 1)
    assert clave_orden_treeview("12,5")[1] == Decimal("12.5")
    assert clave_orden_treeview("Álcedo") == clave_orden_treeview("alcedo")


def test_ordenador_alterna_y_deja_vacios_al_final():
    tree = _Tree({
        "a": {"cliente": "Zulu", "fecha": ""},
        "b": {"cliente": "Alcedo", "fecha": "02/10/2026"},
        "c": {"cliente": "Beta", "fecha": "30/09/2026"},
    })
    ordenador = OrdenadorTreeview(tree, (("cliente", "Cliente"), ("fecha", "Fecha")))

    ordenador.ordenar("cliente")
    assert tree.order == ["b", "c", "a"]
    assert tree.headings["cliente"]["text"] == "Cliente \u25b2"

    ordenador.ordenar("fecha")
    assert tree.order == ["c", "b", "a"]
    ordenador.ordenar("fecha")
    assert tree.order == ["b", "c", "a"]
    assert tree.headings["fecha"]["text"] == "Fecha \u25bc"
