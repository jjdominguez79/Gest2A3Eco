from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault(
    "BACKEND_DATABASE_URL",
    "postgresql+psycopg://gest2a3eco_test:gest2a3eco_test@localhost:5432/gest2a3eco_test",
)

from backend.api import dgt_staff_api
from backend.api.database import Base
from backend.api.messaging_models import MessagingStaff
from backend.api.models import Evento, Parte
from backend.api.schemas import ExpedienteCreate


def _factory(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        "backend.api.service.get_settings",
        lambda: SimpleNamespace(
            public_base_url="https://tramites.example.test",
            token_ttl_hours=168,
        ),
    )
    return sessionmaker(bind=engine, expire_on_commit=False)


def _datos_parte(rol: str) -> dict:
    datos = {
        "direccion": "Calle Uno 1",
        "cp": "39001",
        "poblacion": "Santander",
        "provincia": "Cantabria",
    }
    if rol == "vendedor":
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
                "direccion_envio": "Calle Dos 2",
                "cp_envio": "39002",
                "poblacion_envio": "Santander",
                "provincia_envio": "Cantabria",
            }
        )
    return datos


def test_administrador_flutter_crea_enlaces_y_comprueba_datos(monkeypatch):
    factory = _factory(monkeypatch)
    staff = MessagingStaff(
        external_id="empleado-dgt",
        name="Empleado DGT",
        email="dgt@example.test",
        role="admin",
        active=True,
    )
    with factory() as db:
        db.add(staff)
        db.commit()
        payload = dgt_staff_api.crear_expediente_dgt(
            ExpedienteCreate(
                titulo="Cambio de titularidad",
                vendedor_nombre="Ana Vendedora",
                vendedor_telefono="600000001",
                comprador_nombre="Luis Comprador",
                comprador_telefono="600000002",
            ),
            staff,
            db,
        )

    item = payload["expediente"]
    assert payload["enlaces"]["vendedor"]["url"].startswith(
        "https://tramites.example.test/t/"
    )
    assert payload["enlaces"]["comprador"]["url"].startswith(
        "https://tramites.example.test/t/"
    )
    assert item["partes"]["vendedor"]["nombre"] == "Ana Vendedora"

    with factory() as db:
        pending = dgt_staff_api.comprobar_expediente_dgt(item["id"], staff, db)
        assert pending["completo"] is False
        assert any("formulario completo" in error for error in pending["errores"])

        partes = db.scalars(
            select(Parte).where(Parte.expediente_id == item["id"])
        ).all()
        for parte in partes:
            parte.tipo_persona = "fisica"
            parte.nombre = "Persona Completa"
            parte.nif = "00000000T"
            parte.email = f"{parte.rol}@example.test"
            parte.telefono = "600000003"
            parte.datos = _datos_parte(parte.rol)
            parte.estado = "completado"
        db.commit()

    with factory() as db:
        complete = dgt_staff_api.comprobar_expediente_dgt(item["id"], staff, db)
        assert complete["completo"] is True
        assert complete["errores"] == []
        actors = set(
            db.scalars(
                select(Evento.actor).where(Evento.expediente_id == item["id"])
            )
        )
    assert actors == {"empleado-dgt"}


def test_dgt_flutter_rechaza_empleado_sin_permiso(monkeypatch):
    _factory(monkeypatch)
    review = MessagingStaff(
        external_id="revision-dgt",
        name="Revision",
        email="revision@example.test",
        role="empleado",
        review_only=False,
        active=True,
    )
    with pytest.raises(HTTPException) as error:
        dgt_staff_api._operador_dgt(review)
    assert error.value.status_code == 403
