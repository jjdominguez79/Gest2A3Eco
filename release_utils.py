from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
APP_VERSION_RE = re.compile(
    r'^(?P<prefix>\s*APP_VERSION\s*=\s*")(?P<version>\d+\.\d+\.\d+)(?P<suffix>".*)$',
    re.MULTILINE,
)
SETUP_VERSION_RE = re.compile(
    r'^(?P<prefix>\s*#define\s+MyAppVersion\s+")(?P<version>\d+\.\d+\.\d+)(?P<suffix>".*)$',
    re.MULTILINE,
)


def is_valid_semver(version: str) -> bool:
    return bool(SEMVER_RE.fullmatch(version))


def parse_semver(version: str) -> tuple[int, int, int]:
    if not is_valid_semver(version):
        raise ValueError(f"Version semantica invalida: {version!r}")
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def compare_versions(current: str, target: str) -> int:
    current_parts = parse_semver(current)
    target_parts = parse_semver(target)
    if current_parts == target_parts:
        return 0
    return -1 if current_parts < target_parts else 1


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def read_app_version(path: Path) -> str:
    match = APP_VERSION_RE.search(_read_text(path))
    if not match:
        raise ValueError(f"No se encontro APP_VERSION en {path}")
    return match.group("version")


def read_setup_version(path: Path) -> str:
    match = SETUP_VERSION_RE.search(_read_text(path))
    if not match:
        raise ValueError(f'No se encontro #define MyAppVersion en {path}')
    return match.group("version")


def update_app_version_text(content: str, version: str) -> str:
    parse_semver(version)
    if not APP_VERSION_RE.search(content):
        raise ValueError("No se encontro APP_VERSION en el contenido.")
    return APP_VERSION_RE.sub(rf"\g<prefix>{version}\g<suffix>", content, count=1)


def update_setup_version_text(content: str, version: str) -> str:
    parse_semver(version)
    if not SETUP_VERSION_RE.search(content):
        raise ValueError("No se encontro #define MyAppVersion en el contenido.")
    return SETUP_VERSION_RE.sub(rf"\g<prefix>{version}\g<suffix>", content, count=1)


def update_app_version_file(path: Path, version: str) -> None:
    _write_text(path, update_app_version_text(_read_text(path), version))


def update_setup_version_file(path: Path, version: str) -> None:
    _write_text(path, update_setup_version_text(_read_text(path), version))


def build_tag(version: str) -> str:
    parse_semver(version)
    return f"v{version}"


def build_installer_name(version: str) -> str:
    parse_semver(version)
    return f"Setup_Gest2A3Eco_{version}.exe"


def build_release_title(version: str) -> str:
    parse_semver(version)
    return f"Gest2A3Eco {version}"


def build_download_url(repo: str, version: str) -> str:
    return f"https://github.com/{repo}/releases/download/{build_tag(version)}/{build_installer_name(version)}"


def build_release_notes(version: str, changelog: str) -> str:
    parse_semver(version)
    clean = changelog.strip()
    return (
        f"# Gest2A3Eco {version}\n\n"
        f"## Cambios\n\n"
        f"{clean}\n\n"
        f"## Instalacion\n\n"
        f"Esta version se distribuira automaticamente mediante el actualizador de Gest2A3Eco.\n"
    )


def build_release_metadata(version: str, changelog: str, force_update: bool) -> dict[str, Any]:
    return {
        "version": version,
        "tag": build_tag(version),
        "changelog": changelog.strip(),
        "force_update": bool(force_update),
    }


def build_version_manifest(
    version: str,
    changelog: str,
    force_update: bool,
    repo: str,
    previous_minimum_version: str | None = None,
) -> dict[str, Any]:
    parse_semver(version)
    if previous_minimum_version is not None:
        parse_semver(previous_minimum_version)

    minimum_required_version = version if force_update else (previous_minimum_version or version)
    return {
        "latest_version": version,
        "minimum_required_version": minimum_required_version,
        "download_url": build_download_url(repo, version),
        "changelog": changelog.strip(),
        "force_update": bool(force_update),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(_read_text(path))
    if not isinstance(data, dict):
        raise ValueError(f"Se esperaba un objeto JSON en {path}")
    return data


def validate_tag(tag: str) -> str:
    if not tag.startswith("v"):
        raise ValueError(f"El tag debe empezar por 'v' minuscula: {tag}")
    if tag != tag.lower():
        raise ValueError(f"El tag contiene mayusculas y no es valido: {tag}")
    version = tag[1:]
    parse_semver(version)
    return version


def validate_release_state(
    tag: str,
    repo: str,
    app_version_file: Path,
    setup_file: Path,
    metadata_file: Path,
) -> dict[str, Any]:
    version_from_tag = validate_tag(tag)
    version_from_app = read_app_version(app_version_file)
    version_from_setup = read_setup_version(setup_file)
    metadata = read_json(metadata_file)
    version_from_metadata = str(metadata.get("version", ""))
    tag_from_metadata = str(metadata.get("tag", ""))

    if version_from_app != version_from_tag:
        raise ValueError(
            f"La version de {app_version_file} ({version_from_app}) no coincide con el tag {tag}."
        )
    if version_from_setup != version_from_tag:
        raise ValueError(
            f"La version de {setup_file} ({version_from_setup}) no coincide con el tag {tag}."
        )
    if version_from_metadata != version_from_tag:
        raise ValueError(
            f"La version de {metadata_file} ({version_from_metadata}) no coincide con el tag {tag}."
        )
    if tag_from_metadata != tag:
        raise ValueError(f"El tag de {metadata_file} ({tag_from_metadata}) no coincide con {tag}.")

    force_update = bool(metadata.get("force_update", False))
    changelog = str(metadata.get("changelog", "")).strip()
    if not changelog:
        raise ValueError(f"El changelog de {metadata_file} no puede estar vacio.")

    return {
        "version": version_from_tag,
        "tag": tag,
        "installer_name": build_installer_name(version_from_tag),
        "download_url": build_download_url(repo, version_from_tag),
        "release_title": build_release_title(version_from_tag),
        "force_update": force_update,
        "changelog": changelog,
        "release_notes": build_release_notes(version_from_tag, changelog),
    }


def assert_http_available(url: str, timeout: float = 30.0) -> None:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", response.getcode())
            if int(status) != 200:
                raise ValueError(f"La URL {url} respondio con estado {status}.")
            return
    except urllib.error.HTTPError as exc:
        if exc.code == 405:
            request = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = getattr(response, "status", response.getcode())
                if int(status) != 200:
                    raise ValueError(f"La URL {url} respondio con estado {status}.")
                return
        raise


def _load_text_argument(text: str | None, text_file: Path | None) -> str:
    if text is not None and text_file is not None:
        raise ValueError("Usa solo uno de --text o --text-file.")
    if text_file is not None:
        return _read_text(text_file).strip()
    return (text or "").strip()


def _command_compare(args: argparse.Namespace) -> int:
    print(compare_versions(args.current, args.target))
    return 0


def _command_read_app_version(args: argparse.Namespace) -> int:
    print(read_app_version(Path(args.path)))
    return 0


def _command_read_setup_version(args: argparse.Namespace) -> int:
    print(read_setup_version(Path(args.path)))
    return 0


def _command_update_files(args: argparse.Namespace) -> int:
    update_app_version_file(Path(args.app_version_file), args.version)
    update_setup_version_file(Path(args.setup_file), args.version)
    return 0


def _command_write_release_metadata(args: argparse.Namespace) -> int:
    changelog = _load_text_argument(args.changelog, Path(args.changelog_file) if args.changelog_file else None)
    payload = build_release_metadata(args.version, changelog, args.force_update)
    write_json(Path(args.output), payload)
    return 0


def _command_write_version_json(args: argparse.Namespace) -> int:
    changelog = _load_text_argument(args.changelog, Path(args.changelog_file) if args.changelog_file else None)
    payload = build_version_manifest(
        version=args.version,
        changelog=changelog,
        force_update=args.force_update,
        repo=args.repo,
        previous_minimum_version=args.previous_minimum_version,
    )
    write_json(Path(args.output), payload)
    return 0


def _command_build_download_url(args: argparse.Namespace) -> int:
    print(build_download_url(args.repo, args.version))
    return 0


def _command_validate_release_state(args: argparse.Namespace) -> int:
    payload = validate_release_state(
        tag=args.tag,
        repo=args.repo,
        app_version_file=Path(args.app_version_file),
        setup_file=Path(args.setup_file),
        metadata_file=Path(args.metadata_file),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _command_assert_http_available(args: argparse.Namespace) -> int:
    assert_http_available(args.url, timeout=args.timeout)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Utilidades de publicacion de versiones.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    compare_parser = subparsers.add_parser("compare", help="Compara dos versiones semanticas.")
    compare_parser.add_argument("current")
    compare_parser.add_argument("target")
    compare_parser.set_defaults(func=_command_compare)

    read_app_parser = subparsers.add_parser("read-app-version", help="Lee APP_VERSION.")
    read_app_parser.add_argument("--path", default="app_version.py")
    read_app_parser.set_defaults(func=_command_read_app_version)

    read_setup_parser = subparsers.add_parser("read-setup-version", help="Lee MyAppVersion.")
    read_setup_parser.add_argument("--path", default="setup.iss")
    read_setup_parser.set_defaults(func=_command_read_setup_version)

    update_parser = subparsers.add_parser("update-files", help="Actualiza app_version.py y setup.iss.")
    update_parser.add_argument("--version", required=True)
    update_parser.add_argument("--app-version-file", default="app_version.py")
    update_parser.add_argument("--setup-file", default="setup.iss")
    update_parser.set_defaults(func=_command_update_files)

    metadata_parser = subparsers.add_parser(
        "write-release-metadata",
        help="Genera updates/release_metadata.json.",
    )
    metadata_parser.add_argument("--version", required=True)
    metadata_parser.add_argument("--output", default="updates/release_metadata.json")
    metadata_parser.add_argument("--changelog")
    metadata_parser.add_argument("--changelog-file")
    metadata_parser.add_argument("--force-update", action="store_true")
    metadata_parser.set_defaults(func=_command_write_release_metadata)

    version_json_parser = subparsers.add_parser(
        "write-version-json",
        help="Genera updates/version.json.",
    )
    version_json_parser.add_argument("--version", required=True)
    version_json_parser.add_argument("--repo", required=True)
    version_json_parser.add_argument("--output", default="updates/version.json")
    version_json_parser.add_argument("--changelog")
    version_json_parser.add_argument("--changelog-file")
    version_json_parser.add_argument("--force-update", action="store_true")
    version_json_parser.add_argument("--previous-minimum-version")
    version_json_parser.set_defaults(func=_command_write_version_json)

    url_parser = subparsers.add_parser("build-download-url", help="Construye la URL del asset.")
    url_parser.add_argument("--repo", required=True)
    url_parser.add_argument("--version", required=True)
    url_parser.set_defaults(func=_command_build_download_url)

    validate_parser = subparsers.add_parser(
        "validate-release-state",
        help="Valida el estado de una release a partir del tag y los archivos del repo.",
    )
    validate_parser.add_argument("--tag", required=True)
    validate_parser.add_argument("--repo", required=True)
    validate_parser.add_argument("--app-version-file", default="app_version.py")
    validate_parser.add_argument("--setup-file", default="setup.iss")
    validate_parser.add_argument("--metadata-file", default="updates/release_metadata.json")
    validate_parser.set_defaults(func=_command_validate_release_state)

    http_parser = subparsers.add_parser(
        "assert-http-available",
        help="Verifica que una URL publica responde correctamente.",
    )
    http_parser.add_argument("--url", required=True)
    http_parser.add_argument("--timeout", type=float, default=30.0)
    http_parser.set_defaults(func=_command_assert_http_available)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
