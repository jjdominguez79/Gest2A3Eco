"""
Tests del modulo Notificaciones Electronicas.

Cubre CRUD de certificados, organismos y buzones, y la maquina de estados
de la bandeja. Usa SQLite en memoria temporal; no importa app_controller.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from models.gestor_sqlite import GestorSQLite


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gestor(tmp_path: Path) -> GestorSQLite:
    return GestorSQLite(tmp_path / "notif_test.db")


EMPRESA = "T001"
EJERCICIO = 2026


# ── Certificados ──────────────────────────────────────────────────────────────

def test_crear_certificado(tmp_path):
    g = _gestor(tmp_path)
    g.upsert_notif_certificado({
        "codigo_empresa": EMPRESA,
        "nombre": "Cert AEAT",
        "nif_titular": "B12345678",
        "tipo": "PFX",
        "fecha_emision":   "2024-01-01",
        "fecha_caducidad": "2027-01-01",
        "activo": 1,
    })
    rows = g.listar_notif_certificados(EMPRESA)
    assert len(rows) == 1
    assert rows[0]["nombre"] == "Cert AEAT"
    assert rows[0]["nif_titular"] == "B12345678"


def test_editar_certificado(tmp_path):
    g = _gestor(tmp_path)
    g.upsert_notif_certificado({
        "codigo_empresa": EMPRESA,
        "nombre": "Cert Original",
        "nif_titular": "B12345678",
        "tipo": "PFX",
        "activo": 1,
    })
    cert_id = g.listar_notif_certificados(EMPRESA)[0]["id"]
    g.upsert_notif_certificado({
        "id": cert_id,
        "codigo_empresa": EMPRESA,
        "nombre": "Cert Editado",
        "nif_titular": "B12345678",
        "tipo": "P12",
        "activo": 1,
    })
    cert = g.get_notif_certificado(cert_id)
    assert cert["nombre"] == "Cert Editado"
    assert cert["tipo"] == "P12"


def test_eliminar_certificado(tmp_path):
    g = _gestor(tmp_path)
    g.upsert_notif_certificado({
        "codigo_empresa": EMPRESA,
        "nombre": "Cert Temporal",
        "nif_titular": "B12345678",
        "tipo": "PFX",
        "activo": 1,
    })
    cert_id = g.listar_notif_certificados(EMPRESA)[0]["id"]
    g.eliminar_notif_certificado(EMPRESA, cert_id)
    assert g.listar_notif_certificados(EMPRESA) == []


def test_listar_certificados_solo_activos(tmp_path):
    g = _gestor(tmp_path)
    g.upsert_notif_certificado({"codigo_empresa": EMPRESA, "nombre": "Activo",   "nif_titular": "B00000001", "tipo": "PFX", "activo": 1})
    g.upsert_notif_certificado({"codigo_empresa": EMPRESA, "nombre": "Inactivo", "nif_titular": "B00000002", "tipo": "PFX", "activo": 0})
    todos   = g.listar_notif_certificados(EMPRESA)
    activos = g.listar_notif_certificados(EMPRESA, solo_activos=True)
    assert len(todos)   == 2
    assert len(activos) == 1
    assert activos[0]["nombre"] == "Activo"


# ── Organismos ────────────────────────────────────────────────────────────────

def test_crear_organismo(tmp_path):
    g = _gestor(tmp_path)
    g.upsert_notif_organismo({
        "codigo": "DEHU",
        "nombre": "Direccion Electronica Habilitada unica",
        "tipo":   "ESTATAL",
        "activo": 1,
    })
    rows = g.listar_notif_organismos()
    assert [r["codigo"] for r in rows] == ["DEHU"]


def test_editar_organismo(tmp_path):
    g = _gestor(tmp_path)
    g.upsert_notif_organismo({"codigo": "DEHU", "nombre": "DEHu", "tipo": "ESTATAL", "activo": 1})
    org_id = next(r["id"] for r in g.listar_notif_organismos() if r["codigo"] == "DEHU")
    g.upsert_notif_organismo({"id": org_id, "codigo": "DEHU", "nombre": "DEHu Editada", "tipo": "ESTATAL", "activo": 1})
    org = g.get_notif_organismo(org_id)
    assert org["nombre"] == "DEHu Editada"


def test_rechaza_organismo_distinto_de_dehu(tmp_path):
    g = _gestor(tmp_path)
    with pytest.raises(ValueError, match="DEHu"):
        g.upsert_notif_organismo({"codigo": "TGSS", "nombre": "TGSS", "activo": 1})


def test_listar_organismos_solo_activos(tmp_path):
    g = _gestor(tmp_path)
    g.upsert_notif_organismo({"codigo": "DEHU", "nombre": "DEHu", "tipo": "ESTATAL", "activo": 1})
    todos   = g.listar_notif_organismos()
    activos = g.listar_notif_organismos(solo_activos=True)
    assert len(todos) == 1
    assert all(r["activo"] for r in activos)


# ── Buzones ───────────────────────────────────────────────────────────────────

def _crear_organismo_y_cert(g: GestorSQLite) -> tuple[int, int | None]:
    """Devuelve (organismo_id, cert_id) para usar en buzones."""
    g.upsert_notif_organismo({"codigo": "DEHU", "nombre": "DEHu", "tipo": "ESTATAL", "activo": 1})
    org_id = next(r["id"] for r in g.listar_notif_organismos() if r["codigo"] == "DEHU")
    g.upsert_notif_certificado({"codigo_empresa": EMPRESA, "nombre": "Cert SS", "nif_titular": "B99999999", "tipo": "PFX", "activo": 1})
    cert_id = g.listar_notif_certificados(EMPRESA)[0]["id"]
    return org_id, cert_id


def test_crear_buzon(tmp_path):
    g = _gestor(tmp_path)
    org_id, cert_id = _crear_organismo_y_cert(g)
    g.upsert_notif_buzon({
        "codigo_empresa": EMPRESA,
        "nombre":         "DEHu",
        "organismo_id":   org_id,
        "tipo_buzon":     "DEHU",
        "nif_titular":    "B99999999",
        "certificado_id": cert_id,
        "activo":         1,
    })
    rows = g.listar_notif_buzones(EMPRESA)
    assert len(rows) == 1
    assert rows[0]["nombre"] == "DEHu"


def test_editar_buzon(tmp_path):
    g = _gestor(tmp_path)
    org_id, cert_id = _crear_organismo_y_cert(g)
    g.upsert_notif_buzon({"codigo_empresa": EMPRESA, "nombre": "DEHu", "organismo_id": org_id, "tipo_buzon": "DEHU", "activo": 1})
    buzon_id = g.listar_notif_buzones(EMPRESA)[0]["id"]
    g.upsert_notif_buzon({"id": buzon_id, "codigo_empresa": EMPRESA, "nombre": "DEHu Editada", "organismo_id": org_id, "tipo_buzon": "DEHU", "activo": 1})
    buzon = g.get_notif_buzon(buzon_id)
    assert buzon["nombre"] == "DEHu Editada"
    assert buzon["tipo_buzon"] == "DEHU"


def test_eliminar_buzon(tmp_path):
    g = _gestor(tmp_path)
    org_id, _ = _crear_organismo_y_cert(g)
    g.upsert_notif_buzon({"codigo_empresa": EMPRESA, "nombre": "DEHu", "organismo_id": org_id, "tipo_buzon": "DEHU", "activo": 1})
    buzon_id = g.listar_notif_buzones(EMPRESA)[0]["id"]
    g.eliminar_notif_buzon(EMPRESA, buzon_id)
    assert g.listar_notif_buzones(EMPRESA) == []


# ── Bandeja — maquina de estados ─────────────────────────────────────────────

import uuid


def _insertar_notif(g: GestorSQLite, estado: str = "PENDIENTE") -> str:
    """Inserta un item en notif_bandeja y devuelve su id."""
    item_id = str(uuid.uuid4())
    now = "2026-06-10T10:00:00"
    g.conn.execute(
        """INSERT INTO notif_bandeja
           (id, codigo_empresa, ejercicio, asunto, estado, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (item_id, EMPRESA, EJERCICIO, "Notif test", estado, now, now),
    )
    g.conn.commit()
    return item_id


def test_bandeja_pendiente_a_aceptada(tmp_path):
    g = _gestor(tmp_path)
    item_id = _insertar_notif(g)
    g.cambiar_estado_notif_bandeja(EMPRESA, item_id, "ACEPTADA", "2026-06-10")
    item = g.get_notif_bandeja_item(item_id)
    assert item["estado"] == "ACEPTADA"
    assert item["fecha_aceptacion"] == "2026-06-10"


def test_bandeja_pendiente_a_rechazada(tmp_path):
    g = _gestor(tmp_path)
    item_id = _insertar_notif(g)
    g.cambiar_estado_notif_bandeja(EMPRESA, item_id, "RECHAZADA", "2026-06-10")
    item = g.get_notif_bandeja_item(item_id)
    assert item["estado"] == "RECHAZADA"
    assert item["fecha_rechazo"] == "2026-06-10"


def test_bandeja_eliminar_item(tmp_path):
    g = _gestor(tmp_path)
    item_id = _insertar_notif(g)
    g.eliminar_notif_bandeja_item(EMPRESA, item_id)
    assert g.get_notif_bandeja_item(item_id) is None


def test_bandeja_listar_filtra_por_empresa(tmp_path):
    g = _gestor(tmp_path)
    id1 = _insertar_notif(g, "PENDIENTE")
    # Segunda empresa — no debe aparecer al listar T001
    now = "2026-06-10T10:00:00"
    g.conn.execute(
        "INSERT INTO notif_bandeja (id, codigo_empresa, ejercicio, asunto, estado, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), "OTRA", EJERCICIO, "Otra empresa", "PENDIENTE", now, now),
    )
    g.conn.commit()
    rows = g.listar_notif_bandeja(EMPRESA, EJERCICIO)
    assert all(r["codigo_empresa"] == EMPRESA for r in rows)
    assert any(r["id"] == id1 for r in rows)


def test_bandeja_estado_vencida(tmp_path):
    g = _gestor(tmp_path)
    item_id = _insertar_notif(g, "VENCIDA")
    rows = g.listar_notif_bandeja(EMPRESA, EJERCICIO)
    assert any(r["id"] == item_id and r["estado"] == "VENCIDA" for r in rows)


# ── Migracion: indice en notif_buzones.organismo_id existe ───────────────────

def test_indice_notif_buzones_organismo_existe(tmp_path):
    g = _gestor(tmp_path)
    indices = {
        r[1]
        for r in g.conn.execute(
            "SELECT type, name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert "idx_notif_buzones_organismo" in indices


def test_migracion_conserva_historico_y_deja_un_solo_dehu(tmp_path):
    g = _gestor(tmp_path)
    now = "2026-07-25T12:00:00"
    g.conn.execute(
        """INSERT INTO notif_organismos
           (codigo,nombre,tipo,activo,created_at,updated_at)
           VALUES ('TGSS','TGSS','ESTATAL',1,?,?)""",
        (now, now),
    )
    org_id = g.conn.execute(
        "SELECT id FROM notif_organismos WHERE codigo='TGSS'"
    ).fetchone()[0]
    g.conn.execute(
        """INSERT INTO notif_buzones
           (id,codigo_empresa,nombre,organismo_id,tipo_buzon,activo,created_at,updated_at)
           VALUES ('b-tgss',?,'TGSS',?,'DEH',1,?,?)""",
        (EMPRESA, org_id, now, now),
    )
    g.conn.execute(
        """INSERT INTO notif_bandeja
           (id,codigo_empresa,ejercicio,buzon_id,organismo_id,asunto,estado,created_at,updated_at)
           VALUES ('n-tgss',?,?,'b-tgss',?,'Notificacion historica','PENDIENTE',?,?)""",
        (EMPRESA, EJERCICIO, org_id, now, now),
    )
    g.conn.commit()

    g.asegurar_dehu_unico()

    assert [o["codigo"] for o in g.listar_notif_organismos()] == ["DEHU"]
    buzones = g.listar_notif_buzones(EMPRESA)
    assert len(buzones) == 1
    assert buzones[0]["organismo_codigo"] == "DEHU"
    assert buzones[0]["tipo_buzon"] == "DEHU"
    historico = g.get_notif_bandeja_item("n-tgss")
    assert historico is not None
    assert historico["organismo_codigo"] == "DEHU"
    assert historico["buzon_id"] == buzones[0]["id"]


# ── Migracion: tablas del modulo existen ─────────────────────────────────────

def test_tablas_notificaciones_existen(tmp_path):
    g = _gestor(tmp_path)
    tablas = {
        r[0]
        for r in g.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for tabla in ("notificaciones", "notificaciones_config",
                  "notif_certificados", "notif_organismos",
                  "notif_buzones", "notif_bandeja"):
        assert tabla in tablas, f"Tabla '{tabla}' no existe"
