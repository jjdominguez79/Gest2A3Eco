from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYNOLOGY = ROOT / "deploy" / "synology"


def test_synology_packages_match_the_real_network_layout():
    packages = {
        "gest2a3eco-mail-sync": "gest2a3eco-mail-sync",
        "gest2a3eco-messaging-sync": "gest2a3eco-messaging-sync",
        "gest2a3eco-master-data-sync": "gest2a3eco-master-data-sync",
    }

    for folder, container in packages.items():
        compose = (SYNOLOGY / folder / "compose.yaml").read_text(encoding="utf-8")
        assert f"container_name: {container}" in compose
        assert 'POSTGRES_HOST: "192.168.0.18"' in compose
        assert 'POSTGRES_PORT: "5433"' in compose
        assert "192.168.0.19" not in compose


def test_each_worker_owns_only_its_secret_contract():
    mail = (SYNOLOGY / "gest2a3eco-mail-sync" / "compose.yaml").read_text()
    messaging = (SYNOLOGY / "gest2a3eco-messaging-sync" / "compose.yaml").read_text()
    master = (SYNOLOGY / "gest2a3eco-master-data-sync" / "compose.yaml").read_text()

    assert "Gest2A3Eco-Sync.pfx" in mail
    assert "messaging_sync_token.txt" not in mail
    assert "client_master_sync_token.txt" not in mail

    assert "messaging_sync_token.txt" in messaging
    assert "client_master_sync_token.txt" not in messaging

    assert "client_master_sync_token.txt" in master
    assert "messaging_sync_token.txt" not in master


def test_package_builder_copies_only_required_worker_modules():
    builder = (SYNOLOGY / "build_packages.ps1").read_text(encoding="utf-8")

    assert "gest2a3eco-mail-sync" in builder
    assert "messaging_worker.py" in builder
    assert "master_data_worker.py" in builder
    assert "Los ficheros de secrets no se copian" in builder


def test_worker_messaging_solo_sincroniza_adjuntos():
    worker = (ROOT / "sync_worker" / "messaging_worker.py").read_text(
        encoding="utf-8"
    )

    assert "sync_organizations" not in worker
    assert "/sync/organizations" not in worker
    assert "/sync/attachments/pending" in worker


def test_imagen_messaging_tiene_version_explicita():
    compose = (
        SYNOLOGY / "gest2a3eco-messaging-sync" / "compose.yaml"
    ).read_text(encoding="utf-8")

    assert "image: gest2a3eco-messaging-sync:2026.09.03.1" in compose
