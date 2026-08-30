from pathlib import Path

from backend.api import config


def test_settings_uses_flutter_pubspec_as_release_source(
    tmp_path: Path,
    monkeypatch,
):
    pubspec = tmp_path / "pubspec.yaml"
    pubspec.write_text("name: gestinem\nversion: 2.3.4+57\n", encoding="utf-8")
    monkeypatch.setattr(config, "FLUTTER_PUBSPEC_PATH", pubspec)
    monkeypatch.setenv("BACKEND_DATABASE_URL", "postgresql://example.test/database")
    monkeypatch.delenv("MESSAGING_LATEST_APP_VERSION", raising=False)
    monkeypatch.delenv("MESSAGING_LATEST_APP_BUILD", raising=False)

    settings = config.get_settings()

    assert settings.messaging_latest_app_version == "2.3.4"
    assert settings.messaging_latest_app_build == 57


def test_settings_allows_temporary_release_override(tmp_path: Path, monkeypatch):
    pubspec = tmp_path / "pubspec.yaml"
    pubspec.write_text("version: 2.3.4+57\n", encoding="utf-8")
    monkeypatch.setattr(config, "FLUTTER_PUBSPEC_PATH", pubspec)
    monkeypatch.setenv("BACKEND_DATABASE_URL", "postgresql://example.test/database")
    monkeypatch.setenv("MESSAGING_LATEST_APP_VERSION", "2.3.5")
    monkeypatch.setenv("MESSAGING_LATEST_APP_BUILD", "58")

    settings = config.get_settings()

    assert settings.messaging_latest_app_version == "2.3.5"
    assert settings.messaging_latest_app_build == 58


def test_settings_prioritizes_backend_environment_names(monkeypatch):
    monkeypatch.setenv("BACKEND_DATABASE_URL", "postgresql://new/database")
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql://legacy/database")
    monkeypatch.setenv("BACKEND_INTERNAL_API_KEY", "new-key")
    monkeypatch.setenv("DGT_INTERNAL_API_KEY", "legacy-key")
    monkeypatch.setenv("BACKEND_PUBLIC_BASE_URL", "https://backend.example.test/")
    monkeypatch.delenv("DGT_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("MESSAGING_PUBLIC_BASE_URL", raising=False)

    settings = config.get_settings()

    assert settings.database_url == "postgresql://new/database"
    assert settings.internal_api_key == "new-key"
    assert settings.public_base_url == "https://backend.example.test"
    assert settings.messaging_public_base_url == "https://backend.example.test"


def test_settings_accepts_legacy_dgt_core_names_during_migration(monkeypatch):
    monkeypatch.delenv("BACKEND_DATABASE_URL", raising=False)
    monkeypatch.delenv("BACKEND_INTERNAL_API_KEY", raising=False)
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql://legacy/database")
    monkeypatch.setenv("DGT_INTERNAL_API_KEY", "legacy-key")
    monkeypatch.setenv("DGT_PUBLIC_BASE_URL", "https://legacy.example.test/")
    monkeypatch.delenv("BACKEND_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("MESSAGING_PUBLIC_BASE_URL", raising=False)

    settings = config.get_settings()

    assert settings.database_url == "postgresql://legacy/database"
    assert settings.internal_api_key == "legacy-key"
    assert settings.public_base_url == "https://legacy.example.test"
    assert settings.messaging_public_base_url == "https://legacy.example.test"
