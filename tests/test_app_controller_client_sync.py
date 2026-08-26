from __future__ import annotations

from types import SimpleNamespace

from controllers.app_controller import AppController


def test_sync_client_platform_uses_synced_organization_id(monkeypatch):
    calls = []

    class ServiceStub:
        configured = True

        def sync_company_profile(self, **kwargs):
            calls.append(("profile", kwargs))
            return {"organization_id": "org-42"}

        def sync_customers(self, **kwargs):
            calls.append(("customers", kwargs))
            return {"synced": len(kwargs["customers"])}

    class ImmediateThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self):
            self.target()

    reader = SimpleNamespace(
        get_empresa=lambda codigo, ejercicio: {
            "codigo": codigo,
            "nombre": "Empresa Test",
            "cif": "B12345678",
            "pais": "ES",
        },
        listar_terceros_por_empresa=lambda codigo, ejercicio: [{
            "id": "ter-1",
            "nif": "A12345678",
            "nombre": "Cliente Test",
            "subcuenta_cliente": "43000001",
        }],
        conn=SimpleNamespace(close=lambda: calls.append(("closed", {}))),
    )
    controller = AppController.__new__(AppController)
    controller._gestor = SimpleNamespace(crear_sesion_lectura=lambda: reader)

    monkeypatch.setattr(
        "services.backend_client_service.BackendClientService",
        ServiceStub,
    )
    monkeypatch.setattr(
        "controllers.app_controller.threading.Thread",
        ImmediateThread,
    )

    controller._sync_client_platform("E00001", 2026)

    customer_call = next(value for kind, value in calls if kind == "customers")
    assert customer_call["organization_id"] == "org-42"
    assert customer_call["customers"][0]["desktop_subcuenta"] == "43000001"
    assert calls[-1][0] == "closed"
