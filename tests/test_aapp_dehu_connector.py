from services.aapp.cert_store import CertMaterial
from services.aapp.dehu_playwright import ConectorDEHU, _map_estado


def test_estados_dehu_no_convierten_historico_en_pendiente():
    assert _map_estado("ACCEPTED") == "ACEPTADA"
    assert _map_estado("REJECTED") == "RECHAZADA"
    assert _map_estado("EXPIRED") == "VENCIDA"
    assert _map_estado("REALIZADA") == "REALIZADA"


def test_registro_realizado_sin_estado_se_mantiene_como_realizado():
    connector = ConectorDEHU()
    rows = connector._map_registros(
        [{
            "identifier": "DEHU-1",
            "concept": "Notificacion historica",
            "nifTitular": "B12345678",
            "_endpoint": "/api/v1/realized_notifications",
        }],
        CertMaterial(
            cert_id="cert-1",
            nombre="Cliente Uno",
            nif_titular="B12345678",
            ruta_archivo="cliente.pfx",
            password="",
        ),
        "B12345678",
    )

    assert rows[0].estado == "REALIZADA"
