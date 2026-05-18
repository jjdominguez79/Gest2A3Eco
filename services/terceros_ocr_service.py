"""
Busqueda, propuesta de subcuenta y creacion de terceros para el flujo OCR.

Reglas de uso:
  - resolver_tercero: SOLO busca, nunca crea. Llamar desde main thread.
  - proponer_subcuenta: calcula la siguiente libre, no la persiste.
  - crear_tercero: crea tercero + relacion empresa. Llamar solo con accion explicita del usuario.

Jerarquia de busqueda:
  1. NIF exacto (normalizado) en terceros de la empresa.
  2. Nombre normalizado exacto en terceros de la empresa.
  3. Nombre parcial (uno contiene al otro) en terceros de la empresa.
  4. NIF exacto en maestro global de terceros.

Propuesta de subcuenta:
  Prefijos por tipo: proveedor=400, acreedor=410, cliente=430.
  Busca la primera posicion libre tanto en terceros_empresas como en plan_cuentas.
"""
from __future__ import annotations

import re
import unicodedata

from utils.validaciones import normalizar_nif_cif
from services.terceros_empresa_fiscal_service import DEFAULT_REL_CONFIG


# ── Prefijos contables por tipo de tercero ────────────────────────────────────

PREFIJOS = {
    "proveedor": "400",
    "acreedor":  "410",
    "cliente":   "430",
}

CAMPO_SUBCUENTA = {
    "proveedor": "subcuenta_proveedor",
    "acreedor":  "subcuenta_proveedor",
    "cliente":   "subcuenta_cliente",
}


# ── Servicio principal ────────────────────────────────────────────────────────

class TercerosOcrService:

    # ── Busqueda ──────────────────────────────────────────────────────────────

    def resolver_tercero(
        self,
        gestor,
        nif: str,
        nombre: str,
        codigo: str,
        ejercicio: int,
    ) -> dict | None:
        """Devuelve el tercero encontrado (con subcuentas) o None.

        El dict devuelto es el mismo formato que listar_terceros_por_empresa:
        incluye campos de 'terceros' + subcuenta_proveedor, subcuenta_cliente, etc.
        """
        nif_norm = _norm_nif(nif)
        nombre_norm = _norm_nombre(nombre)

        empresa_terceros = gestor.listar_terceros_por_empresa(codigo, ejercicio)

        # 1. NIF exacto en terceros de la empresa
        if nif_norm:
            for t in empresa_terceros:
                if _norm_nif(t.get("nif")) == nif_norm:
                    return t

        # 2+3. Nombre normalizado en terceros de la empresa
        if nombre_norm:
            # Exacto
            for t in empresa_terceros:
                if _norm_nombre(t.get("nombre") or "") == nombre_norm:
                    return t
            # Parcial (uno contiene al otro, minimo 5 chars para evitar falsos)
            if len(nombre_norm) >= 5:
                for t in empresa_terceros:
                    t_norm = _norm_nombre(t.get("nombre") or "")
                    if t_norm and len(t_norm) >= 5:
                        if nombre_norm in t_norm or t_norm in nombre_norm:
                            return t

        # 4. NIF exacto en maestro global
        if nif_norm:
            for t in gestor.listar_terceros():
                if _norm_nif(t.get("nif")) == nif_norm:
                    return t

        return None

    # ── Propuesta de subcuenta ────────────────────────────────────────────────

    def proponer_subcuenta(
        self,
        gestor,
        tipo_tercero: str,
        codigo: str,
        ejercicio: int,
    ) -> str:
        """Calcula la siguiente subcuenta libre para el tipo de tercero.

        Consulta (sin modificar):
          1. maestro_subcuentas_empresa (fuente de verdad nueva)
          2. terceros_empresas (legacy, backward compat)
          3. plan_cuentas (cuentas importadas de A3)
        No persiste nada.
        """
        empresa = gestor.get_empresa(codigo, ejercicio) or {}
        ndig = int(empresa.get("digitos_plan") or 8)
        prefijo = PREFIJOS.get(tipo_tercero, "400")
        campo = CAMPO_SUBCUENTA.get(tipo_tercero, "subcuenta_proveedor")

        usadas: set[int] = set()

        # 1. maestro_subcuentas_empresa (nuevo)
        for sub in gestor.listar_maestro_subcuentas_empresa(codigo, activo=None):
            val = str(sub.get("subcuenta") or "").strip()
            if _es_subcuenta_valida(val, prefijo, ndig):
                usadas.add(int(val))

        # 2. terceros_empresas (legacy)
        for t in gestor.listar_terceros_por_empresa(codigo, ejercicio):
            sub = str(t.get(campo) or "").strip()
            if _es_subcuenta_valida(sub, prefijo, ndig):
                usadas.add(int(sub))

        # 3. plan_cuentas
        for cuenta in gestor.buscar_cuentas_en_plan(codigo, ejercicio, prefijo):
            cuenta = str(cuenta).strip()
            if _es_subcuenta_valida(cuenta, prefijo, ndig):
                usadas.add(int(cuenta))

        primera = int(prefijo) * (10 ** (ndig - len(prefijo))) + 1
        candidato = primera
        while candidato in usadas:
            candidato += 1

        return str(candidato).zfill(ndig)

    # ── Creacion de tercero ───────────────────────────────────────────────────

    def crear_tercero(
        self,
        gestor,
        datos: dict,
        subcuenta: str,
        tipo_tercero: str,
        codigo: str,
        ejercicio: int,
    ) -> dict:
        """Crea tercero global + relacion empresa. Idempotente por NIF.

        Llamar SOLO con accion explicita del usuario (nunca en el hilo OCR).

        Parametros:
          datos      : dict con nif, nombre, y campos opcionales (direccion, cp, etc.)
          subcuenta  : subcuenta a asignar (proponer_subcuenta o introducida por usuario)
          tipo_tercero: "proveedor" | "acreedor" | "cliente"
        Devuelve el dict del tercero con la subcuenta asignada.
        """
        nif = normalizar_nif_cif(datos.get("nif") or "")

        # Anti-duplicado: si ya existe por NIF, reusar su id
        tercero_id: str | None = None
        if nif:
            for t in gestor.listar_terceros():
                if _norm_nif(t.get("nif")) == _norm_nif(nif):
                    tercero_id = str(t["id"])
                    break

        tercero = {
            "id":        tercero_id,
            "nif":       nif,
            "nombre":    str(datos.get("nombre") or "").strip(),
            "direccion": datos.get("direccion") or "",
            "cp":        datos.get("cp") or "",
            "poblacion": datos.get("poblacion") or "",
            "provincia": datos.get("provincia") or "",
            "telefono":  datos.get("telefono") or "",
            "email":     datos.get("email") or "",
            "contacto":  datos.get("contacto") or "",
            "tipo":      None,   # campo legacy; el tipo real viene de la subcuenta asignada
        }
        tid = gestor.upsert_tercero(tercero)

        campo = CAMPO_SUBCUENTA.get(tipo_tercero, "subcuenta_proveedor")
        rel = {
            "codigo_empresa":   codigo,
            "ejercicio":        ejercicio,
            "tercero_id":       tid,
            "subcuenta_cliente":   subcuenta if campo == "subcuenta_cliente" else None,
            "subcuenta_proveedor": subcuenta if campo == "subcuenta_proveedor" else None,
            "subcuenta_ingreso":   None,
            "subcuenta_gasto":     None,
            "cliente_tipo_operacion_iva": DEFAULT_REL_CONFIG["cliente_tipo_operacion_iva"],
            "cliente_iva_deducible": DEFAULT_REL_CONFIG["cliente_iva_deducible"],
            "cliente_porcentaje_deduccion_iva": DEFAULT_REL_CONFIG["cliente_porcentaje_deduccion_iva"],
            "proveedor_tipo_operacion_iva": DEFAULT_REL_CONFIG["proveedor_tipo_operacion_iva"],
            "proveedor_iva_deducible": DEFAULT_REL_CONFIG["proveedor_iva_deducible"],
            "proveedor_porcentaje_deduccion_iva": DEFAULT_REL_CONFIG["proveedor_porcentaje_deduccion_iva"],
        }
        gestor.upsert_tercero_empresa(rel)

        # Sincronizar con maestro_subcuentas_empresa (Fase 2+)
        tipo_sub = {"subcuenta_proveedor": "proveedor", "subcuenta_cliente": "cliente"}.get(campo, tipo_tercero)
        gestor.upsert_maestro_subcuenta({
            "codigo_empresa":       codigo,
            "tercero_id":           str(tid),
            "subcuenta":            str(subcuenta),
            "nombre_subcuenta":     tercero.get("nombre") or "",
            "tipo_subcuenta":       tipo_sub,
            "nif_snapshot":         nif,
            "activo":               1,
            "origen":               "manual",
            "creado_en_gest2a3eco": 1,
            "pendiente_alta_a3":    1,
        })

        tercero["id"] = tid
        tercero[campo] = subcuenta
        return tercero

    # ── Validacion de NIF antes de crear ─────────────────────────────────────

    def nif_ya_existe(self, gestor, nif: str) -> bool:
        """True si el NIF normalizado ya existe en el maestro global de terceros."""
        nif_norm = _norm_nif(nif)
        if not nif_norm:
            return False
        return any(_norm_nif(t.get("nif")) == nif_norm for t in gestor.listar_terceros())


# ── Utilidades de normalizacion (nivel modulo, testables) ─────────────────────

_SUFIJOS_LEGALES = frozenset({
    "sl", "sa", "slu", "sc", "cb", "srl", "sau", "sad",
    "ltd", "gmbh", "bv", "inc", "llc", "spa", "nv",
    "s.l", "s.a", "s.l.u", "s.c", "c.b",
})


def _norm_nif(nif: str | None) -> str:
    return str(nif or "").strip().upper().replace("-", "").replace(" ", "").replace(".", "")


def _norm_nombre(nombre: str | None) -> str:
    """Normaliza nombre de empresa para comparacion fuzzy.

    Pasos:
    1. Minusculas y strip.
    2. Sustituir signos diacriticos (accents → base).
    3. Eliminar puntuacion y guiones.
    4. Eliminar sufijos juridicos comunes.
    5. Colapsar espacios.
    """
    if not nombre:
        return ""
    s = str(nombre).lower().strip()
    # Eliminar acentos
    s = "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )
    # Reemplazar signos por espacio
    s = re.sub(r"[,\.\-\_\/\(\)\[\]]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Eliminar sufijos juridicos
    palabras = [p for p in s.split() if p not in _SUFIJOS_LEGALES]
    return " ".join(palabras).strip()


def _es_subcuenta_valida(sub: str, prefijo: str, ndig: int) -> bool:
    return (
        sub.startswith(prefijo)
        and sub.isdigit()
        and len(sub) == ndig
    )
