from __future__ import annotations


def listar_cuentas_bancarias_para_plantilla(gestor, codigo: str, ejercicio: int) -> list[dict]:
    """Obtiene las cuentas del ejercicio y usa las generales (ejercicio 0) como respaldo."""
    cuentas = list(gestor.listar_cuentas_bancarias(codigo, ejercicio) or [])
    if int(ejercicio or 0) != 0:
        generales = gestor.listar_cuentas_bancarias(codigo, 0) or []
        ids = {cuenta.get("id") for cuenta in cuentas}
        claves = {
            (cuenta.get("iban"), cuenta.get("subcuenta_contable"))
            for cuenta in cuentas
        }
        for cuenta in generales:
            clave = (cuenta.get("iban"), cuenta.get("subcuenta_contable"))
            if cuenta.get("id") not in ids and clave not in claves:
                cuentas.append(cuenta)
    return cuentas


def etiqueta_cuenta_bancaria(cuenta: dict) -> str:
    descripcion = str(cuenta.get("descripcion") or "").strip()
    numero = str(cuenta.get("iban") or "").strip()
    subcuenta = str(cuenta.get("subcuenta_contable") or "").strip()
    partes = [parte for parte in (descripcion, numero, subcuenta) if parte]
    return " | ".join(partes)


def datos_plantilla_desde_cuenta(cuenta: dict) -> dict:
    numero = str(cuenta.get("iban") or "").strip()
    return {
        "banco": str(cuenta.get("descripcion") or "").strip() or numero,
        "numero_cuenta": numero,
        "subcuenta_banco": str(cuenta.get("subcuenta_contable") or "").strip(),
    }
