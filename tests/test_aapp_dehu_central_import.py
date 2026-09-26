from services.aapp.sync_service import (
    actualizar_bandeja_desde_dehu,
    importar_bandeja_central,
)


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
            "nombre": "DEHu",
            "activo": 1,
        }]

    def get_empresa(self, codigo):
        assert codigo == "E00001"
        return {"codigo": codigo, "cif": "B12345678"}

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
    assert result.actualizadas == 1
    assert next(iter(gestor.rows.values()))["estado"] == "LEIDA"


def test_actualizacion_manual_consulta_dehu_antes_de_importar():
    class Backend(_Backend):
        def __init__(self):
            super().__init__()
            self.creada = None

        def create_certificate_request(self, **kwargs):
            self.creada = kwargs
            self.items[0]["status"] = "ACEPTADA"
            self.items.append({
                **self.items[0],
                "id": "central-2",
                "reference": "DEHU-2",
                "subject": "Notificacion nueva ya aceptada",
            })
            return {"id": "request-manual", "status": "queued"}

        def list_certificate_requests(self, **_kwargs):
            return [{
                "id": "request-manual",
                "certificate_type": "DEHU_SYNC",
                "status": "completed",
            }]

    gestor = _Gestor()
    backend = Backend()
    importar_bandeja_central(gestor, backend=backend)

    result = actualizar_bandeja_desde_dehu(
        gestor, company_code="E00001", backend=backend,
        timeout_seconds=0, poll_interval=0,
    )

    assert backend.creada["company_code"] == "E00001"
    assert backend.creada["certificate_type"] == "DEHU_SYNC"
    assert backend.creada["parameters"]["download_mode"] == "SOLO_DETECTAR"
    assert result.encoladas == 1
    assert result.completadas == 1
    assert result.pendientes == 0
    assert result.nuevas == 1
    assert result.actualizadas == 1
    assert {row["estado"] for row in gestor.rows.values()} == {"ACEPTADA"}


def test_actualizacion_manual_adelanta_un_reintento_automatico_aplazado():
    class Conflicto(Exception):
        response = type("Response", (), {"status_code": 409})()

    class Backend(_Backend):
        def __init__(self):
            super().__init__()
            self.reintentada = None
            self.consultas = 0

        def create_certificate_request(self, **_kwargs):
            raise Conflicto("Ya existe una solicitud activa")

        def list_certificate_requests(self, **_kwargs):
            self.consultas += 1
            return [{
                "id": "request-automatico",
                "certificate_type": "DEHU_SYNC",
                "status": "queued" if self.consultas == 1 else "completed",
                "next_attempt_at": "2026-09-26T08:30:00+00:00" if self.consultas == 1 else None,
            }]

        def retry_certificate_request(self, request_id):
            self.reintentada = request_id
            return {"id": request_id, "status": "queued"}

    backend = Backend()
    result = actualizar_bandeja_desde_dehu(
        _Gestor(), company_code="E00001", backend=backend,
        timeout_seconds=0, poll_interval=0,
    )

    assert backend.reintentada == "request-automatico"
    assert result.encoladas == 1
    assert result.completadas == 1
