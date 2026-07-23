"""Tests para la lectura de la referencia interna desde ficheros A3ECO (*A.DAT).

Cubre los dos modos de codificacion:
  - Mensual : 4 bytes big-endian en bytes 110-113 = MES*1_000_000 + SEQ
              se devuelve como "MM/NNNNN" (ej. "05/00007")
  - Anual   : 2 bytes big-endian en bytes 110-111 (fallback cuando el campo
              de 4 bytes no codifica un mes valido)
              se devuelve como cadena simple (ej. "15")

Los ficheros binarios se construyen en memoria; no se necesita A3ECO instalado.
"""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

from services.import_a3_empresa import (
    _detectar_modo_numeracion,
    _mes_desde_nombre_fichero,
    leer_numero_asiento_desde_a3,
)

# ─── helpers para construir ficheros binarios sinteticos ─────────────────────

_ISAM_HEADER_SIZE = 128
_REC_SIZE = 132  # tamano total de registro (incluye 4 bytes de overhead ISAM)
_PAYLOAD_SIZE = _REC_SIZE - 4  # 128


def _make_isam_header(payload_size: int = _PAYLOAD_SIZE) -> bytes:
    header = bytearray(_ISAM_HEADER_SIZE)
    struct.pack_into(">I", header, 54, payload_size)
    return bytes(header)


def _ref_mensual(mes: int, seq: int) -> int:
    """Codificacion 4 bytes de referencia interna mensual: MES*1_000_000 + SEQ."""
    return mes * 1_000_000 + seq


def _make_record(
    num_fra: str,
    concepto: str,
    asiento: int = 0,
    active: bool = True,
    apunte_offset: int = 110,
    ref_interna: int | None = None,
) -> bytes:
    """Construye un registro de 132 bytes con los campos minimos necesarios.

    Si ref_interna no es None, se codifica como 4 bytes big-endian en bytes 110-113
    (formato mensual). En caso contrario se usa asiento como 2 bytes big-endian
    en apunte_offset (formato anual / fallback).

    Los campos de texto se rellenan con espacios (como en A3ECO real) para que
    strip() funcione correctamente al leer.
    """
    rec = bytearray(_REC_SIZE)
    rec[0] = 0x40 if active else 0x00
    # campo num_fra: bytes 45-54 (10 chars cp850, relleno con espacios)
    encoded_fra = num_fra.encode("cp850", errors="replace")[:10].ljust(10, b" ")
    rec[45:55] = encoded_fra
    # campo concepto: bytes 15-44 (30 chars cp850, relleno con espacios)
    encoded_con = concepto.encode("cp850", errors="replace")[:30].ljust(30, b" ")
    rec[15:45] = encoded_con
    if ref_interna is not None:
        struct.pack_into(">I", rec, 110, ref_interna)
    else:
        struct.pack_into(">H", rec, apunte_offset, asiento)
    return bytes(rec)


def _make_dat_file(records: list[bytes]) -> bytes:
    return _make_isam_header() + b"".join(records)


def _write_dat(tmp_path: Path, codigo_norm: str, ej_digit: str, mes_cod: str, records: list[bytes]) -> Path:
    path = tmp_path / f"{codigo_norm}{ej_digit}{mes_cod}A.DAT"
    path.write_bytes(_make_dat_file(records))
    return path


# ─── tests: _mes_desde_nombre_fichero ────────────────────────────────────────

@pytest.mark.parametrize("filename,expected", [
    ("E0042361A.DAT", None),   # .DAT en el stem
    ("E0042361A", 1),          # enero
    ("E0042369A", 9),          # septiembre
    ("E004236OA", 10),         # octubre: "O" → 10
    ("E004236 1A", 1),         # espacio en stem: penultimo "1" → mes 1
])
def test_mes_desde_nombre_fichero_stem(filename: str, expected: int | None):
    path = Path(f"{filename}.DAT")
    result = _mes_desde_nombre_fichero(path)
    assert result == expected


@pytest.mark.parametrize("stem,expected", [
    ("E0042361A", 1),
    ("E0042362A", 2),
    ("E0042369A", 9),
    ("E004236OA", 10),   # octubre
    ("E004236NA", 11),   # noviembre
    ("E004236DA", 12),   # diciembre
    ("E004236IA", None), # cierre anual, sin mes
])
def test_mes_desde_nombre_fichero_todos_meses(stem: str, expected: int | None):
    path = Path(stem + ".DAT")
    assert _mes_desde_nombre_fichero(path) == expected


# ─── tests: _detectar_modo_numeracion ────────────────────────────────────────

def test_detectar_modo_anual(tmp_path, monkeypatch):
    """Numeros correlativos sin repeticion entre meses → anual."""
    codigo_norm = "00423"
    ej_digit = "6"

    _write_dat(tmp_path, codigo_norm, ej_digit, "1", [
        _make_record("FRA001", "Concepto A", 1),
        _make_record("FRA002", "Concepto B", 2),
    ])
    _write_dat(tmp_path, codigo_norm, ej_digit, "2", [
        _make_record("FRA003", "Concepto C", 3),
        _make_record("FRA004", "Concepto D", 4),
    ])

    monkeypatch.setattr(
        "services.import_a3_empresa._candidate_dirs",
        lambda codigo: [tmp_path],
    )

    assert _detectar_modo_numeracion(codigo_norm, 2026) == "anual"


def test_detectar_modo_mensual(tmp_path, monkeypatch):
    """Mismo numero en meses distintos → mensual."""
    codigo_norm = "00841"
    ej_digit = "6"

    _write_dat(tmp_path, codigo_norm, ej_digit, "1", [
        _make_record("FRA001", "Concepto A", 1),
        _make_record("FRA002", "Concepto B", 2),
    ])
    _write_dat(tmp_path, codigo_norm, ej_digit, "2", [
        _make_record("FRA003", "Concepto C", 1),
        _make_record("FRA004", "Concepto D", 2),
    ])

    monkeypatch.setattr(
        "services.import_a3_empresa._candidate_dirs",
        lambda codigo: [tmp_path],
    )

    assert _detectar_modo_numeracion(codigo_norm, 2026) == "mensual"


def test_detectar_modo_sin_ficheros(tmp_path, monkeypatch):
    """Sin ficheros disponibles → anual (valor por defecto seguro)."""
    monkeypatch.setattr(
        "services.import_a3_empresa._candidate_dirs",
        lambda codigo: [tmp_path],
    )
    assert _detectar_modo_numeracion("99999", 2026) == "anual"


# ─── tests: leer_numero_asiento_desde_a3 — referencia interna mensual ────────

def test_mensual_ref_interna_mayo(tmp_path, monkeypatch):
    """Caso real empresa 8: FRA A000007 mayo → ref. interna 5*1_000_000+7 → '05/00007'."""
    codigo_norm = "00841"
    ej_digit = "6"

    _write_dat(tmp_path, codigo_norm, ej_digit, "1", [
        _make_record("A000007", "Mayo venta", ref_interna=_ref_mensual(5, 7)),
    ])

    monkeypatch.setattr(
        "services.import_a3_empresa._candidate_dirs",
        lambda codigo: [tmp_path],
    )

    result = leer_numero_asiento_desde_a3(f"E{codigo_norm}", 2026, "A000007", mes=5)
    assert result == "05/00007"


def test_mensual_enero_seq1(tmp_path, monkeypatch):
    """Enero, secuencial 1 → '01/00001'."""
    codigo_norm = "00841"
    ej_digit = "6"

    _write_dat(tmp_path, codigo_norm, ej_digit, "1", [
        _make_record("FRA001", "Enero venta", ref_interna=_ref_mensual(1, 1)),
    ])

    monkeypatch.setattr(
        "services.import_a3_empresa._candidate_dirs",
        lambda codigo: [tmp_path],
    )

    result = leer_numero_asiento_desde_a3(f"E{codigo_norm}", 2026, "FRA001", mes=1)
    assert result == "01/00001"


def test_mensual_octubre_seq42(tmp_path, monkeypatch):
    """Octubre, secuencial 42 → '10/00042'."""
    codigo_norm = "00841"
    ej_digit = "6"

    _write_dat(tmp_path, codigo_norm, ej_digit, "O", [
        _make_record("FRA042", "Octubre 42", ref_interna=_ref_mensual(10, 42)),
    ])

    monkeypatch.setattr(
        "services.import_a3_empresa._candidate_dirs",
        lambda codigo: [tmp_path],
    )

    result = leer_numero_asiento_desde_a3(f"E{codigo_norm}", 2026, "FRA042", mes=10)
    assert result == "10/00042"


def test_mensual_dos_facturas_mismo_seq_distinto_mes(tmp_path, monkeypatch):
    """FRA001 en enero seq=1 y FRA002 en febrero seq=1 dan claves distintas."""
    codigo_norm = "00841"
    ej_digit = "6"

    _write_dat(tmp_path, codigo_norm, ej_digit, "1", [
        _make_record("FRA001", "Enero", ref_interna=_ref_mensual(1, 1)),
    ])
    _write_dat(tmp_path, codigo_norm, ej_digit, "2", [
        _make_record("FRA002", "Febrero", ref_interna=_ref_mensual(2, 1)),
    ])

    monkeypatch.setattr(
        "services.import_a3_empresa._candidate_dirs",
        lambda codigo: [tmp_path],
    )

    r1 = leer_numero_asiento_desde_a3(f"E{codigo_norm}", 2026, "FRA001", mes=1)
    r2 = leer_numero_asiento_desde_a3(f"E{codigo_norm}", 2026, "FRA002", mes=2)
    assert r1 == "01/00001"
    assert r2 == "02/00001"
    assert r1 != r2


# ─── tests: leer_numero_asiento_desde_a3 — referencia anual (fallback) ───────

def test_anual_devuelve_numero_sin_barra(tmp_path, monkeypatch):
    """Modo anual: 2 bytes big-endian que no codifican mes valido → numero simple."""
    codigo_norm = "00423"
    ej_digit = "6"

    # asiento=15 → bytes 110-111=0x000F, bytes 112-113=0x0000
    # valor4 = 0x000F0000 = 983040 → mes_ref=0 → fallback → "15"
    _write_dat(tmp_path, codigo_norm, ej_digit, "1", [
        _make_record("FRA001", "Concepto A", asiento=15),
        _make_record("FRA002", "Concepto B", asiento=16),
    ])
    _write_dat(tmp_path, codigo_norm, ej_digit, "2", [
        _make_record("FRA003", "Concepto C", asiento=17),
    ])

    monkeypatch.setattr(
        "services.import_a3_empresa._candidate_dirs",
        lambda codigo: [tmp_path],
    )

    result = leer_numero_asiento_desde_a3(f"E{codigo_norm}", 2026, "FRA001")
    assert result == "15"


def test_anual_no_encontrado_devuelve_none(tmp_path, monkeypatch):
    """Si la factura no esta en ningun fichero, retorna None."""
    codigo_norm = "00423"
    ej_digit = "6"

    _write_dat(tmp_path, codigo_norm, ej_digit, "1", [
        _make_record("FRA001", "Concepto", asiento=5),
    ])

    monkeypatch.setattr(
        "services.import_a3_empresa._candidate_dirs",
        lambda codigo: [tmp_path],
    )

    assert leer_numero_asiento_desde_a3(f"E{codigo_norm}", 2026, "INEXISTENTE") is None


def test_fallback_por_concepto(tmp_path, monkeypatch):
    """Si num_factura no coincide, busca por los primeros 10 chars del concepto."""
    codigo_norm = "00423"
    ej_digit = "6"

    _write_dat(tmp_path, codigo_norm, ej_digit, "3", [
        _make_record("", "MARZO VENTA X S.L.", asiento=7),
    ])

    monkeypatch.setattr(
        "services.import_a3_empresa._candidate_dirs",
        lambda codigo: [tmp_path],
    )

    result = leer_numero_asiento_desde_a3(
        f"E{codigo_norm}", 2026, num_factura="", descripcion="MARZO VENTA X S.L."
    )
    assert result == "7"
