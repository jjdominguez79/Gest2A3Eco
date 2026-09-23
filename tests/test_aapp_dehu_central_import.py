from services.aapp.sync_service import importar_bandeja_central


class _Backend:
    def __init__(self):
        self.items = [{
            "id": "central-1",
            "request_id": "request-1",
            "company_code": "E00001",
            "mailbox_id": "mailbox-1",
            "reference": "DEHU-1",
            "subject": "Notificacion de prueba",
            "description": "Descripcion",
            "issuing_body": "Agencia Tributaria",
            "issuing_body_source": "AEAT",
            "action_type": "NOTIFICACION",
            "holder_tax_id": "B12345678",
            "holder_name": "Cliente Uno",
            "available_date": "2026-09-12",
            "expiration_date": "2026-09-22",
            "status": "PENDIENTE",
            "document_id": None,
            "metadata": {"sentReference": "ENV-1"},
        }]

    def list_dehu_notifications(self, **_kwargs):
        return list(self.items)


class _Gestor:
    def __init__(self):
        self.rows = {}

    def listar_notif_buzones_global(self):
        return [{
            "id": "mailbox-1",
            "codigo_empresa": "E00001",
            "organismo_id": 1,
            "organismo_codigo": "DEHU",
        }]

    def get_notif_bandeja_item(self, item_id):
        return self.rows.get(item_id)

    def upsert_notif_bandeja_item(self, item):
        self.rows[item["id"]] = item


def test_importa_bandeja_central_sin_duplicar():
    gestor = _Gestor()
    first = importar_bandeja_central(gestor, backend=_Backend())
    second = importar_bandeja_central(gestor, backend=_Backend())

    assert first.total == 1
    assert first.nuevas == 1
    assert second.nuevas == 0
    assert len(gestor.rows) == 1
    row = next(iter(gestor.rows.values()))
    assert row["ejercicio"] == 2026
    assert row["descripcion"] == "Agencia Tributaria"
    assert "central-1" in row["metadatos_json"]
    assert "issuing_body" in row["metadatos_json"]


def test_no_reimporta_leidas_ni_revierte_estado_local():
    gestor = _Gestor()
    importar_bandeja_central(gestor, backend=_Backend())
    row = next(iter(gestor.rows.values()))
    row["estado"] = "LEIDA"
    result = importar_bandeja_central(gestor, backend=_Backend())
    assert result.omitidas == 1
    assert row["estado"] == "LEIDA"


def test_conserva_historico_local_si_deja_de_aparecer_en_la_bandeja_central():
    gestor = _Gestor()
    backend = _Backend()
    importar_bandeja_central(gestor, backend=backend)
    item_id = next(iter(gestor.rows))

    # El portal ya no devuelve el aviso (por lectura, rechazo o caducidad),
    # pero la sincronizacion incremental nunca purga el historico importado.
    backend.items = []
    result = importar_bandeja_central(gestor, backend=backend)

    assert result.total == 0
    assert item_id in gestor.rows
    assert gestor.rows[item_id]["referencia"] == "DEHU-1"


def test_actualiza_a_leida_si_el_portal_la_realiza_fuera_de_la_aplicacion():
    gestor = _Gestor()
    backend = _Backend()
    importar_bandeja_central(gestor, backend=backend)
    backend.items[0]["status"] = "LEIDA"
    backend.items[0]["source_endpoint"] = "/api/v1/realized_notifications"

    result = importar_bandeja_central(gestor, backend=backend)

    assert result.omitidas == 0
    assert next(iter(gestor.rows.values()))["estado"] == "LEIDA"
