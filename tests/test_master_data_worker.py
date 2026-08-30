"""Pruebas del worker unidireccional de datos maestros."""

from types import SimpleNamespace

from backend.api import security
from sync_worker.master_data_worker import MasterDataConfig, MasterDataWorker


class _Response:
    def __init__(self, data=None):
        self._data = data or {"status": "ok"}

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class _Session:
    def __init__(self):
        self.calls = []

    def put(self, url, **kwargs):
        self.calls.append(("PUT", url, kwargs))
        return _Response({"organization_id": "org-1"})

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return _Response()


def test_worker_publica_perfil_clientes_y_serie_solo_hacia_backend(monkeypatch):
    session = _Session()
    worker = MasterDataWorker(
        MasterDataConfig(
            api_url="https://backend.example",
            api_token="secret",
            postgres_dsn="postgresql://desktop",
            interval_seconds=300,
            online_series_code="APP",
        ),
        session=session,
    )
    monkeypatch.setattr(worker, "_load_companies", lambda: [{
        "codigo": "E00006", "ejercicio": 2026, "nombre": "Empresa Demo",
        "activo": True, "cif": "b-12345678", "direccion": "Calle Uno",
        "cp": "28001", "poblacion": "Madrid", "provincia": "Madrid",
        "pais": "ES", "telefono": "911", "email": "info@example.com",
    }])
    monkeypatch.setattr(worker, "_load_customers", lambda _code: [{
        "tax_id": "A12345678", "legal_name": "Cliente", "active": True,
        "desktop_tercero_id": "ter-1", "desktop_subcuenta": "43000001",
    }])

    assert worker.run_once() == {"companies": 1, "customers": 1}
    assert [method for method, *_ in session.calls] == ["PUT", "POST", "POST"]

    profile = session.calls[0][2]["json"]
    customers = session.calls[1][2]["json"]
    series = session.calls[2][2]["json"]
    assert profile["company_code"] == "E00006"
    assert customers == {
        "organization_id": "org-1",
        "customers": [{
            "tax_id": "A12345678", "legal_name": "Cliente", "active": True,
            "desktop_tercero_id": "ter-1", "desktop_subcuenta": "43000001",
        }],
        "full_snapshot": True,
    }
    assert series["series_code"] == "APP"
    assert series["fiscal_year"] == 2026
    assert all(call[2]["headers"]["X-API-Key"] == "secret" for call in session.calls)


def test_backend_acepta_clave_exclusiva_del_worker_maestro(monkeypatch):
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(client_master_sync_api_key="master-secret"),
    )
    assert (
        security.require_master_sync_or_workstation_internal("master-secret")
        == "client-master-sync"
    )
