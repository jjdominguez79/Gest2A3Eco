from pathlib import Path

from backend.api import config


def test_settings_uses_flutter_pubspec_as_release_source(
    tmp_path: Path,
    monkeypatch,
):
    pubspec = tmp_path / "pubspec.yaml"
    pubspec.write_text("name: gestinem\nversion: 2.3.4+57\n", encoding="utf-8")
    monkeypatch.setattr(config, "FLUTTER_PUBSPEC_PATH", pubspec)
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql://example.test/database")
    monkeypatch.delenv("MESSAGING_LATEST_APP_VERSION", raising=False)
    monkeypatch.delenv("MESSAGING_LATEST_APP_BUILD", raising=False)

    settings = config.get_settings()

    assert settings.messaging_latest_app_version == "2.3.4"
    assert settings.messaging_latest_app_build == 57


def test_settings_allows_temporary_release_override(tmp_path: Path, monkeypatch):
    pubspec = tmp_path / "pubspec.yaml"
    pubspec.write_text("version: 2.3.4+57\n", encoding="utf-8")
    monkeypatch.setattr(config, "FLUTTER_PUBSPEC_PATH", pubspec)
    monkeypatch.setenv("DGT_DATABASE_URL", "postgresql://example.test/database")
    monkeypatch.setenv("MESSAGING_LATEST_APP_VERSION", "2.3.5")
    monkeypatch.setenv("MESSAGING_LATEST_APP_BUILD", "58")

    settings = config.get_settings()

    assert settings.messaging_latest_app_version == "2.3.5"
    assert settings.messaging_latest_app_build == 58
