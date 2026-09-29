from pathlib import Path

from services import import_a3_empresa
from services.import_a3_empresa import _year_from_cu_path


def test_ejercicio_sin_fichero_cu_devuelve_none():
    assert _year_from_cu_path(None) is None


def test_ejercicio_se_extrae_del_nombre_cu():
    assert _year_from_cu_path(Path("000866CU.DAT")) == 2026


def _write_records(path: Path, records: list[bytes]) -> None:
    path.write_bytes(bytes(128) + b"".join(records))


def test_importa_responsables_masivamente_con_prioridad_eco(monkeypatch, tmp_path):
    cli_path = tmp_path / "ASECLI.DAT"
    respo_path = tmp_path / "ASERESPO.DAT"
    usr_path = tmp_path / "ASEUSR.DAT"

    clientes = []
    for nif, cliente_id in (("B12345678", 11), ("A87654321", 22)):
        record = bytearray(1028)
        record[42:56] = nif.encode("cp1252").ljust(14)
        record[56:60] = cliente_id.to_bytes(4, "big")
        clientes.append(bytes(record))
    _write_records(cli_path, clientes)

    usuarios = []
    for usuario_id, nombre in ((3, "Responsable ECO"), (4, "Responsable GES")):
        record = bytearray(2604)
        record[0] = 0x4A
        record[2:6] = usuario_id.to_bytes(4, "big")
        record[6:36] = nombre.encode("cp1252").ljust(30)
        usuarios.append(bytes(record))
    _write_records(usr_path, usuarios)

    asignaciones = []
    for usuario_id, aplicacion, cliente_id, orden in (
        (4, "GES", 11, 1),
        (3, "ECO", 11, 2),
        (4, "GES", 22, 1),
    ):
        record = bytearray(516)
        record[0] = 0x22
        record[2:6] = usuario_id.to_bytes(4, "big")
        record[6:16] = aplicacion.encode("cp1252").ljust(10)
        record[32:36] = cliente_id.to_bytes(4, "big")
        record[36:40] = orden.to_bytes(4, "big")
        asignaciones.append(bytes(record))
    _write_records(respo_path, asignaciones)

    monkeypatch.setattr(
        import_a3_empresa,
        "_candidate_entorno_responsable_paths",
        lambda: [(cli_path, respo_path, usr_path)],
    )

    assert import_a3_empresa.importar_responsables_a3eco() == {
        "B12345678": "Responsable ECO",
        "A87654321": "Responsable GES",
    }
