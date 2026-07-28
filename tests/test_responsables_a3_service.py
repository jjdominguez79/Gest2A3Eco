from models.gestor_sqlite import GestorSQLite
from services import responsables_a3_service as service


def test_cliente_interno_acepta_varios_emails():
    assert service.es_cliente_interno({
        "email": "cliente@example.com; usuario@gestinem.es",
    })
    assert not service.es_cliente_interno({"email": "cliente@example.com"})


def test_actualiza_todos_los_ejercicios_y_prioriza_cliente_interno(
    monkeypatch, tmp_path,
):
    gestor = GestorSQLite(tmp_path / "test.db")
    for ejercicio in (2025, 2026):
        gestor.upsert_empresa({
            "codigo": "E00001", "ejercicio": ejercicio, "nombre": "Cliente",
            "cif": "B12345678", "email": "cliente@example.com",
        })
        gestor.upsert_empresa({
            "codigo": "E00002", "ejercicio": ejercicio, "nombre": "Interno",
            "cif": "B87654321", "email": "admin@gestinem.es",
        })
    monkeypatch.setattr(
        service, "_leer_mapa_responsables",
        lambda: {"B12345678": "Olya", "B87654321": "Analia"},
    )

    result = service.actualizar_responsables_desde_a3(
        gestor, "Administrador",
    )

    assert result.clientes_a3 == 2
    assert result.clientes_internos == 1
    assert result.filas_actualizadas == 4
    assert gestor.get_empresa("E00001", 2026)["responsable"] == "Olya"
    assert gestor.get_empresa("E00002", 2026)["responsable"] == "Administrador"
