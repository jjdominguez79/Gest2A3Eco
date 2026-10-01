from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "gestinem_app"
TOOL = APP / "tool"


def _leer(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_lanzadores_ofrecen_las_mismas_plataformas() -> None:
    powershell = _leer(TOOL / "build_production.ps1")
    bash = _leer(TOOL / "build_production.sh")

    for plataforma in ("android", "apk", "web", "windows", "ios", "macos"):
        assert f"'{plataforma}'" in powershell
        assert plataforma in bash

    assert "web-deploy" not in powershell
    assert "web-deploy" not in bash
    assert not (TOOL / "deploy_firebase.ps1").exists()


def test_ambos_despliegues_web_incluyen_vapid_y_firebase() -> None:
    for script in ("build_production.ps1", "build_production.sh"):
        content = _leer(TOOL / script)
        assert "MESSAGING_VAPID_PUBLIC_KEY" in content
        assert "FIREBASE_WEB_VAPID_KEY" in content
        assert "flutter build web --release" in content
        assert "firebase deploy --only hosting --project gest2a3eco" in content
        assert "PENDIENTE_FIREBASE_" in content


def test_ambos_windows_publican_copia_verificada() -> None:
    powershell = _leer(TOOL / "build_production.ps1")
    bash = _leer(TOOL / "build_production.sh")

    assert "GestinemMain\\Doc_Compartidos\\Gest2A3Eco" in powershell
    assert "Get-FileHash" in powershell
    assert "GestinemMain/Doc_Compartidos/Gest2A3Eco" in bash
    assert "sha256sum" in bash


def test_documentacion_no_referencia_los_comandos_retirados() -> None:
    documents = (
        ROOT / "docs" / "flutter_production_build.md",
        ROOT / "docs" / "flutter_messaging_architecture.md",
        APP / "README.md",
        APP / "FIREBASE_HOSTING.md",
    )
    combined = "\n".join(_leer(path) for path in documents)

    assert "deploy_firebase" not in combined
    assert "web-deploy" not in combined
    assert "build_production.sh web" in combined
    assert "build_production.ps1 web" in combined
    assert "Bash" in combined
    assert "PowerShell" in combined
