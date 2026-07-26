from services.import_a3_empresa import _leer_responsable_entorno
from models.gestor_sqlite import GestorSQLite


def _record(size: int, marker: int = 0x41) -> bytearray:
    row = bytearray(b" " * size)
    row[0] = marker
    return row


def test_lee_solo_responsable_de_aplicacion_eco(tmp_path):
    cliente_id = 445
    cli = _record(1028, 0x44)
    cli[42:56] = b" B12345678    "
    cli[56:60] = cliente_id.to_bytes(4, "big")

    ges = _record(260)
    ges[2:6] = cliente_id.to_bytes(4, "big")
    ges[6:16] = b"GES       "
    ges[34:74] = b"RESPONSABLE GES".ljust(40)

    eco = _record(260)
    eco[2:6] = cliente_id.to_bytes(4, "big")
    eco[6:16] = b"ECO       "
    eco[34:74] = b"LOPEZ ROYANO, MARTA".ljust(40)

    cli_path = tmp_path / "ASECLI.DAT"
    apl_path = tmp_path / "ASECLAPL.DAT"
    cli_path.write_bytes(bytes(128) + cli)
    apl_path.write_bytes(bytes(128) + ges + eco)

    assert _leer_responsable_entorno("B-12345678", cli_path, apl_path) == "LOPEZ ROYANO, MARTA"


def test_responsable_no_coincide_con_otro_cliente(tmp_path):
    cli = _record(1028, 0x44)
    cli[42:56] = b" B12345678    "
    cli[56:60] = (10).to_bytes(4, "big")

    eco = _record(260)
    eco[2:6] = (11).to_bytes(4, "big")
    eco[6:16] = b"ECO       "
    eco[34:74] = b"OTRA PERSONA".ljust(40)

    cli_path = tmp_path / "ASECLI.DAT"
    apl_path = tmp_path / "ASECLAPL.DAT"
    cli_path.write_bytes(bytes(128) + cli)
    apl_path.write_bytes(bytes(128) + eco)

    assert _leer_responsable_entorno("B12345678", cli_path, apl_path) == ""


def test_responsable_se_persiste_en_empresa(tmp_path):
    gestor = GestorSQLite(tmp_path / "gestor.db")
    gestor.upsert_empresa({
        "codigo": "E00123",
        "ejercicio": 2026,
        "nombre": "Empresa",
        "digitos_plan": 8,
        "responsable": "MARTA LOPEZ",
    })

    assert gestor.get_empresa("E00123", 2026)["responsable"] == "MARTA LOPEZ"
