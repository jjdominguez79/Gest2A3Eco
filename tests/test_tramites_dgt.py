from pathlib import Path

from models.gestor_sqlite import GestorSQLite
from services.tramites_dgt_service import TramitesDgtService, get_protocol_url_from_argv


def _tables(gestor: GestorSQLite) -> set[str]:
    rows = gestor.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def _columns(gestor: GestorSQLite, table: str) -> set[str]:
    rows = gestor.conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def test_tramites_dgt_schema(tmp_path: Path):
    gestor = GestorSQLite(tmp_path / "dgt.db")
    tables = _tables(gestor)
    assert "dgt_expedientes" in tables
    assert "dgt_documentos_generados" in tables
    assert "usuarios_permisos_globales" in tables
    for col in ("referencia", "estado", "vendedor_token_hash", "comprador_token_hash", "firma_provider"):
        assert col in _columns(gestor, "dgt_expedientes")


def test_crear_validar_y_generar_documentos(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("services.tramites_dgt_service.get_app_data_dir", lambda: tmp_path)
    gestor = GestorSQLite(tmp_path / "dgt_service.db")
    service = TramitesDgtService(gestor)
    expediente_id = service.crear_expediente_minimo(
        {
            "vendedor_nombre": "Vendedor Demo",
            "comprador_nombre": "Comprador Demo",
            "vehiculo_matricula": "1234 ABC",
            "precio_venta": "1200,50",
        }
    )
    links = service.regenerar_links(expediente_id)
    vendedor_token = links["vendedor"].split("token=", 1)[1]
    expediente = service.get_expediente(expediente_id)
    assert expediente["referencia"].startswith("DGT-")
    assert expediente["vehiculo_matricula"] == "1234ABC"
    assert expediente["vendedor_token_hash"]
    assert expediente["comprador_token_hash"]

    service.completar_desde_link(
        expediente["referencia"],
        "vendedor",
        vendedor_token,
        {
            "nombre": "Vendedor Demo",
            "nif": "00000000T",
            "direccion": "Calle Mayor 1",
            "vehiculo_matricula": "1234 ABC",
            "precio_venta": "1200,50",
        },
    )
    service.guardar_datos_parte(
        expediente_id,
        "comprador",
        {
            "nombre": "Comprador Demo",
            "nif": "00000001R",
            "direccion": "Calle Menor 2",
        },
    )
    adjunto = tmp_path / "dni.pdf"
    adjunto.write_bytes(b"%PDF-1.4 demo")
    doc = service.adjuntar_documento(expediente_id, "comprador", str(adjunto), tipo="dni")
    assert doc["sha256"]

    service.validar_expediente(expediente_id)
    docs = service.generar_documentos(expediente_id)
    assert {doc["tipo_documento"] for doc in docs} == {
        "contrato_compraventa",
        "mandato_dgt_comprador",
        "mandato_dgt_vendedor",
    }
    for doc in docs:
        assert Path(doc["ruta_txt"]).exists()
        if doc.get("ruta_docx"):
            assert Path(doc["ruta_docx"]).exists()

    paquete = service.preparar_paquete_firma(expediente_id, provider="box_sign")
    assert paquete["provider"] == "box_sign"
    assert len(paquete["documentos"]) == 3
    assert service.get_expediente(expediente_id)["firma_estado"] == "preparado"


def test_rechaza_token_dgt_incorrecto(tmp_path: Path):
    gestor = GestorSQLite(tmp_path / "dgt_token.db")
    service = TramitesDgtService(gestor)
    expediente_id = service.crear_expediente_minimo({"vendedor_nombre": "A", "comprador_nombre": "B"})
    expediente = service.get_expediente(expediente_id)
    try:
        service.verificar_token(expediente["referencia"], "vendedor", "token-malo")
    except PermissionError:
        pass
    else:
        raise AssertionError("El token incorrecto no fue rechazado")


def test_parsea_link_seguro_y_completa_comprador(tmp_path: Path):
    gestor = GestorSQLite(tmp_path / "dgt_link.db")
    service = TramitesDgtService(gestor)
    expediente_id = service.crear_expediente_minimo({"vendedor_nombre": "A", "comprador_nombre": "B"})
    link = service.regenerar_links(expediente_id)["comprador"]
    parsed = service.parse_link_seguro(link)
    assert parsed["rol"] == "comprador"
    assert parsed["referencia"].startswith("DGT-")
    assert parsed["token"]

    service.completar_desde_link(
        parsed["referencia"],
        parsed["rol"],
        parsed["token"],
        {"nombre": "Comprador Link", "nif": "00000001R", "direccion": "Calle Link"},
    )
    expediente = service.get_expediente(expediente_id)
    assert expediente["comprador_nombre"] == "Comprador Link"
    assert expediente["comprador_payload"]["nif"] == "00000001R"


def test_plantillas_dgt_editables_en_carpeta_configurada(tmp_path: Path, monkeypatch):
    templates_dir = tmp_path / "plantillas_usuario"
    monkeypatch.setattr("services.tramites_dgt_service.get_word_templates_dir", lambda: str(templates_dir))
    gestor = GestorSQLite(tmp_path / "dgt_templates.db")
    service = TramitesDgtService(gestor)

    before = service.listar_plantillas_editables()
    assert all(str(templates_dir / "tramites_dgt") in item["path"] for item in before)
    assert not any(item["exists"] for item in before)

    created = service.ensure_plantillas_editables()
    assert len(created) == 3
    after = service.listar_plantillas_editables()
    assert all(item["exists"] for item in after)
    for item in after:
        assert Path(item["path"]).exists()


def test_detecta_url_protocolo_dgt_en_argv():
    url = "gest2a3eco://tramites-dgt/vendedor/DGT-2026-0001?token=abc"
    assert get_protocol_url_from_argv(["Gest2A3Eco.exe", url]) == url
    assert get_protocol_url_from_argv(["Gest2A3Eco.exe", "--otro"]) == ""
