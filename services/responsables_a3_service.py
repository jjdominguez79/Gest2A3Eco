from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from services import import_a3_empresa as a3


@dataclass(frozen=True)
class ResponsablesImportSummary:
    clientes_a3: int
    clientes_internos: int
    filas_actualizadas: int
    sin_asignacion_a3: int
    distribucion: dict[str, int]


def es_cliente_interno(empresa: dict) -> bool:
    emails = {
        part.strip().lower()
        for part in re.split(r"[,;]", str(empresa.get("email") or ""))
        if part.strip()
    }
    return any(email.endswith("@gestinem.es") for email in emails)


def _leer_mapa_responsables() -> dict[str, str]:
    paths = next(
        (
            triple for triple in a3._candidate_entorno_responsable_paths()
            if all(path.exists() for path in triple)
        ),
        None,
    )
    if paths is None:
        raise FileNotFoundError("No se encuentran los maestros de responsables de A3ENTORNO.")
    cli_path, respo_path, usr_path = paths
    cli_data = cli_path.read_bytes()
    respo_data = respo_path.read_bytes()
    usr_data = usr_path.read_bytes()

    usuarios = {}
    for offset in range(
        a3._ISAM_HEADER, len(usr_data) - a3._ASEUSR_REC_SIZE + 1,
        a3._ASEUSR_REC_SIZE,
    ):
        record = usr_data[offset: offset + a3._ASEUSR_REC_SIZE]
        if record[0] != a3._ASEUSR_MARKER:
            continue
        user_id = int.from_bytes(record[a3._ASEUSR_ID], "big")
        nombre = " ".join(
            record[a3._ASEUSR_NOMBRE]
            .decode(a3._A3_ENCODING, errors="ignore").strip().split()
        )
        if user_id and nombre:
            usuarios[user_id] = nombre

    cliente_nif = {}
    for offset in range(
        a3._ISAM_HEADER, len(cli_data) - a3._ASECLI_REC_SIZE + 1,
        a3._ASECLI_REC_SIZE,
    ):
        record = cli_data[offset: offset + a3._ASECLI_REC_SIZE]
        nif = a3._normalizar_nif_a3(
            record[a3._ASECLI_NIF].decode(a3._A3_ENCODING, errors="ignore")
        )
        client_id = int.from_bytes(record[a3._ASECLI_ID], "big")
        if nif and client_id:
            cliente_nif[client_id] = nif

    candidatos = {}
    for offset in range(
        a3._ISAM_HEADER, len(respo_data) - a3._ASERESPO_REC_SIZE + 1,
        a3._ASERESPO_REC_SIZE,
    ):
        record = respo_data[offset: offset + a3._ASERESPO_REC_SIZE]
        if record[0] not in a3._ASERESPO_MARKERS:
            continue
        client_id = int.from_bytes(record[a3._ASERESPO_CLIENT_ID], "big")
        application = (
            record[a3._ASERESPO_APP]
            .decode(a3._A3_ENCODING, errors="ignore").strip().upper()
        )
        user_id = int.from_bytes(record[a3._ASERESPO_USUARIO_ID], "big")
        order = int.from_bytes(record[a3._ASERESPO_ORDEN], "big")
        if application != "ECO" or client_id not in cliente_nif or user_id not in usuarios:
            continue
        nif = cliente_nif[client_id]
        candidate = (order, user_id, usuarios[user_id])
        if nif not in candidatos or candidate[:2] < candidatos[nif][:2]:
            candidatos[nif] = candidate
    return {nif: candidate[2] for nif, candidate in candidatos.items()}


def actualizar_responsables_desde_a3(
    gestor, administrador_nombre: str = "Administrador",
) -> ResponsablesImportSummary:
    mapa = _leer_mapa_responsables()
    rows = [dict(row) for row in gestor.conn.execute(
        "SELECT codigo,ejercicio,cif,email,responsable FROM empresas"
    ).fetchall()]
    latest = {}
    updated = 0
    matched_codes = set()
    internal_codes = set()
    with gestor.conn:
        for row in rows:
            code = str(row["codigo"])
            latest[code] = row
            nif = a3._normalizar_nif_a3(row.get("cif"))
            responsible = mapa.get(nif)
            if responsible:
                matched_codes.add(code)
            if es_cliente_interno(row):
                responsible = administrador_nombre
                internal_codes.add(code)
            if responsible and str(row.get("responsable") or "") != responsible:
                gestor.conn.execute(
                    "UPDATE empresas SET responsable=? WHERE codigo=? AND ejercicio=?",
                    (responsible, code, row["ejercicio"]),
                )
                updated += 1

    latest_rows = {}
    for row in rows:
        code = str(row["codigo"])
        if (
            code not in latest_rows
            or int(row.get("ejercicio") or 0) > int(latest_rows[code].get("ejercicio") or 0)
        ):
            latest_rows[code] = row
    distribution = Counter()
    for code, row in latest_rows.items():
        nif = a3._normalizar_nif_a3(row.get("cif"))
        responsible = mapa.get(nif, "")
        if code in internal_codes:
            responsible = administrador_nombre
        if responsible:
            distribution[responsible] += 1
    return ResponsablesImportSummary(
        clientes_a3=len(matched_codes),
        clientes_internos=len(internal_codes),
        filas_actualizadas=updated,
        sin_asignacion_a3=len(latest_rows) - len(matched_codes | internal_codes),
        distribucion=dict(distribution),
    )
