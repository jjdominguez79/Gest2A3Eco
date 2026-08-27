from models.gestor_base import SCHEMA, GestorBase
from utils.utilidades import _normalize_config


def test_esquema_no_crea_tablas_del_generador_documental_retirado():
    for tabla in (
        "plantillas_documentos",
        "intervinientes",
        "operaciones",
        "operacion_intervinientes",
        "documentos_generados",
        "documento_intervinientes",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {tabla}" not in SCHEMA


def test_gestor_no_expone_la_api_del_generador_documental_retirado():
    for metodo in (
        "listar_plantillas_documentos",
        "upsert_plantilla_documento",
        "listar_intervinientes",
        "listar_operaciones",
        "listar_documentos_generados",
        "upsert_documento_generado",
    ):
        assert not hasattr(GestorBase, metodo)


def test_configuracion_descarta_directorio_de_salida_legacy():
    config = _normalize_config({"documentos_output_dir": "C:/legacy"})

    assert "documentos_output_dir" not in config
