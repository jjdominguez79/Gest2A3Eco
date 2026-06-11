from controllers.factura_dialog_controller import FacturaDialogController
from models.gestor_sqlite import GestorSQLite


class _ViewStub:
    def __init__(self):
        self.values = []
        self.selected = ""
        self.nif = ""
        self.nombre = ""
        self.subcuenta = ""
        self.tipo_operacion = ""
        self.modelo_fiscal = ""
        self.warning = None

    def set_terceros(self, values):
        self.values = list(values)

    def get_selected_tercero_display(self):
        return self.selected

    def set_tercero_display(self, label):
        self.selected = label

    def set_nif(self, value):
        self.nif = value

    def set_nombre(self, value):
        self.nombre = value

    def set_subcuenta(self, value):
        self.subcuenta = value

    def set_tipo_operacion(self, value):
        self.tipo_operacion = value

    def set_modelo_fiscal(self, value):
        self.modelo_fiscal = value

    def set_subcuenta_warning(self, message):
        self.warning = message


def _make_gestor(tmp_path):
    g = GestorSQLite(tmp_path / "factura-dialog.db")
    g.upsert_empresa(
        {
            "codigo": "E00570",
            "ejercicio": 2026,
            "nombre": "Empresa Test",
            "digitos_plan": 8,
            "activo": 1,
        }
    )
    return g


def test_carga_subcuenta_cliente_desde_maestro_sin_configuracion(tmp_path):
    gestor = _make_gestor(tmp_path)
    gestor.upsert_maestro_subcuenta(
        {
            "codigo_empresa": "E00570",
            "subcuenta": "43000001",
            "nombre_subcuenta": "Cliente Solo Maestro",
            "tipo_subcuenta": "cliente",
            "nif_snapshot": "12345678A",
            "activo": 1,
            "origen": "manual",
            "creado_en_gest2a3eco": 1,
        }
    )
    view = _ViewStub()
    controller = FacturaDialogController(
        gestor,
        "E00570",
        2026,
        8,
        {"id": None, "subcuenta_cliente": "", "nif": ""},
        view,
    )

    controller.load_terceros()

    assert any("43000001" in label for label in view.values)
    view.selected = view.values[0]
    controller.on_tercero_selected()
    assert view.subcuenta == "43000001"
    assert view.nif == "12345678A"
    assert view.tipo_operacion == ""
    assert view.modelo_fiscal == ""
    assert "Puede continuar" in view.warning
