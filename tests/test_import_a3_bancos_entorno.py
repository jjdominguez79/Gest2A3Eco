from pathlib import Path

from services import import_a3_empresa as servicio


def _archivo_isam(registros: list[bytes]) -> bytes:
    return bytes(128) + b"".join(registros)


def _registro_cliente(nif: str, cliente_id: int) -> bytes:
    rec = bytearray(b" " * 1028)
    rec[0] = 0x44
    rec[42:51] = nif.encode("cp1252").ljust(9)
    rec[56:60] = cliente_id.to_bytes(4, "big")
    return bytes(rec)


def _registro_banco(
    cliente_id: int,
    iban: str,
    *,
    descripcion: str = "",
    principal: bool = False,
    no_activa: bool = False,
) -> bytes:
    rec = bytearray(b" " * 304)
    rec[0] = 0x41
    rec[4:6] = cliente_id.to_bytes(2, "big")
    rec[10:30] = iban[4:].encode("ascii").ljust(20)
    rec[30:70] = descripcion.encode("cp1252").ljust(40)
    rec[70:150] = b"Oficina principal".ljust(80)
    rec[150:151] = b"S" if principal else b"N"
    rec[151:152] = b"S" if no_activa else b"N"
    rec[152:186] = iban.encode("ascii").ljust(34)
    rec[192:203] = b"CAIXESBBXXX"
    return bytes(rec)


def test_lee_cuentas_del_cliente_desde_a3entorno(tmp_path: Path, monkeypatch):
    cli = tmp_path / "ASECLI.DAT"
    ccc = tmp_path / "ASECCC.DAT"
    cli.write_bytes(
        _archivo_isam(
            [
                _registro_cliente("B12345678", 25),
                _registro_cliente("A87654321", 30),
            ]
        )
    )
    ccc.write_bytes(
        _archivo_isam(
            [
                _registro_banco(25, "ES9121000418450200051332", descripcion="Cuenta operativa"),
                _registro_banco(
                    25,
                    "ES6621000418401234567891",
                    descripcion="Cuenta principal",
                    principal=True,
                ),
                _registro_banco(
                    25,
                    "ES0721000418031234567890",
                    descripcion="Cuenta antigua",
                    no_activa=True,
                ),
                _registro_banco(30, "ES7921000813610123456789"),
            ]
        )
    )
    monkeypatch.setattr(servicio, "_candidate_entorno_bank_paths", lambda: [(cli, ccc)])

    cuentas, origen = servicio._leer_cuentas_bancarias_entorno("B-12345678")

    assert origen == str(ccc)
    assert [c["descripcion"] for c in cuentas] == ["Cuenta principal", "Cuenta operativa"]
    assert cuentas[0]["principal"] is True
    assert cuentas[0]["iban"] == "ES6621000418401234567891"
    assert cuentas[0]["bic"] == "CAIXESBBXXX"
    assert all(c["origen"] == "a3_entorno" for c in cuentas)


def test_sin_nif_no_asigna_cuentas_de_otro_cliente(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(servicio, "_candidate_entorno_bank_paths", lambda: [])

    assert servicio._leer_cuentas_bancarias_entorno("") == ([], "")

