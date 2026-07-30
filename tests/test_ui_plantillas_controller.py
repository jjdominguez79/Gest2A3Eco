from controllers.ui_plantillas_controller import PlantillasController
from views.ui_plantillas import InlineKVEditor


class TreeFalso:
    def selection(self):
        return ("fila-vacia",)

    def item(self, _iid, _opcion):
        return ("", "", "", "")

    def delete(self, *_args):
        pass

    def get_children(self):
        return ()

    def insert(self, *_args, **_kwargs):
        pass


class GestorFalso:
    def __init__(self):
        self.eliminada = None
        self.guardada = None
        self.bancos = []

    def listar_bancos(self, _codigo, _ejercicio):
        return self.bancos

    def listar_emitidas(self, _codigo, _ejercicio):
        return []

    def listar_recibidas(self, _codigo, _ejercicio):
        return []

    def eliminar_banco(self, codigo, banco, ejercicio):
        self.eliminada = (codigo, banco, ejercicio)

    def upsert_banco(self, plantilla):
        self.guardada = dict(plantilla)


class VistaFalsa:
    def ask_yes_no(self, _titulo, _mensaje):
        return True

    def show_info(self, *_args):
        pass

    def open_config_dialog(self, _tipo, plantilla):
        actualizada = dict(plantilla)
        actualizada["banco"] = "Cuenta nueva"
        actualizada["numero_cuenta"] = "ES02"
        return True, actualizada


def test_eliminar_plantilla_banco_con_nombre_vacio():
    gestor = GestorFalso()
    controller = PlantillasController(
        gestor, {"codigo": "E00505", "ejercicio": 2026}, VistaFalsa()
    )
    tree = TreeFalso()
    controller.register_tabs(
        {"tv": tree}, {"tv": tree}, {"tv": tree}
    )

    controller.eliminar(tree, "Bancos")

    assert gestor.eliminada == ("E00505", "", 2026)


def test_configurar_cuenta_distinta_reemplaza_plantilla_anterior():
    gestor = GestorFalso()
    gestor.bancos = [{
        "codigo_empresa": "E00505", "ejercicio": 2026,
        "banco": "Cuenta anterior", "numero_cuenta": "ES01",
    }]
    controller = PlantillasController(
        gestor, {"codigo": "E00505", "ejercicio": 2026}, VistaFalsa()
    )

    class TreeCuentaAnterior(TreeFalso):
        def item(self, _iid, _opcion):
            return ("Cuenta anterior", "ES01", "57200001", "55500000")

    tree = TreeCuentaAnterior()
    controller.register_tabs({"tv": tree}, {"tv": tree}, {"tv": tree})

    controller.config(tree, "Bancos")

    assert gestor.guardada["banco"] == "Cuenta nueva"
    assert gestor.eliminada == ("E00505", "Cuenta anterior", 2026)


def test_mapeo_excel_confirma_la_celda_activa_antes_de_guardar():
    class TreeMapeoFalso:
        def get_children(self):
            return ("fila",)

        def item(self, _iid, _opcion):
            return ("Importe", "F")

    class EditorFalso:
        tv = TreeMapeoFalso()
        edicion_confirmada = False

        def _apply_edit(self):
            self.edicion_confirmada = True

    editor = EditorFalso()

    resultado = InlineKVEditor.to_dict(editor)

    assert editor.edicion_confirmada is True
    assert resultado == {"Importe": "F"}
