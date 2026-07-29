import services.import_a3_empresa as import_a3
from services.import_a3_empresa import _buscar_responsable_a3eco, _leer_responsable_entorno
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

    supervisor = _record(2604, 0x4A)
    supervisor[2:6] = (1).to_bytes(4, "big")
    supervisor[6:36] = b"Supervisor".ljust(30)
    otro_usuario = _record(2604, 0x4A)
    otro_usuario[2:6] = (11).to_bytes(4, "big")
    otro_usuario[6:36] = b"OTRA PERSONA".ljust(30)

    eco = _record(516, 0x22)
    eco[2:6] = (1).to_bytes(4, "big")
    eco[6:16] = b"ECO       "
    eco[32:36] = cliente_id.to_bytes(4, "big")
    eco[36:40] = (6).to_bytes(4, "big")
    eco_secundario = _record(516, 0x42)
    eco_secundario[2:6] = (11).to_bytes(4, "big")
    eco_secundario[6:16] = b"ECO       "
    eco_secundario[32:36] = cliente_id.to_bytes(4, "big")
    eco_secundario[36:40] = (8).to_bytes(4, "big")

    cli_path = tmp_path / "ASECLI.DAT"
    respo_path = tmp_path / "ASERESPO.DAT"
    usr_path = tmp_path / "ASEUSR.DAT"
    cli_path.write_bytes(bytes(128) + cli)
    respo_path.write_bytes(bytes(128) + eco_secundario + eco)
    usr_path.write_bytes(bytes(128) + supervisor + otro_usuario)

    assert _leer_responsable_entorno(
        "B-12345678", cli_path, respo_path, usr_path
    ) == "Supervisor"


def test_responsable_no_coincide_con_otro_cliente(tmp_path):
    cli = _record(1028, 0x44)
    cli[42:56] = b" B12345678    "
    cli[56:60] = (10).to_bytes(4, "big")

    usuario = _record(2604, 0x4A)
    usuario[2:6] = (11).to_bytes(4, "big")
    usuario[6:36] = b"OTRA PERSONA".ljust(30)
    eco = _record(516, 0x42)
    eco[2:6] = (11).to_bytes(4, "big")
    eco[6:16] = b"ECO       "
    eco[32:36] = (11).to_bytes(4, "big")
    eco[36:40] = (1).to_bytes(4, "big")

    cli_path = tmp_path / "ASECLI.DAT"
    respo_path = tmp_path / "ASERESPO.DAT"
    usr_path = tmp_path / "ASEUSR.DAT"
    cli_path.write_bytes(bytes(128) + cli)
    respo_path.write_bytes(bytes(128) + eco)
    usr_path.write_bytes(bytes(128) + usuario)

    assert _leer_responsable_entorno(
        "B12345678", cli_path, respo_path, usr_path
    ) == ""


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


def test_buscar_responsable_usa_ges_si_no_hay_asignacion_eco(tmp_path, monkeypatch):
    cliente_id = 209
    cli = _record(1028, 0x44)
    cli[42:56] = b" B39821350    "
    cli[56:60] = cliente_id.to_bytes(4, "big")

    usuario = _record(2604, 0x4A)
    usuario[2:6] = (1).to_bytes(4, "big")
    usuario[6:36] = b"Supervisor".ljust(30)

    ges = _record(516, 0x42)
    ges[2:6] = (1).to_bytes(4, "big")
    ges[6:16] = b"GES       "
    ges[32:36] = cliente_id.to_bytes(4, "big")
    ges[36:40] = (6).to_bytes(4, "big")

    cli_path = tmp_path / "ASECLI.DAT"
    respo_path = tmp_path / "ASERESPO.DAT"
    usr_path = tmp_path / "ASEUSR.DAT"
    cli_path.write_bytes(bytes(128) + cli)
    respo_path.write_bytes(bytes(128) + ges)
    usr_path.write_bytes(bytes(128) + usuario)
    monkeypatch.setattr(
        import_a3,
        "_candidate_entorno_responsable_paths",
        lambda: [(cli_path, respo_path, usr_path)],
    )

    assert _buscar_responsable_a3eco("B39821350")[0] == "Supervisor"
