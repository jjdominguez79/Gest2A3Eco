import subprocess
import sys


def test_app_controller_no_carga_modulos_pesados_antes_del_login():
    codigo = (
        "import sys; "
        "import controllers.app_controller; "
        "prohibidos = ["
        "'pandas', 'views.ui_procesos', 'views.ui_comunicaciones', "
        "'views.ui_facturas_emitidas', 'views.ui_ocr_facturas'"
        "]; "
        "cargados = [nombre for nombre in prohibidos if nombre in sys.modules]; "
        "assert not cargados, cargados"
    )

    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert resultado.returncode == 0, resultado.stderr or resultado.stdout
