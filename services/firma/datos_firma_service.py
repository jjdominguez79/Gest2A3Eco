"""Datos de clientes y terceros disponibles en los flujos de firma."""
from __future__ import annotations


def listar_terceros_para_firma(gestor, codigo_empresa: str = "", ejercicio: int = 0) -> list[dict]:
    """Devuelve primero los terceros vinculados y despues el resto del maestro global."""
    vinculados = []
    if codigo_empresa:
        vinculados = list(gestor.listar_terceros_por_empresa(codigo_empresa, ejercicio) or [])
    globales = list(gestor.listar_terceros() or [])

    resultado = []
    vistos = set()
    for tercero in [*vinculados, *globales]:
        item = dict(tercero or {})
        tercero_id = str(item.get("id") or item.get("tercero_id") or "").strip()
        clave = tercero_id or "|".join(
            str(item.get(campo) or "").strip().lower()
            for campo in ("nif", "nombre_legal", "nombre", "email")
        )
        if not clave or clave in vistos or item.get("activo") in (0, False):
            continue
        vistos.add(clave)
        resultado.append(item)
    return resultado
