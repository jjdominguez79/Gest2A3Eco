from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.dgt_api import app as app_module
from backend.dgt_api.database import Base, build_engine
from backend.dgt_api.models import Firma, Pago, Parte
from backend.dgt_api.paygold import (
    PayGoldClient,
    codificar_parametros,
    decodificar_parametros,
    firmar_parametros,
    importe_centimos,
)


TEST_SECRET = "sq7HjrUOBfKmC576ILgskD5srU870gJ7"


def test_firma_coincide_con_vector_oficial_redsys():
    parameters = (
        '{"DS_MERCHANT_MERCHANTCODE":"999008881",'
        '"DS_MERCHANT_TERMINAL":"1",'
        '"DS_MERCHANT_ORDER":"06080232580",'
        '"DS_MERCHANT_AMOUNT":"100",'
        '"DS_MERCHANT_CURRENCY":"978",'
        '"DS_MERCHANT_TRANSACTIONTYPE":"3"}'
    )
    import base64

    encoded = base64.b64encode(parameters.encode("utf-8")).decode("ascii")

    assert (
        firmar_parametros(TEST_SECRET, "06080232580", encoded)
        == "GmHwTovthyrztLs7D77GflclBzsANderHe3zFF6JiZQ="
    )


def test_codifica_parametros_e_importes_sin_redondeos_binarios():
    payload = {"DS_MERCHANT_ORDER": "1234ABCDEF", "nombre": "José"}

    assert decodificar_parametros(codificar_parametros(payload)) == payload
    assert importe_centimos("102.35") == "10235"


def test_informa_si_el_terminal_no_tiene_paygold():
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"errorCode": "SIS0487"}

    class Session:
        @staticmethod
        def post(*_args, **_kwargs):
            return Response()

    client = PayGoldClient(
        "999008881",
        "999",
        TEST_SECRET,
        "https://sandbox.example.test",
        "",
        session=Session(),
    )

    try:
        client.crear_enlace(
            order="1234ABCDEF",
            amount_cents="100",
            description="Prueba",
            customer_name="Cliente",
            expiry_minutes=30,
        )
    except ValueError as exc:
        assert "no tiene PayGold habilitado" in str(exc)
        assert "SIS0487" in str(exc)
    else:
        raise AssertionError("Debia informar que PayGold no esta habilitado")


class _FakePayGold:
    def __init__(self):
        self.calls = []
        self.notification = {}

    def crear_enlace(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "Ds_Order": kwargs["order"],
            "Ds_Response": "9998",
            "Ds_UrlPago2Fases": "https://sis-t.redsys.es/sis/p2f?t=PRUEBA",
        }

    def validar_respuesta(self, _envelope):
        return dict(self.notification)


def _client(tmp_path: Path, monkeypatch, fake: _FakePayGold):
    engine = build_engine(f"sqlite:///{(tmp_path / 'paygold.db').as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setenv("DGT_INTERNAL_API_KEY", "test-secret")
    monkeypatch.setenv("DGT_PUBLIC_BASE_URL", "https://backend.example.test")
    monkeypatch.setenv("REDSYS_ENVIRONMENT", "test")
    monkeypatch.setenv("REDSYS_MERCHANT_CODE", "999008881")
    monkeypatch.setenv("REDSYS_TERMINAL", "1")
    monkeypatch.setenv("REDSYS_SECRET_KEY", TEST_SECRET)
    app_module.app.dependency_overrides[app_module.get_db] = override_db
    app_module.app.dependency_overrides[app_module.get_paygold_client] = lambda: fake
    return TestClient(app_module.app), engine, factory


def test_crea_enlace_sandbox_solo_para_expediente_firmado(tmp_path, monkeypatch):
    fake = _FakePayGold()
    client, engine, factory = _client(tmp_path, monkeypatch, fake)
    headers = {"X-API-Key": "test-secret"}
    expediente = client.post(
        "/api/v1/expedientes",
        headers=headers,
        json={"comprador_email": "cliente@example.test", "comprador_telefono": "600000000"},
    ).json()
    with factory() as db:
        comprador = db.scalar(
            select(Parte).where(
                Parte.expediente_id == expediente["id"], Parte.rol == "comprador"
            )
        )
        comprador.nombre = "Cliente de prueba"
        db.add(Firma(expediente_id=expediente["id"], estado="firmado"))
        db.commit()

    response = client.post(
        f"/api/v1/expedientes/{expediente['id']}/pagos/paygold",
        headers=headers,
        json={"importe": "102.35", "descripcion": "Tramite DGT de prueba"},
    )

    assert response.status_code == 201
    payment = response.json()
    assert payment["entorno"] == "test"
    assert payment["estado"] == "enlace_generado"
    assert payment["importe_centimos"] == 10235
    assert payment["enlace"].startswith("https://sis-t.redsys.es/")
    assert fake.calls[0]["enviar_desde_redsys"] is False

    fake.notification = {
        "Ds_Order": payment["pedido"],
        "Ds_MerchantCode": "999008881",
        "Ds_Terminal": "1",
        "Ds_Amount": "10235",
        "Ds_Response": "0000",
        "Ds_AuthorisationCode": "123456",
    }
    notified = client.post(
        "/api/v1/pagos/redsys/notificacion",
        data={"Ds_MerchantParameters": "simulado", "Ds_Signature": "simulada"},
    )
    assert notified.status_code == 200
    assert notified.text == "OK"
    with factory() as db:
        stored = db.scalar(select(Pago).where(Pago.pedido == payment["pedido"]))
        assert stored.estado == "pagado"
        assert stored.codigo_autorizacion == "123456"

    app_module.app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
