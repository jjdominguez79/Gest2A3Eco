"""Evita publicar otra vez un visor web sin su motor PDF local."""

import json
import re
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "gestinem_app"


def test_visor_pdf_carga_motor_worker_y_fuentes_desde_la_app():
    index = (APP / "web/index.html").read_text(encoding="utf-8")
    motor = re.search(r"import\('\./(pdfjs/[^']+/build/pdf.min.mjs)'\)", index)
    assert motor, "Falta inicializar el motor web requerido por pdfx"
    motor_path = APP / "web" / motor.group(1)
    assert motor_path.is_file()
    recursos = motor_path.parent.parent
    assert (recursos / "build/pdf.worker.min.mjs").is_file()
    assert list((recursos / "cmaps").glob("*.bcmap"))
    assert list((recursos / "standard_fonts").glob("*"))
    assert (recursos / "LICENSE").is_file()
    assert "globalThis.pdfjsLib =" in index
    assert "isEvalSupported: false" in index
    assert "standardFontDataUrl:" in index
    assert "cMapPacked: true" in index


def test_arranque_espera_motor_pdf_y_conserva_actualizacion_de_flutter():
    bootstrap = (APP / "web/flutter_bootstrap.js").read_text(encoding="utf-8")
    assert bootstrap.index("await globalThis.gestinemPdfJsReady") < bootstrap.index(
        "_flutter.loader.load("
    )
    assert "serviceWorkerVersion: {{flutter_service_worker_version}}" in bootstrap
    index = (APP / "web/index.html").read_text(encoding="utf-8")
    assert 'src="flutter_bootstrap.js?v=' in index


def test_publicacion_no_reutiliza_arranque_y_codigo_antiguos_por_una_hora():
    config = json.loads((APP / "firebase.json").read_text(encoding="utf-8"))
    headers = {
        item["source"]: {h["key"]: h["value"] for h in item["headers"]}
        for item in config["hosting"]["headers"]
    }
    for recurso in ("/index.html", "/flutter_bootstrap.js", "/main.dart.js"):
        assert "no-cache" in headers[recurso]["Cache-Control"]
