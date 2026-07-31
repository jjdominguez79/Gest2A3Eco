from pathlib import Path

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
