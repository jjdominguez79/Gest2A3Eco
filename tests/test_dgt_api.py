from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.dgt_api import app as app_module
from backend.dgt_api.database import Base, build_engine
from backend.dgt_api.integrations import DatapriusBackend
from backend.dgt_api.models import Parte


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
    internal = client.get(f"/api/v1/expedientes/{item['id']}", headers=headers).json()
    assert internal["vehiculo"]["matricula"] == "1234ABC"
    assert internal["vehiculo"]["bastidor"] == "VF1AAAAAA12345678"
    assert internal["operacion"]["precio_venta"] == "8500"
    assert internal["operacion"]["fecha_operacion"] == "2026-07-20"
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
    assert item["titulo"].startswith("Cambio de titularidad DGT-")
    link = client.post(f"/api/v1/expedientes/{item['id']}/links", headers=headers).json()["comprador"]["url"]
    token = link.split("token=", 1)[1]
    portal = client.get(f"/t/{item['referencia']}/comprador?token={token}")
    assert portal.status_code == 200
    assert 'name="viewport"' in portal.text
    assert 'href="/static/portal.css"' in portal.text
    assert 'src="/static/portal.js"' in portal.text
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
    listado = client.get(
        f"/api/v1/expedientes/{item['id']}/documentos-generados", headers=headers
    ).json()
    assert listado[0]["fecha_generacion"]
    assert client.delete(
        f"/api/v1/documentos-generados/{generado['id']}", headers=headers
    ).status_code == 200
    assert client.delete(f"/api/v1/expedientes/{item['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/expedientes/{item['id']}", headers=headers).status_code == 404
    Base.metadata.drop_all(engine)


def test_codigo_tasa_y_modelo_620_presentado(tmp_path, monkeypatch):
    client, engine = _client(tmp_path, monkeypatch)
    monkeypatch.setenv("DGT_STORAGE_DIR", str(tmp_path / "private"))
    headers = {"X-API-Key": "test-secret"}
    item = client.post("/api/v1/expedientes", headers=headers, json={}).json()
    links = client.post(f"/api/v1/expedientes/{item['id']}/links", headers=headers).json()
    for rol in ("vendedor", "comprador"):
        token = links[rol]["url"].split("token=", 1)[1]
        path = f"/public/tramites/{item['referencia']}/{rol}"
        assert client.patch(f"{path}?token={token}", json=_party_payload(role=rol)).status_code == 200
        assert client.post(f"{path}/submit?token={token}&privacy_accepted=true").status_code == 200

    invalid = client.patch(
        f"/api/v1/expedientes/{item['id']}",
        headers=headers,
        json={"codigo_tasa": "?!", "version": 1},
    )
    assert invalid.status_code == 422
    patched = client.patch(
        f"/api/v1/expedientes/{item['id']}",
        headers=headers,
        json={"codigo_tasa": "TASA-123456789", "modelo_620_presentado": True, "version": 1},
    )
    assert patched.status_code == 200
    assert patched.json()["operacion"]["codigo_tasa"] == "TASA-123456789"
    missing = client.post(f"/api/v1/expedientes/{item['id']}/validar", headers=headers)
    assert missing.status_code == 422
    assert "620" in missing.json()["detail"]

    uploaded = client.post(
        f"/api/v1/expedientes/{item['id']}/documentos",
        headers=headers,
        data={"rol": "gestor", "tipo": "modelo_620"},
        files={"file": ("modelo620.pdf", b"%PDF-1.4 modelo 620", "application/pdf")},
    )
    assert uploaded.status_code == 201
    assert client.post(f"/api/v1/expedientes/{item['id']}/validar", headers=headers).status_code == 200
    docs = client.get(f"/api/v1/expedientes/{item['id']}/documentos", headers=headers).json()
    assert any(doc["tipo"] == "modelo_620" for doc in docs)
    Base.metadata.drop_all(engine)


def test_backend_expone_anulacion_de_signrequest(tmp_path, monkeypatch):
    client, engine = _client(tmp_path, monkeypatch)

    class FirmaBackendFalso:
        def cancelar(self, request_id):
            return {"detail": "OK", "cancelled": request_id == "firma-1"}

    monkeypatch.setattr(app_module, "SignRequestBackend", FirmaBackendFalso)
    response = client.post(
        "/api/v1/integrations/signrequest/firma-1/cancel",
        headers={"X-API-Key": "test-secret"},
    )

    assert response.status_code == 200
    assert response.json()["cancelled"] is True
    Base.metadata.drop_all(engine)


def test_dataprius_reutiliza_archivo_existente_sin_duplicarlo():
    backend = object.__new__(DatapriusBackend)
    backend.base_path = "FOLDERS/Gest2A3Eco/Tramites DGT"
    llamadas = []

    def request(method, path, **kwargs):
        llamadas.append((method, path, kwargs))
        if path == "/folders/getpath":
            return {"data": [{"ID": 123}]}
        if path == "/folders/files/123":
            return {"data": [{"ID": 456, "Name": "contrato_firmado.pdf", "Size": 100}]}
        raise AssertionError("No debe intentar subir un fichero que ya existe")

    backend._request = request
    resultado = backend.subir(
        "expedientes/DGT-2026-0001/Firmados",
        "contrato_firmado.pdf",
        b"%PDF",
    )

    assert resultado["id"] == 456
    assert resultado["existente"] is True
    assert [path for _method, path, _kwargs in llamadas] == [
        "/folders/getpath",
        "/folders/files/123",
    ]


def test_edicion_interna_guarda_partes_vehiculo_y_operacion(tmp_path, monkeypatch):
    client, engine = _client(tmp_path, monkeypatch)
    headers = {"X-API-Key": "test-secret"}
    item = client.post(
        "/api/v1/expedientes",
        headers=headers,
        json={"vendedor_email": "incorrecto@example.test"},
    ).json()

    patched = client.patch(
        f"/api/v1/expedientes/{item['id']}",
        headers=headers,
        json={
            "version": item["version"],
            "vendedor_nombre": "Vendedor corregido",
            "vendedor_email": "correcto@example.test",
            "vendedor_telefono": "611111111",
            "comprador_nombre": "Comprador corregido",
            "comprador_email": "comprador@example.test",
            "comprador_telefono": "622222222",
            "vehiculo_matricula": "1234ABC",
            "vehiculo_bastidor": "VF1AAAAAA12345678",
            "precio_venta": 9750.5,
            "fecha_operacion": "2026-07-31",
        },
    )

    assert patched.status_code == 200
    saved = client.get(f"/api/v1/expedientes/{item['id']}", headers=headers).json()
    assert saved["partes"]["vendedor"]["email"] == "correcto@example.test"
    assert saved["partes"]["vendedor"]["nombre"] == "Vendedor corregido"
    assert saved["partes"]["comprador"]["email"] == "comprador@example.test"
    assert saved["vehiculo"]["matricula"] == "1234ABC"
    assert saved["vehiculo"]["bastidor"] == "VF1AAAAAA12345678"
    assert saved["operacion"]["precio_venta"] == 9750.5
    assert saved["operacion"]["fecha_operacion"] == "2026-07-31"
    Base.metadata.drop_all(engine)


def test_persiste_estado_y_solicitudes_de_firma(tmp_path, monkeypatch):
    client, engine = _client(tmp_path, monkeypatch)
    headers = {"X-API-Key": "test-secret"}
    item = client.post("/api/v1/expedientes", headers=headers, json={}).json()

    response = client.patch(
        f"/api/v1/expedientes/{item['id']}",
        headers=headers,
        json={
            "version": item["version"],
            "firma_estado": "enviado",
            "firma_provider": "signrequest",
            "firma_request_id": "[\"firma-1\"]",
            "firma_evidencia": {"solicitudes": [{"request_id": "firma-1"}]},
        },
    )

    assert response.status_code == 200
    detail = client.get(f"/api/v1/expedientes/{item['id']}", headers=headers).json()
    assert detail["firma_estado"] == "enviado"
    assert detail["firma_provider"] == "signrequest"
    assert detail["firma_evidencia"]["solicitudes"][0]["request_id"] == "firma-1"
    Base.metadata.drop_all(engine)


def test_correccion_interna_conserva_envio_y_datos_no_editados(tmp_path, monkeypatch):
    client, engine = _client(tmp_path, monkeypatch)
    headers = {"X-API-Key": "test-secret"}
    item = client.post("/api/v1/expedientes", headers=headers, json={}).json()
    link = client.post(f"/api/v1/expedientes/{item['id']}/links", headers=headers).json()["vendedor"]["url"]
    token = link.split("token=", 1)[1]
    path = f"/public/tramites/{item['referencia']}/vendedor"
    original = _party_payload()
    client.patch(f"{path}?token={token}", json=original)
    client.post(f"{path}/submit?token={token}&privacy_accepted=true")

    corrected = {**original, "datos": {"precio_venta": "9000"}}
    response = client.patch(
        f"/api/v1/expedientes/{item['id']}/partes/vendedor",
        headers=headers,
        json=corrected,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["partes"]["vendedor"]["estado"] == "completado"
    assert data["partes"]["vendedor"]["submitted_at"]
    assert data["partes"]["vendedor"]["datos"]["vehiculo_marca"] == "Renault"
    assert data["partes"]["vendedor"]["datos"]["precio_venta"] == "9000"
    assert data["estado"] == "revision_interna"

    buyer_link = client.post(f"/api/v1/expedientes/{item['id']}/links", headers=headers).json()["comprador"]["url"]
    buyer_token = buyer_link.split("token=", 1)[1]
    buyer_path = f"/public/tramites/{item['referencia']}/comprador"
    client.patch(f"{buyer_path}?token={buyer_token}", json=_party_payload(role="comprador"))
    client.post(f"{buyer_path}/submit?token={buyer_token}&privacy_accepted=true")
    with sessionmaker(bind=engine, expire_on_commit=False)() as db:
        seller = db.scalar(select(Parte).where(Parte.expediente_id == item["id"], Parte.rol == "vendedor"))
        seller.estado = "en_curso"
        db.commit()
    assert client.post(f"/api/v1/expedientes/{item['id']}/validar", headers=headers).status_code == 200
    Base.metadata.drop_all(engine)


def test_subsanacion_regenera_solo_enlace_de_la_parte(tmp_path, monkeypatch):
    client, engine = _client(tmp_path, monkeypatch)
    headers = {"X-API-Key": "test-secret"}
    item = client.post("/api/v1/expedientes", headers=headers, json={}).json()
    links = client.post(f"/api/v1/expedientes/{item['id']}/links", headers=headers).json()
    old_seller = links["vendedor"]["url"]
    old_buyer = links["comprador"]["url"]
    response = client.post(
        f"/api/v1/expedientes/{item['id']}/subsanaciones",
        headers=headers,
        json={"rol": "vendedor", "mensaje": "Corrige el bastidor"},
    )
    assert response.status_code == 201
    new_seller = response.json()["url"]
    assert new_seller != old_seller
    assert client.get(old_seller.replace("https://tramites.example.test", "")).status_code == 401
    assert client.get(old_buyer.replace("https://tramites.example.test", "")).status_code == 200
    assert client.get(new_seller.replace("https://tramites.example.test", "")).status_code == 200
    current = client.get(f"/api/v1/expedientes/{item['id']}", headers=headers).json()
    assert current["partes"]["vendedor"]["estado"] == "requiere_subsanacion"
    assert current["partes"]["comprador"]["estado"] == "pendiente"
    Base.metadata.drop_all(engine)
