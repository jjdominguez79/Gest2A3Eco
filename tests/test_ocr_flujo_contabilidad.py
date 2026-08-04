from pathlib import Path
from types import SimpleNamespace

from controllers.ui_contabilidad_controller import UIContabilidadController
from controllers.ui_ocr_facturas_controller import UIOcrFacturasController


ROOT = Path(__file__).resolve().parents[1]


def test_ocr_no_expone_generacion_de_suenlace():
    assert not hasattr(UIOcrFacturasController, "generar_suenlace_seleccionadas")
    for ruta in (
        ROOT / "views" / "ui_ocr_facturas.py",
        ROOT / "views" / "ui_facturas_recibidas_ocr.py",
    ):
        contenido = ruta.read_text(encoding="utf-8").lower()
        assert "generar suenlace" not in contenido


def test_contabilidad_conserva_la_exportacion_de_suenlace():
    assert callable(getattr(UIContabilidadController, "exportar_suenlace", None))
    contenido = (ROOT / "views" / "ui_contabilidad.py").read_text(encoding="utf-8").lower()
    assert "exportar suenlace.dat" in contenido
    assert "capturar nº asiento de a3" in contenido


def test_captura_asiento_recibida_desde_a3(monkeypatch):
    class Gestor:
        def get_factura_recibida_doc(self, _doc_id):
            return {
                "id": "doc-1", "estado_contable": "contabilizada",
                "numero_factura": "F-24", "fecha_asiento": "2026-05-15",
                "descripcion": "Factura F-24",
            }

        def actualizar_numero_asiento_factura_recibida(
            self, codigo, documento_id, asiento,
        ):
            self.actualizado = (codigo, documento_id, asiento)
            return True

    class View:
        def get_selected_received_ids(self):
            return ["doc-1"]

        def show_info(self, _title, message):
            self.message = message

        def show_warning(self, *_args):
            raise AssertionError("No se esperaba aviso")

    gestor, view = Gestor(), View()
    controller = UIContabilidadController(gestor, "E00570", 2026, view)
    monkeypatch.setattr(
        "controllers.ui_contabilidad_controller.leer_numero_asiento_desde_a3",
        lambda codigo, ejercicio, numero, descripcion, mes=None: "05/00042",
    )
    monkeypatch.setattr(controller, "refresh", lambda select_id=None: None)

    controller.capturar_numero_asiento_desde_a3()

    assert gestor.actualizado == ("E00570", "doc-1", "05/00042")
    assert "05/00042" in view.message


def test_generar_asiento_no_marca_la_factura_como_contabilizada(monkeypatch):
    doc = {
        "id": "doc-1", "codigo_empresa": "E00570", "ejercicio": 2026,
        "estado_contable": "pendiente_contabilizar", "numero_factura": "F-24",
        "fecha_factura": "2026-05-15", "total": 121.0,
    }

    class Gestor:
        def get_factura_recibida_doc(self, _doc_id):
            return doc

        def get_empresa(self, *_args):
            return {"digitos_plan": 8}

        def upsert_asiento_contable(self, asiento):
            self.asiento = asiento

        def upsert_factura_recibida_doc(self, factura):
            self.factura = dict(factura)

    class View:
        def get_numero_asiento(self):
            return ""

        def get_fecha_asiento(self):
            return "2026-05-15"

        def show_info(self, *_args):
            pass

    gestor, view = Gestor(), View()
    controller = UIContabilidadController(gestor, "E00570", 2026, view)
    controller._selected_id = "doc-1"
    monkeypatch.setattr(controller, "_resolve_plantilla", lambda: {})
    monkeypatch.setattr(
        "controllers.ui_contabilidad_controller.generar_asiento_recibida",
        lambda *_args: [SimpleNamespace(
            fecha="2026-05-15", subcuenta="40000001", dh="H",
            importe=121.0, concepto="Factura F-24",
        )],
    )
    monkeypatch.setattr(controller, "refresh", lambda **_kwargs: None)

    controller.generar_asiento()

    assert gestor.factura["estado_contable"] == "pendiente_contabilizar"
