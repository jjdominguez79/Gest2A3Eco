import json

from utils import utilidades


def test_get_user_config_path_usa_localappdata_en_frozen(monkeypatch, tmp_path):
    install_dir = tmp_path / "install"
    localappdata = tmp_path / "LocalAppData"
    install_dir.mkdir()

    monkeypatch.setattr(utilidades.sys, "frozen", True, raising=False)
    monkeypatch.setattr(utilidades.sys, "executable", str(install_dir / "Gest2A3Eco.exe"))
    monkeypatch.setenv("LOCALAPPDATA", str(localappdata))

    cfg_path = utilidades.get_user_config_path()

    assert cfg_path == localappdata / "Gestinem" / "Gest2A3Eco" / "config.local.json"


def test_get_packaged_resource_path_usa_meipass_en_frozen(monkeypatch, tmp_path):
    internal_dir = tmp_path / "install" / "_internal"
    internal_dir.mkdir(parents=True)

    monkeypatch.setattr(utilidades.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        utilidades.sys, "_MEIPASS", str(internal_dir), raising=False
    )

    assert (
        utilidades.get_packaged_resource_path("logo.png")
        == internal_dir / "logo.png"
    )


def test_load_app_config_migra_legacy_config_a_localappdata(monkeypatch, tmp_path):
    install_dir = tmp_path / "install"
    localappdata = tmp_path / "LocalAppData"
    install_dir.mkdir()
    legacy_path = install_dir / "config.local.json"
    legacy_data = {
        "db_path": r"\\Servidor\Compartida\Gest2A3Eco\gest2a3eco.db",
        "word_templates_dir": r"\\Servidor\Compartida\Gest2A3Eco\plantillas",
    }
    legacy_path.write_text(json.dumps(legacy_data), encoding="utf-8")

    monkeypatch.setattr(utilidades.sys, "frozen", True, raising=False)
    monkeypatch.setattr(utilidades.sys, "executable", str(install_dir / "Gest2A3Eco.exe"))
    monkeypatch.setenv("LOCALAPPDATA", str(localappdata))

    cfg = utilidades.load_app_config()
    migrated_path = localappdata / "Gestinem" / "Gest2A3Eco" / "config.local.json"

    assert migrated_path.exists()
    assert cfg["db_path"] == legacy_data["db_path"]
    assert cfg["last_db_path"] == legacy_data["db_path"]
    assert cfg["word_templates_dir"] == legacy_data["word_templates_dir"]


def test_validate_sqlite_db_path_crea_base_si_la_carpeta_existe(tmp_path):
    db_path = tmp_path / "datos" / "gest2a3eco.db"
    db_path.parent.mkdir()

    validated = utilidades.validate_sqlite_db_path(str(db_path))

    assert validated == str(db_path)
    assert db_path.exists()


def test_validate_sqlite_db_path_falla_si_no_existe_carpeta(tmp_path):
    db_path = tmp_path / "sin-carpeta" / "gest2a3eco.db"

    try:
        utilidades.validate_sqlite_db_path(str(db_path))
    except FileNotFoundError as exc:
        assert str(db_path.parent) in str(exc)
    else:
        raise AssertionError("Se esperaba FileNotFoundError")


def test_load_app_config_admite_configuracion_postgres(monkeypatch, tmp_path):
    monkeypatch.setattr(utilidades, "get_user_config_path", lambda: tmp_path / "config.local.json")
    monkeypatch.setattr(utilidades, "_legacy_config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(utilidades, "_legacy_local_config_path", lambda: tmp_path / "legacy.local.json")
    monkeypatch.setattr(utilidades, "_config_example_path", lambda: tmp_path / "config.example.json")
    monkeypatch.setenv("GEST2A3ECO_DATABASE_ENGINE", "postgres")
    monkeypatch.setenv("GEST2A3ECO_POSTGRES_DSN", "postgresql://gestor@192.168.0.19:5432/gest2a3eco")

    cfg = utilidades.load_app_config()

    assert cfg["database_engine"] == "postgres"
    assert cfg["postgres_dsn"].startswith("postgresql://")


def test_load_app_config_usa_postgres_por_defecto(monkeypatch, tmp_path):
    monkeypatch.setattr(utilidades, "get_user_config_path", lambda: tmp_path / "config.local.json")
    monkeypatch.setattr(utilidades, "_legacy_config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(utilidades, "_legacy_local_config_path", lambda: tmp_path / "legacy.local.json")
    monkeypatch.setattr(utilidades, "_config_example_path", lambda: tmp_path / "config.example.json")

    assert utilidades.load_app_config()["database_engine"] == "postgres"
