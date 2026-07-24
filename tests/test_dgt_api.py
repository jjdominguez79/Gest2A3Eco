from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.dgt_api import app as app_module
from backend.dgt_api.database import Base, build_engine


def _party_payload(*, role="vendedor", tipo_persona="fisica"):
    datos = {
        "direccion": "Calle Uno 1",
        "cp": "39001",
        "poblacion": "Santander",
        "provincia": "Cantabria",
    }
    if tipo_persona == "juridica":
        datos.update({"representante_nombre": "Ana Representante", "representante_nif": "00000000T"})
    if role == "vendedor":
        datos.update(
            {
                "vehiculo_matricula": "1234ABC",
                "vehiculo_bastidor": "VF1AAAAAA12345678",
                "vehiculo_marca": "Renault",
                "vehiculo_modelo": "Clio",
                "primera_matriculacion": "2020-01-01",
                "kilometraje": "45000",
                "precio_venta": "8500",
                "fecha_operacion": "2026-07-20",
                "hora_entrega": "12:30",
                "forma_pago": "Transferencia",
                "llaves_vehiculo": "2",
                "cargas_estado": "sin_cargas",
                "estado_vehiculo": "Usado en buen estado",
            }
        )
    else:
        datos.update(
            {
                "envio_misma_direccion": "on",
                "direccion_envio": "Calle Uno 1",
                "cp_envio": "39001",
                "poblacion_envio": "Santander",
                "provincia_envio": "Cantabria",
            }
        )
    return {
        "tipo_persona": tipo_persona,
        "nombre": "Empresa Demo SL" if tipo_persona == "juridica" else "Ana Demo",
        "nif": "A58818501" if tipo_persona == "juridica" else "00000000T",
        "email": "ana@example.test",
        "telefono": "600000000",
        "datos": datos,
    }


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
        json=_party_payload(),
    )
    assert saved.status_code == 200
    submitted = client.post(f"{public_path.replace('?', '/submit?')}&privacy_accepted=true")
    assert submitted.status_code == 200

    revoked = client.post(f"/api/v1/expedientes/{item['id']}/links/vendedor/revoke", headers=headers)
    assert revoked.json()["revoked"] == 1
    assert client.get(public_path).status_code == 401
    Base.metadata.drop_all(engine)


def test_portal_sin_adjuntos_generales_para_comprador(tmp_path, monkeypatch):
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
    assert uploaded.status_code == 422
    assert not list((tmp_path / "private").rglob("*.pdf"))
    Base.metadata.drop_all(engine)


def test_vendedor_juridico_exige_representante_y_factura(tmp_path, monkeypatch):
    client, engine = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("DGT_STORAGE_DIR", str(tmp_path / "private"))
    headers = {"X-API-Key": "test-secret"}
    item = client.post("/api/v1/expedientes", headers=headers, json={}).json()
    link = client.post(f"/api/v1/expedientes/{item['id']}/links", headers=headers).json()["vendedor"]["url"]
    token = link.split("token=", 1)[1]
    path = f"/public/tramites/{item['referencia']}/vendedor"
    payload = _party_payload(tipo_persona="juridica")
    payload["datos"].pop("representante_nif")
    assert client.patch(f"{path}?token={token}", json=payload).status_code == 200
    missing_rep = client.post(f"{path}/submit?token={token}&privacy_accepted=true")
    assert missing_rep.status_code == 422
    assert any("representante" in error.lower() for error in missing_rep.json()["detail"])

    payload = _party_payload(tipo_persona="juridica")
    assert client.patch(f"{path}?token={token}", json=payload).status_code == 200
    missing_invoice = client.post(f"{path}/submit?token={token}&privacy_accepted=true")
    assert missing_invoice.status_code == 422
    assert any("factura" in error.lower() for error in missing_invoice.json()["detail"])
    uploaded = client.post(
        f"{path}/documentos?token={token}",
        data={"tipo": "factura"},
        files={"file": ("factura.pdf", b"%PDF-1.4 demo", "application/pdf")},
    )
    assert uploaded.status_code == 201
    assert client.post(f"{path}/submit?token={token}&privacy_accepted=true").status_code == 200
    Base.metadata.drop_all(engine)


def test_comprador_juridico_exige_representante_y_direccion_envio(tmp_path, monkeypatch):
    client, engine = _client(tmp_path, monkeypatch)
    headers = {"X-API-Key": "test-secret"}
    item = client.post("/api/v1/expedientes", headers=headers, json={}).json()
    link = client.post(f"/api/v1/expedientes/{item['id']}/links", headers=headers).json()["comprador"]["url"]
    token = link.split("token=", 1)[1]
    path = f"/public/tramites/{item['referencia']}/comprador"
    payload = _party_payload(role="comprador", tipo_persona="juridica")
    payload["datos"].pop("representante_nombre")
    payload["datos"].pop("direccion_envio")
    client.patch(f"{path}?token={token}", json=payload)
    response = client.post(f"{path}/submit?token={token}&privacy_accepted=true")
    assert response.status_code == 422
    text = " ".join(response.json()["detail"]).lower()
    assert "representante" in text
    assert "direccion de envio" in text
    Base.metadata.drop_all(engine)


def test_api_interna_requiere_credencial(tmp_path, monkeypatch):
    client, engine = _client(tmp_path, monkeypatch)
    assert client.get("/api/v1/expedientes").status_code == 401
    assert client.get("/health").status_code == 200
    Base.metadata.drop_all(engine)


def test_elimina_documentos_y_expediente_sin_dejar_ficheros(tmp_path, monkeypatch):
    client, engine = _client(tmp_path, monkeypatch)
    storage = tmp_path / "private"
    monkeypatch.setenv("DGT_STORAGE_DIR", str(storage))
    headers = {"X-API-Key": "test-secret"}
    item = client.post("/api/v1/expedientes", headers=headers, json={}).json()
    link = client.post(f"/api/v1/expedientes/{item['id']}/links", headers=headers).json()["vendedor"]["url"]
    token = link.split("token=", 1)[1]
    path = f"/public/tramites/{item['referencia']}/vendedor"
    client.patch(f"{path}?token={token}", json=_party_payload(tipo_persona="juridica"))
    uploaded = client.post(
        f"{path}/documentos?token={token}",
        data={"tipo": "factura"},
        files={"file": ("factura.pdf", b"%PDF-1.4 demo", "application/pdf")},
    ).json()
    assert list(storage.rglob("*.pdf"))
    assert client.delete(f"/api/v1/documentos/{uploaded['id']}", headers=headers).status_code == 204
    assert not list(storage.rglob("*.pdf"))

    generado = client.post(
        f"/api/v1/expedientes/{item['id']}/documentos-generados",
        headers=headers,
        json={"tipo_documento": "contrato", "ruta_pdf": "C:/temporal/contrato.pdf"},
    ).json()
    assert client.delete(
        f"/api/v1/documentos-generados/{generado['id']}", headers=headers
    ).status_code == 200
    assert client.delete(f"/api/v1/expedientes/{item['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/expedientes/{item['id']}", headers=headers).status_code == 404
    Base.metadata.drop_all(engine)
