"""
Gestion del maestro contable de empresa: subcuentas clasificadas por tipo.

Clasificacion automatica por prefijo de 3 digitos (PGC espanol):
  430 → cliente            400 → proveedor         410 → acreedor
  440 → deudor
  600-629 (selectivo) → gasto
  700-759 (selectivo) → ingreso
  472 → iva_soportado      477 → iva_repercutido
  475 → hacienda           476 → seguridad_social
  465 → personal           572 → banco              570 → caja
  resto → otra

Reglas de uso:
  - proponer_siguiente_subcuenta: solo calcula, nunca persiste.
  - crear_subcuenta_empresa: persiste con pendiente_alta_a3=1 si creado_en_gest2a3eco=1.
  - importar_subcuentas_desde_dataframe: no marca pendiente_alta_a3 (ya viene de A3).
  - marcar_subcuenta_alta_a3_realizada: llama siempre con la confirmacion del usuario.
"""
from __future__ import annotations

import unicodedata

from utils.validaciones import normalizar_nif_cif


# ── Clasificacion por prefijo ─────────────────────────────────────────────────

_TIPO_POR_PREFIJO: list[tuple[str, str]] = [
    ("430", "cliente"),
    ("400", "proveedor"),
    ("410", "acreedor"),
    ("440", "deudor"),
    ("629", "gasto"), ("628", "gasto"), ("627", "gasto"), ("626", "gasto"),
    ("625", "gasto"), ("624", "gasto"), ("623", "gasto"), ("622", "gasto"),
    ("621", "gasto"), ("620", "gasto"), ("607", "gasto"), ("602", "gasto"),
    ("601", "gasto"), ("600", "gasto"),
    ("759", "ingreso"), ("752", "ingreso"), ("709", "ingreso"), ("708", "ingreso"),
    ("706", "ingreso"), ("705", "ingreso"), ("702", "ingreso"), ("701", "ingreso"),
    ("700", "ingreso"),
    ("472", "iva_soportado"),
    ("477", "iva_repercutido"),
    ("475", "hacienda"),
    ("476", "seguridad_social"),
    ("465", "personal"),
    ("572", "banco"),
    ("570", "caja"),
]

# Prefijos de terceros (cuentas personales: tienen subcuenta con NIF)
_PREFIJOS_TERCERO: dict[str, str] = {
    "proveedor": "400",
    "acreedor":  "410",
    "cliente":   "430",
    "deudor":    "440",
}

# Tipos de subcuenta validos
TIPOS_SUBCUENTA = (
    "cliente", "proveedor", "acreedor", "deudor",
    "gasto", "ingreso",
    "iva_soportado", "iva_repercutido",
    "hacienda", "seguridad_social", "personal",
    "banco", "caja", "otra",
)


# ── Funciones puras de modulo ─────────────────────────────────────────────────

def clasificar_tipo_subcuenta(codigo: str) -> str:
    """Clasifica una subcuenta por su prefijo de 3 digitos. Devuelve 'otra' si no coincide."""
    c = str(codigo or "").strip()
    if len(c) < 3:
        return "otra"
    prefijo = c[:3]
    for p, tipo in _TIPO_POR_PREFIJO:
        if prefijo == p:
            return tipo
    return "otra"


# ── Servicio principal ────────────────────────────────────────────────────────

class MaestroContableEmpresaService:

    # ── Busqueda ──────────────────────────────────────────────────────────────

    def buscar_subcuenta(
        self, gestor, codigo_empresa: str, subcuenta: str
    ) -> dict | None:
        return gestor.get_maestro_subcuenta_por_subcuenta(codigo_empresa, subcuenta)

    def buscar_subcuentas_por_tercero(
        self, gestor, codigo_empresa: str, tercero_id: str
    ) -> list[dict]:
        return gestor.listar_maestro_subcuentas_por_tercero(codigo_empresa, tercero_id)

    def buscar_subcuentas_por_tipo(
        self, gestor, codigo_empresa: str, tipo: str
    ) -> list[dict]:
        return gestor.listar_maestro_subcuentas_empresa(codigo_empresa, tipo=tipo)

    def buscar_subcuentas_por_nif(
        self, gestor, codigo_empresa: str, nif: str
    ) -> list[dict]:
        return gestor.listar_maestro_subcuentas_por_nif(codigo_empresa, nif)

    # ── Propuesta de siguiente subcuenta libre ────────────────────────────────

    def proponer_siguiente_subcuenta(
        self,
        gestor,
        codigo_empresa: str,
        tipo: str,
        digitos_plan: int = 8,
    ) -> str:
        """Calcula la siguiente subcuenta libre para el tipo dado.

        Fuentes consultadas (sin modificar ninguna):
          1. maestro_subcuentas_empresa (fuente de verdad nueva)
          2. plan_cuentas (cuentas importadas de A3, todos los ejercicios)
        """
        prefijo = _PREFIJOS_TERCERO.get(tipo) or {
            "gasto":           "600",
            "ingreso":         "700",
            "banco":           "572",
            "iva_soportado":   "472",
            "iva_repercutido": "477",
            "hacienda":        "475",
            "seguridad_social":"476",
            "personal":        "465",
            "caja":            "570",
        }.get(tipo, "400")

        usadas: set[int] = set()

        for sub in gestor.listar_maestro_subcuentas_empresa(codigo_empresa, activo=None):
            val = str(sub.get("subcuenta") or "").strip()
            if _es_del_prefijo(val, prefijo, digitos_plan):
                usadas.add(int(val))

        try:
            rows = gestor.conn.execute(
                "SELECT cuenta FROM plan_cuentas"
                " WHERE codigo_empresa=? AND cuenta LIKE ?",
                (codigo_empresa, prefijo + "%"),
            ).fetchall()
            for row in rows:
                val = str(row[0]).strip()
                if _es_del_prefijo(val, prefijo, digitos_plan):
                    usadas.add(int(val))
        except Exception:
            pass

        primera = int(prefijo) * (10 ** (digitos_plan - len(prefijo))) + 1
        candidato = primera
        while candidato in usadas:
            candidato += 1
        return str(candidato).zfill(digitos_plan)

    # ── Creacion ──────────────────────────────────────────────────────────────

    def crear_subcuenta_empresa(self, gestor, datos: dict) -> dict:
        """Crea o actualiza una subcuenta en el maestro empresa.

        Campos esperados en 'datos':
          codigo_empresa (*), subcuenta (*), nombre_subcuenta,
          tipo_subcuenta (calculado si ausente), tercero_id, nif / nif_snapshot,
          creado_en_gest2a3eco (default 1), pendiente_alta_a3 (default 1 si creado aqui),
          origen, cuenta_gasto_predeterminada_id, cuenta_iva_predeterminada_id,
          cuenta_retencion_predeterminada_id, observaciones, activo.

        Devuelve el dict del registro creado/actualizado.
        """
        codigo = str(datos.get("codigo_empresa") or "").strip()
        subcuenta = str(datos.get("subcuenta") or "").strip()
        if not codigo or not subcuenta:
            raise ValueError("codigo_empresa y subcuenta son obligatorios")

        tipo = datos.get("tipo_subcuenta") or clasificar_tipo_subcuenta(subcuenta)
        creado = int(datos.get("creado_en_gest2a3eco", 1))
        pendiente = int(datos.get("pendiente_alta_a3", 1 if creado else 0))
        nif_snapshot = (
            datos.get("nif_snapshot")
            or normalizar_nif_cif(datos.get("nif") or "")
            or None
        )

        payload = {
            "codigo_empresa":                    codigo,
            "subcuenta":                         subcuenta,
            "nombre_subcuenta":                  datos.get("nombre_subcuenta") or datos.get("nombre") or "",
            "tipo_subcuenta":                    tipo,
            "tercero_id":                        datos.get("tercero_id"),
            "nif_snapshot":                      nif_snapshot,
            "activo":                            int(datos.get("activo", 1)),
            "origen":                            datos.get("origen") or "manual",
            "creado_en_gest2a3eco":              creado,
            "pendiente_alta_a3":                 pendiente,
            "observaciones":                     datos.get("observaciones"),
            "tipo_operacion_predeterminada":     datos.get("tipo_operacion_predeterminada"),
            "cuenta_gasto_predeterminada_id":    datos.get("cuenta_gasto_predeterminada_id"),
            "cuenta_ingreso_predeterminada_id":  datos.get("cuenta_ingreso_predeterminada_id"),
            "cuenta_iva_predeterminada_id":      datos.get("cuenta_iva_predeterminada_id"),
            "cuenta_retencion_predeterminada_id":datos.get("cuenta_retencion_predeterminada_id"),
        }
        gestor.upsert_maestro_subcuenta(payload)
        return gestor.get_maestro_subcuenta_por_subcuenta(codigo, subcuenta) or payload

    # ── Deteccion de duplicados ───────────────────────────────────────────────

    def detectar_duplicados_en_dataframe(
        self, gestor, codigo_empresa: str, df
    ) -> list[str]:
        """Devuelve los codigos de subcuenta del DataFrame que ya existen en el maestro."""
        col_map = {_normalize_colname(c): c for c in df.columns}
        col_sub = col_map.get("subcuenta") or col_map.get("cuenta")
        if not col_sub:
            return []
        duplicados = []
        for _, row in df.iterrows():
            subcuenta = _normalizar_codigo_subcuenta(row.get(col_sub))
            if not subcuenta:
                continue
            if gestor.get_maestro_subcuenta_por_subcuenta(codigo_empresa, subcuenta):
                duplicados.append(subcuenta)
        return duplicados

    # ── Importacion desde DataFrame ───────────────────────────────────────────

    def importar_subcuentas_desde_dataframe(
        self,
        gestor,
        codigo_empresa: str,
        df,
        origen: str = "importacion_excel",
        actualizar_duplicados: bool = True,
        progress_callback=None,
    ) -> dict:
        """Importa subcuentas desde un DataFrame de pandas.

        Columnas esperadas (insensible a mayusculas):
          'subcuenta' o 'cuenta'  — codigo de cuenta (obligatorio)
          'descripcion' o 'nombre' — nombre de la cuenta
          'nif'                    — NIF del tercero vinculado (opcional)

        Parametros:
          actualizar_duplicados — True: sobreescribe existentes; False: las omite.
          progress_callback     — callable(idx, total) para actualizar progreso.

        Devuelve dict con: importadas, actualizadas, omitidas, errores, detalles_error.
        """
        col_map = {_normalize_colname(c): c for c in df.columns}
        col_sub  = col_map.get("subcuenta") or col_map.get("cuenta")
        col_desc = col_map.get("descripcion") or col_map.get("nombre")
        col_nif  = col_map.get("nif")

        if not col_sub:
            raise ValueError("El DataFrame debe tener columna 'subcuenta' o 'cuenta'")

        importadas = actualizadas = errores = omitidas = 0
        detalles_error: list[str] = []
        filas = list(df.iterrows())
        total = len(filas)

        for idx, (_, row) in enumerate(filas):
            if progress_callback:
                try:
                    progress_callback(idx, total)
                except Exception:
                    pass
            subcuenta = _normalizar_codigo_subcuenta(row.get(col_sub))
            if not subcuenta:
                continue
            descripcion = str(row.get(col_desc, "") or "") if col_desc else ""
            nif_raw     = str(row.get(col_nif, "") or "") if col_nif else ""
            try:
                existente = gestor.get_maestro_subcuenta_por_subcuenta(
                    codigo_empresa, subcuenta
                )
                if existente and not actualizar_duplicados:
                    omitidas += 1
                    continue
                payload = {
                    "codigo_empresa":       codigo_empresa,
                    "subcuenta":            subcuenta,
                    "nombre_subcuenta":     descripcion,
                    "tipo_subcuenta":       clasificar_tipo_subcuenta(subcuenta),
                    "nif_snapshot":         normalizar_nif_cif(nif_raw) or None,
                    "origen":               origen,
                    "creado_en_gest2a3eco": 0,
                    "pendiente_alta_a3":    0,
                }
                gestor.upsert_maestro_subcuenta(payload)
                if existente:
                    actualizadas += 1
                else:
                    importadas += 1
            except Exception as exc:
                errores += 1
                detalles_error.append(f"{subcuenta}: {exc}")

        # Notificar progreso final
        if progress_callback:
            try:
                progress_callback(total, total)
            except Exception:
                pass

        return {
            "importadas":     importadas,
            "actualizadas":   actualizadas,
            "omitidas":       omitidas,
            "errores":        errores,
            "detalles_error": detalles_error,
        }

    # ── Altas A3 ──────────────────────────────────────────────────────────────

    def marcar_subcuenta_alta_a3_realizada(
        self, gestor, subcuenta_id: int, lote: str | None = None
    ) -> None:
        """Marca la subcuenta como ya dada de alta en A3 (pendiente_alta_a3 → 0)."""
        gestor.marcar_maestro_subcuenta_alta_a3(subcuenta_id, lote=lote)

    def eliminar_subcuenta_empresa(self, gestor, subcuenta_id: int) -> None:
        """Elimina una subcuenta si no esta usada en facturas."""
        gestor.eliminar_maestro_subcuenta(subcuenta_id)


# ── Utilidades ────────────────────────────────────────────────────────────────

def _normalize_colname(s: str) -> str:
    """Normaliza nombre de columna: sin acentos, minusculas, sin puntos ni espacios extra."""
    nfkd = unicodedata.normalize("NFKD", str(s))
    ascii_s = nfkd.encode("ascii", "ignore").decode("ascii")
    return ascii_s.lower().strip().replace(".", "")


def _es_del_prefijo(val: str, prefijo: str, ndig: int) -> bool:
    return val.startswith(prefijo) and val.isdigit() and len(val) == ndig


def _normalizar_codigo_subcuenta(raw) -> str:
    """Normaliza un codigo de subcuenta procedente de Excel.

    Excel puede representar cuentas como numeros flotantes ("43000001.0") o
    como enteros (43000001). Extrae solo los digitos y elimina decimales.
    Devuelve "" si el valor es nulo o no tiene digitos validos.
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", "null", ""):
        return ""
    # Excel puede dar "43000001.0" por convertir de integer a float → quitar decimal
    if "." in s:
        try:
            s = str(int(float(s)))
        except (ValueError, OverflowError):
            # Si falla, continuar con el string original
            pass
    # Extraer solo digitos (eliminar espacios, guiones, puntos residuales)
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits
