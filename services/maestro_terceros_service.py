"""
Gestion del maestro global de terceros.

Reglas:
  - El maestro es global (no depende de empresa ni ejercicio).
  - La clave de unicidad es nif_normalizado cuando existe NIF.
  - Terceros sin NIF se permiten (tipo_identificacion='sin_nif').
  - Las funciones de modulo (normalizar_nif, detectar_tipo_identificacion) son
    testables directamente sin instanciar la clase.
"""
from __future__ import annotations

import re
import time
import unicodedata

from utils.validaciones import inferir_pais_desde_identificacion, normalizar_codigo_pais, normalizar_nif_cif


# ── Tipos de identificacion reconocidos ──────────────────────────────────────

TIPO_NIF    = "nif"
TIPO_CIF    = "cif"
TIPO_NIE    = "nie"
TIPO_VAT    = "vat"
TIPO_SIN_NIF = "sin_nif"

_RE_NIF = re.compile(r"^\d{8}[A-Z]$")
_RE_CIF = re.compile(r"^[ABCDEFGHJKLMNPQRSUVW]\d{7}[A-Z0-9]$")
_RE_NIE = re.compile(r"^[XYZ]\d{7}[A-Z]$")

_SUFIJOS_JURIDICOS = frozenset({
    "sl", "sa", "slu", "sc", "cb", "srl", "sau", "sad",
    "ltd", "gmbh", "bv", "inc", "llc", "spa", "nv",
    "s.l", "s.a", "s.l.u", "s.c", "c.b",
})


# ── Funciones puras de modulo ─────────────────────────────────────────────────

def normalizar_nif(nif: str | None) -> str:
    """Normaliza NIF/CIF/VAT: mayusculas, sin guiones, puntos ni espacios."""
    return normalizar_nif_cif(nif)


def detectar_tipo_identificacion(nif_norm: str) -> str:
    """Clasifica el tipo de identificacion a partir del NIF normalizado."""
    if not nif_norm:
        return TIPO_SIN_NIF
    if _RE_NIF.match(nif_norm):
        return TIPO_NIF
    if _RE_CIF.match(nif_norm):
        return TIPO_CIF
    if _RE_NIE.match(nif_norm):
        return TIPO_NIE
    return TIPO_VAT


def normalizar_nombre(nombre: str | None) -> str:
    """Normaliza nombre de empresa para comparacion fuzzy.

    Pasos: minusculas, eliminar acentos, eliminar puntuacion,
    eliminar sufijos juridicos, colapsar espacios.
    """
    if not nombre:
        return ""
    s = str(nombre).lower().strip()
    s = "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )
    s = re.sub(r"[,\.\-\_\/\(\)\[\]]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    palabras = [p for p in s.split() if p not in _SUFIJOS_JURIDICOS]
    return " ".join(palabras).strip()


# ── Servicio principal ────────────────────────────────────────────────────────

class MaestroTercerosService:

    # ── Busqueda ──────────────────────────────────────────────────────────────

    def buscar_tercero_por_nif(self, gestor, nif: str) -> dict | None:
        """Busca por nif_normalizado (campo nuevo) con fallback al campo legacy nif.

        Devuelve el primer tercero encontrado o None.
        """
        nif_norm = normalizar_nif(nif)
        if not nif_norm:
            return None
        row = gestor.conn.execute(
            "SELECT * FROM terceros WHERE nif_normalizado=? LIMIT 1",
            (nif_norm,),
        ).fetchone()
        if row:
            return dict(row)
        row = gestor.conn.execute(
            "SELECT * FROM terceros"
            " WHERE UPPER(REPLACE(REPLACE(REPLACE(nif,'-',''),' ',''),'.',''))=? LIMIT 1",
            (nif_norm,),
        ).fetchone()
        return dict(row) if row else None

    def buscar_tercero_por_nombre(
        self, gestor, nombre: str, fuzzy: bool = True
    ) -> list[dict]:
        """Busca terceros por nombre_legal o nombre (exacto, luego parcial si fuzzy=True).

        Requiere al menos 5 caracteres para la busqueda parcial.
        """
        if not nombre or not str(nombre).strip():
            return []
        nombre_strip = str(nombre).strip()
        rows = gestor.conn.execute(
            "SELECT * FROM terceros"
            " WHERE LOWER(TRIM(nombre_legal))=LOWER(?)"
            "    OR LOWER(TRIM(nombre))=LOWER(?)"
            " ORDER BY COALESCE(nombre_legal, nombre)",
            (nombre_strip, nombre_strip),
        ).fetchall()
        exactos = [dict(r) for r in rows]
        if exactos or not fuzzy or len(nombre_strip) < 5:
            return exactos
        nombre_norm = normalizar_nombre(nombre_strip)
        if not nombre_norm or len(nombre_norm) < 5:
            return exactos
        todos = gestor.conn.execute(
            "SELECT * FROM terceros ORDER BY COALESCE(nombre_legal, nombre)"
        ).fetchall()
        resultado = []
        for r in todos:
            t = dict(r)
            t_norm = normalizar_nombre(t.get("nombre_legal") or t.get("nombre") or "")
            if t_norm and (nombre_norm in t_norm or t_norm in nombre_norm):
                resultado.append(t)
        return resultado

    # ── Creacion y actualizacion ──────────────────────────────────────────────

    def crear_tercero_global(self, gestor, datos: dict) -> dict:
        """Crea o actualiza el tercero en el maestro global.

        Idempotente por nif_normalizado: si el NIF ya existe se actualiza.
        Tambien escribe los campos nuevos (nombre_legal, nif_normalizado, etc.).

        Campos de entrada (todos opcionales excepto si no hay NIF):
          nif, nombre / nombre_legal, nombre_comercial, tipo_identificacion,
          pais, direccion, cp / codigo_postal, poblacion, provincia,
          telefono, email, contacto, observaciones, origen, activo.
        """
        nif_raw = str(datos.get("nif") or "").strip()
        nif_norm = normalizar_nif(nif_raw) if nif_raw else ""
        tipo_id = datos.get("tipo_identificacion") or detectar_tipo_identificacion(nif_norm)
        nombre_legal = str(
            datos.get("nombre_legal") or datos.get("nombre") or ""
        ).strip()
        cp = str(datos.get("cp") or datos.get("codigo_postal") or "").strip()
        now = gestor._utc_now()

        existente = self.buscar_tercero_por_nif(gestor, nif_norm) if nif_norm else None
        tercero_id = (
            existente["id"] if existente
            else (datos.get("id") or str(int(time.time() * 1000)))
        )
        fecha_creacion = existente["fecha_creacion"] if existente else now

        gestor.conn.execute(
            """
            INSERT INTO terceros
              (id, nif, nombre, direccion, cp, poblacion, provincia,
               telefono, email, contacto, tipo,
               nif_normalizado, nombre_legal, nombre_comercial, tipo_identificacion,
               pais, codigo_postal, observaciones, origen, activo,
               fecha_creacion, fecha_actualizacion)
            VALUES (?,?,?,?,?,?,?,?,?,?,NULL,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              nif=excluded.nif,
              nombre=excluded.nombre,
              direccion=excluded.direccion,
              cp=excluded.cp,
              poblacion=excluded.poblacion,
              provincia=excluded.provincia,
              telefono=excluded.telefono,
              email=excluded.email,
              contacto=excluded.contacto,
              nif_normalizado=excluded.nif_normalizado,
              nombre_legal=excluded.nombre_legal,
              nombre_comercial=excluded.nombre_comercial,
              tipo_identificacion=excluded.tipo_identificacion,
              pais=excluded.pais,
              codigo_postal=excluded.codigo_postal,
              observaciones=excluded.observaciones,
              activo=excluded.activo,
              fecha_actualizacion=excluded.fecha_actualizacion
            """,
            (
                tercero_id,
                nif_raw or None,
                nombre_legal,
                datos.get("direccion") or "",
                cp,
                datos.get("poblacion") or "",
                datos.get("provincia") or "",
                datos.get("telefono") or "",
                datos.get("email") or "",
                datos.get("contacto") or "",
                nif_norm or None,
                nombre_legal,
                datos.get("nombre_comercial") or None,
                tipo_id,
                normalizar_codigo_pais(datos.get("pais")) or inferir_pais_desde_identificacion(nif_norm) or None,
                cp,
                datos.get("observaciones") or None,
                datos.get("origen") or "manual",
                1 if datos.get("activo", True) else 0,
                fecha_creacion,
                now,
            ),
        )
        gestor.conn.commit()
        row = gestor.conn.execute(
            "SELECT * FROM terceros WHERE id=?", (tercero_id,)
        ).fetchone()
        return dict(row) if row else {"id": tercero_id, **datos}

    def actualizar_tercero(self, gestor, tercero_id: str, datos: dict) -> dict:
        """Actualiza campos del tercero. Solo actualiza los campos presentes en 'datos'.

        Devuelve el dict del tercero actualizado.
        """
        now = gestor._utc_now()
        nif_raw = str(datos.get("nif") or "").strip() if "nif" in datos else None
        nif_norm = normalizar_nif(nif_raw) if nif_raw else None
        nombre_legal = str(
            datos.get("nombre_legal") or datos.get("nombre") or ""
        ).strip() or None
        cp = str(datos.get("cp") or datos.get("codigo_postal") or "").strip() or None

        gestor.conn.execute(
            """UPDATE terceros SET
               nif              = COALESCE(?, nif),
               nombre           = COALESCE(?, nombre),
               direccion        = COALESCE(?, direccion),
               cp               = COALESCE(?, cp),
               poblacion        = COALESCE(?, poblacion),
               provincia        = COALESCE(?, provincia),
               telefono         = COALESCE(?, telefono),
               email            = COALESCE(?, email),
               contacto         = COALESCE(?, contacto),
               nif_normalizado  = COALESCE(?, nif_normalizado),
               nombre_legal     = COALESCE(?, nombre_legal),
               nombre_comercial = COALESCE(?, nombre_comercial),
               tipo_identificacion = COALESCE(?, tipo_identificacion),
               pais             = COALESCE(?, pais),
               codigo_postal    = COALESCE(?, codigo_postal),
               observaciones    = COALESCE(?, observaciones),
               origen           = COALESCE(?, origen),
               activo           = COALESCE(?, activo),
               fecha_actualizacion = ?
             WHERE id=?""",
            (
                nif_raw or None,
                nombre_legal,
                datos.get("direccion"),
                cp,
                datos.get("poblacion"),
                datos.get("provincia"),
                datos.get("telefono"),
                datos.get("email"),
                datos.get("contacto"),
                nif_norm,
                nombre_legal,
                datos.get("nombre_comercial"),
                datos.get("tipo_identificacion"),
                datos.get("pais"),
                cp,
                datos.get("observaciones"),
                datos.get("origen"),
                (1 if datos["activo"] else 0) if "activo" in datos else None,
                now,
                str(tercero_id),
            ),
        )
        gestor.conn.commit()
        row = gestor.conn.execute(
            "SELECT * FROM terceros WHERE id=?", (str(tercero_id),)
        ).fetchone()
        return dict(row) if row else {}

    def nif_ya_existe(self, gestor, nif: str) -> bool:
        """True si el NIF normalizado ya existe en el maestro global."""
        return self.buscar_tercero_por_nif(gestor, nif) is not None
