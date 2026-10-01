from pathlib import Path

from services.import_a3_empresa import (
    _CU_REC_SIZE,
    _ISAM_HEADER,
    _filtrar_plan_cuentas_por_digitos,
    _leer_plan_cuentas_binario,
    _leer_subcuentas_binario,
)


def _registro_cu(*, cuenta_padre: int, indice: int, descripcion: str) -> bytes:
    registro = bytearray(_CU_REC_SIZE)
    registro[0] = 0x41
    registro[1:4] = cuenta_padre.to_bytes(3, "big")
    registro[4:8] = indice.to_bytes(4, "big")
    texto = descripcion.encode("cp1252")[:30]
    registro[8:8 + len(texto)] = texto
    return bytes(registro)


def test_leer_plan_incluye_subcuenta_con_indice_cero(tmp_path: Path):
    cu_path = tmp_path / "004236CU.DAT"
    cu_path.write_bytes(
        bytes(_ISAM_HEADER)
        + _registro_cu(
            cuenta_padre=0,
            indice=6230,
            descripcion="SERVICIOS PROFESIONALES INDEP.",
        )
        + _registro_cu(
            cuenta_padre=6230,
            indice=0,
            descripcion="SERVICIOS PROFESIONALES INDEP.",
        )
        + _registro_cu(
            cuenta_padre=6230,
            indice=10000,
            descripcion="SUBCONTRATACION LABORAL",
        )
    )

    plan = _leer_plan_cuentas_binario(cu_path)
    plan.extend(_leer_subcuentas_binario(cu_path, 8))
    cuentas = {
        item["cuenta"]
        for item in _filtrar_plan_cuentas_por_digitos(plan, 8)
    }

    assert cuentas == {"62300000", "62300001"}
