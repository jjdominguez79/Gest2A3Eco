import json

import pytest

from release_utils import (
    build_download_url,
    build_installer_name,
    build_release_metadata,
    build_version_manifest,
    compare_versions,
    is_valid_semver,
    read_app_version,
    read_setup_version,
    update_app_version_file,
    update_setup_version_file,
    validate_release_state,
    write_json,
)


def test_is_valid_semver_accepts_strict_xyz() -> None:
    assert is_valid_semver("1.2.3") is True
    assert is_valid_semver("0.0.1") is True


@pytest.mark.parametrize("value", ["v1.2.3", "V1.2.3", "1.2", "1.2.3.4", "01.2.3"])
def test_is_valid_semver_rejects_invalid_values(value: str) -> None:
    assert is_valid_semver(value) is False


def test_compare_versions_orders_semver() -> None:
    assert compare_versions("1.2.1", "1.2.2") == -1
    assert compare_versions("1.2.2", "1.2.2") == 0
    assert compare_versions("2.0.0", "1.9.9") == 1


def test_read_app_version(tmp_path) -> None:
    path = tmp_path / "app_version.py"
    path.write_text('APP_VERSION = "1.2.1"\nUPDATE_CHECK_URL = "x"\n', encoding="utf-8")
    assert read_app_version(path) == "1.2.1"


def test_read_setup_version(tmp_path) -> None:
    path = tmp_path / "setup.iss"
    path.write_text('#define MyAppVersion   "1.2.1"\n', encoding="utf-8")
    assert read_setup_version(path) == "1.2.1"


def test_update_app_version_file(tmp_path) -> None:
    path = tmp_path / "app_version.py"
    path.write_text('APP_VERSION = "1.2.1"\nUPDATE_CHECK_URL = "x"\n', encoding="utf-8")
    update_app_version_file(path, "1.2.2")
    assert 'APP_VERSION = "1.2.2"' in path.read_text(encoding="utf-8")
    assert 'UPDATE_CHECK_URL = "x"' in path.read_text(encoding="utf-8")


def test_update_setup_version_file(tmp_path) -> None:
    path = tmp_path / "setup.iss"
    path.write_text('#define MyAppVersion   "1.2.1"\n#define MyAppId "{{GUID}}"\n', encoding="utf-8")
    update_setup_version_file(path, "1.2.2")
    content = path.read_text(encoding="utf-8")
    assert '#define MyAppVersion   "1.2.2"' in content
    assert '#define MyAppId "{{GUID}}"' in content


def test_build_download_url() -> None:
    assert (
        build_download_url("jjdominguez79/Gest2A3Eco", "1.2.2")
        == "https://github.com/jjdominguez79/Gest2A3Eco/releases/download/v1.2.2/Setup_Gest2A3Eco_1.2.2.exe"
    )


def test_build_version_manifest_preserves_previous_minimum_when_not_forced() -> None:
    manifest = build_version_manifest(
        version="1.2.2",
        changelog="Cambios de prueba",
        force_update=False,
        repo="jjdominguez79/Gest2A3Eco",
        previous_minimum_version="1.2.0",
    )
    assert manifest == {
        "latest_version": "1.2.2",
        "minimum_required_version": "1.2.0",
        "download_url": "https://github.com/jjdominguez79/Gest2A3Eco/releases/download/v1.2.2/Setup_Gest2A3Eco_1.2.2.exe",
        "changelog": "Cambios de prueba",
        "force_update": False,
    }


def test_build_version_manifest_forces_minimum_to_new_version() -> None:
    manifest = build_version_manifest(
        version="1.2.2",
        changelog="Cambios de prueba",
        force_update=True,
        repo="jjdominguez79/Gest2A3Eco",
        previous_minimum_version="1.2.0",
    )
    assert manifest["minimum_required_version"] == "1.2.2"
    assert manifest["force_update"] is True


def test_build_release_metadata() -> None:
    assert build_release_metadata("1.2.2", "Linea 1\nLinea 2", True) == {
        "version": "1.2.2",
        "tag": "v1.2.2",
        "changelog": "Linea 1\nLinea 2",
        "force_update": True,
    }


def test_validate_release_state(tmp_path) -> None:
    app_version_file = tmp_path / "app_version.py"
    setup_file = tmp_path / "setup.iss"
    metadata_file = tmp_path / "release_metadata.json"

    app_version_file.write_text('APP_VERSION = "1.2.2"\n', encoding="utf-8")
    setup_file.write_text('#define MyAppVersion   "1.2.2"\n', encoding="utf-8")
    write_json(
        metadata_file,
        build_release_metadata("1.2.2", "Cambios importantes", False),
    )

    state = validate_release_state(
        tag="v1.2.2",
        repo="jjdominguez79/Gest2A3Eco",
        app_version_file=app_version_file,
        setup_file=setup_file,
        metadata_file=metadata_file,
    )

    assert state["version"] == "1.2.2"
    assert state["tag"] == "v1.2.2"
    assert state["installer_name"] == build_installer_name("1.2.2")
    assert state["download_url"] == build_download_url("jjdominguez79/Gest2A3Eco", "1.2.2")


def test_write_json_creates_valid_json(tmp_path) -> None:
    payload = build_release_metadata("1.2.2", "Cambios", True)
    path = tmp_path / "out" / "release_metadata.json"
    write_json(path, payload)
    assert json.loads(path.read_text(encoding="utf-8")) == payload
