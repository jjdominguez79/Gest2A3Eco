from datetime import datetime
from pathlib import Path

from views.ui_tramites_dgt import UITramitesDgt


def test_dependencias_para_fechas_de_documentos_estan_disponibles(tmp_path: Path):
    documento = tmp_path / "contrato.pdf"
    documento.write_bytes(b"%PDF-1.4")

    fecha = datetime.fromtimestamp(documento.stat().st_mtime).isoformat()

    assert UITramitesDgt._formatear_fecha(fecha)
