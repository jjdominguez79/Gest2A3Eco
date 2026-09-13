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
    assert "gest2a3eco-aapp-worker" in builder
    assert "'worker.py'" in builder
    assert '"aapp_worker\\$module"' in builder
    assert "'certificados.py'" in builder
    assert "'dehu_playwright.py'" in builder
    assert '"services\\aapp\\$module"' in builder
    assert "Los ficheros de secrets no se copian" in builder


def test_aapp_worker_synology_es_aislado_y_usa_secreto_montado():
    root = SYNOLOGY / "gest2a3eco-aapp-worker"
    compose = (root / "compose.yaml").read_text(encoding="utf-8")
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")

    assert "container_name:" not in compose
    assert "image: gest2a3eco-aapp-worker:2026.09.13.23" in compose
    assert "AAPP_WORKER_API_KEY_FILE" in compose
    assert "aapp_worker_api_key.txt" in compose
    assert "read_only: true" in compose
    assert "cap_drop:" in compose
    assert "COPY aapp_worker /app/aapp_worker" in dockerfile
    assert "COPY services /app/services" in dockerfile


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
