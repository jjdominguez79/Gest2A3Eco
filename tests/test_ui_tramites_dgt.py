from datetime import datetime
from pathlib import Path

from views.ui_tramites_dgt import UITramitesDgt
from services.tramites_dgt_documentos import (
    FILTROS_ARCHIVO_DGT,
    MIME_POR_EXTENSION_DGT,
    ROLES_DOCUMENTO_DGT,
    TIPOS_DOCUMENTO_DGT,
    etiqueta_rol_documento,
    etiqueta_tipo_documento,
    rol_desde_etiqueta,
    tipo_desde_etiqueta,
)


def test_dependencias_para_fechas_de_documentos_estan_disponibles(tmp_path: Path):
    documento = tmp_path / "contrato.pdf"
    documento.write_bytes(b"%PDF-1.4")

    fecha = datetime.fromtimestamp(documento.stat().st_mtime).isoformat()

    assert UITramitesDgt._formatear_fecha(fecha)


def test_mapeo_de_etiquetas_a_roles():
    assert rol_desde_etiqueta("Expediente / Gestoría") == "gestor"
    assert rol_desde_etiqueta("Comprador") == "comprador"
    assert rol_desde_etiqueta("Vendedor") == "vendedor"
    assert tuple(ROLES_DOCUMENTO_DGT) == ("gestor", "comprador", "vendedor")


def test_catalogo_y_seleccion_de_modelo_620():
    assert tipo_desde_etiqueta("Modelo 620 presentado") == "modelo_620"
    assert TIPOS_DOCUMENTO_DGT["otro"] == "Otro documento"
    assert len(TIPOS_DOCUMENTO_DGT) >= 10


def test_presentacion_con_fallback_para_valores_historicos():
    assert etiqueta_rol_documento("gestor") == "Expediente / Gestoría"
    assert etiqueta_tipo_documento("modelo_620") == "Modelo 620 presentado"
    assert etiqueta_tipo_documento("tipo libre antiguo") == "tipo libre antiguo"
    assert etiqueta_rol_documento("rol_antiguo") == "rol_antiguo"


def test_formatos_ofrecidos_coinciden_con_los_admitidos():
    assert set(MIME_POR_EXTENSION_DGT) == {".pdf", ".jpg", ".jpeg", ".png"}
    patrones = " ".join(pattern for _label, pattern in FILTROS_ARCHIVO_DGT).lower()
    assert all(f"*{extension}" in patrones for extension in MIME_POR_EXTENSION_DGT)
    assert ".doc" not in patrones
