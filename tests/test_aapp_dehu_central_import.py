from services.aapp.sync_service import importar_bandeja_central


class _Backend:
    def list_dehu_notifications(self, **_kwargs):
        return [{
            "id": "central-1",
            "request_id": "request-1",
            "company_code": "E00001",
            "mailbox_id": "mailbox-1",
            "reference": "DEHU-1",
            "subject": "Notificacion de prueba",
            "description": "Descripcion",
            "action_type": "NOTIFICACION",
            "holder_tax_id": "B12345678",
            "holder_name": "Cliente Uno",
            "available_date": "2026-09-12",
            "expiration_date": "2026-09-22",
            "status": "PENDIENTE",
            "document_id": None,
            "metadata": {"sentReference": "ENV-1"},
        }]


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
    assert "central-1" in row["metadatos_json"]
