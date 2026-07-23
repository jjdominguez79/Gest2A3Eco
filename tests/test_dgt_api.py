from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.dgt_api import app as app_module
from backend.dgt_api.database import Base, build_engine


def _client(tmp_path: Path, monkeypatch):
    db_path = (tmp_path / "api.db").as_posix()
    engine = build_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setenv("DGT_INTERNAL_API_KEY", "test-secret")
    monkeypatch.setenv("DGT_PUBLIC_BASE_URL", "https://tramites.example.test")
    app_module.app.dependency_overrides[app_module.get_db] = override_db
    return TestClient(app_module.app), engine


def test_flujo_api_separa_roles_y_audita(tmp_path, monkeypatch):
    client, engine = _client(tmp_path, monkeypatch)
    headers = {"X-API-Key": "test-secret"}
    created = client.post(
        "/api/v1/expedientes",
        headers=headers,
        json={"titulo": "Cambio titularidad", "vendedor_email": "v@example.test"},
    )
    assert created.status_code == 201
    item = created.json()
    assert set(item["partes"]) == {"vendedor", "comprador"}

    links = client.post(f"/api/v1/expedientes/{item['id']}/links", headers=headers).json()
    seller_url = links["vendedor"]["url"]
    token = seller_url.split("token=", 1)[1]
    public_path = f"/public/tramites/{item['referencia']}/vendedor?token={token}"
    public = client.get(public_path)
    assert public.status_code == 200
    assert public.json()["rol"] == "vendedor"
    assert "comprador" not in public.text

    saved = client.patch(
        public_path,
        json={"nombre": "Ana Vendedora", "nif": "00000000T", "datos": {"direccion": "Calle Uno"}},
    )
    assert saved.status_code == 200
    submitted = client.post(f"{public_path.replace('?', '/submit?')}&privacy_accepted=true")
    assert submitted.status_code == 200

    revoked = client.post(f"/api/v1/expedientes/{item['id']}/links/vendedor/revoke", headers=headers)
    assert revoked.json()["revoked"] == 1
    assert client.get(public_path).status_code == 401
    Base.metadata.drop_all(engine)


def test_portal_responsive_y_upload_privado(tmp_path, monkeypatch):
    client, engine = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("DGT_STORAGE_DIR", str(tmp_path / "private"))
    headers = {"X-API-Key": "test-secret"}
    item = client.post("/api/v1/expedientes", headers=headers, json={}).json()
    link = client.post(f"/api/v1/expedientes/{item['id']}/links", headers=headers).json()["comprador"]["url"]
    token = link.split("token=", 1)[1]
    portal = client.get(f"/t/{item['referencia']}/comprador?token={token}")
    assert portal.status_code == 200
    assert 'name="viewport"' in portal.text
    assert "Vehiculo y operacion" not in portal.text

    uploaded = client.post(
        f"/public/tramites/{item['referencia']}/comprador/documentos?token={token}",
        data={"tipo": "dni"},
        files={"file": ("dni.pdf", b"%PDF-1.4 demo", "application/pdf")},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["sha256"]
    assert list((tmp_path / "private").rglob("*.pdf"))
    Base.metadata.drop_all(engine)


def test_api_interna_requiere_credencial(tmp_path, monkeypatch):
    client, engine = _client(tmp_path, monkeypatch)
    assert client.get("/api/v1/expedientes").status_code == 401
    assert client.get("/health").status_code == 200
    Base.metadata.drop_all(engine)
