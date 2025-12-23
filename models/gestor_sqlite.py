import json
import os
import sqlite3
import time
from pathlib import Path


def _ej_val(v):
    try:
        return int(v)
    except Exception:
        return None


def _ensure_dir(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


SCHEMA = """
CREATE TABLE IF NOT EXISTS empresas (
  codigo TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  nombre TEXT,
  digitos_plan INTEGER,
  serie_emitidas TEXT,
  siguiente_num_emitidas INTEGER,
  cuenta_bancaria TEXT,
  cuentas_bancarias TEXT,
  cif TEXT,
  direccion TEXT,
  cp TEXT,
  poblacion TEXT,
  provincia TEXT,
  telefono TEXT,
  email TEXT,
  logo_path TEXT,
  PRIMARY KEY (codigo, ejercicio)
);
CREATE TABLE IF NOT EXISTS bancos (
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  banco TEXT NOT NULL,
  subcuenta_banco TEXT,
  subcuenta_por_defecto TEXT,
  conceptos_json TEXT,
  excel_json TEXT,
  PRIMARY KEY (codigo_empresa, ejercicio, banco)
);
CREATE TABLE IF NOT EXISTS facturas_emitidas (
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  nombre TEXT NOT NULL,
  cuenta_cliente_prefijo TEXT,
  cuenta_ingreso_por_defecto TEXT,
  cuenta_iva_repercutido_defecto TEXT,
  excel_json TEXT,
  PRIMARY KEY (codigo_empresa, ejercicio, nombre)
);
CREATE TABLE IF NOT EXISTS facturas_recibidas (
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  nombre TEXT NOT NULL,
  cuenta_proveedor_prefijo TEXT,
  cuenta_gasto_por_defecto TEXT,
  cuenta_iva_soportado_defecto TEXT,
  excel_json TEXT,
  PRIMARY KEY (codigo_empresa, ejercicio, nombre)
);
CREATE TABLE IF NOT EXISTS facturas_emitidas_docs (
  id TEXT PRIMARY KEY,
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  tercero_id TEXT,
  serie TEXT,
  numero TEXT,
  numero_largo_sii TEXT,
  fecha_asiento TEXT,
  fecha_expedicion TEXT,
  fecha_operacion TEXT,
  nif TEXT,
  nombre TEXT,
  descripcion TEXT,
  subcuenta_cliente TEXT,
  forma_pago TEXT,
  cuenta_bancaria TEXT,
  generada INTEGER DEFAULT 0,
  fecha_generacion TEXT,
  lineas_json TEXT
);
CREATE TABLE IF NOT EXISTS terceros (
  id TEXT PRIMARY KEY,
  nif TEXT,
  nombre TEXT,
  direccion TEXT,
  cp TEXT,
  poblacion TEXT,
  provincia TEXT,
  telefono TEXT,
  email TEXT,
  contacto TEXT,
  tipo TEXT
);
CREATE TABLE IF NOT EXISTS terceros_empresas (
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  tercero_id TEXT NOT NULL,
  subcuenta_cliente TEXT,
  subcuenta_proveedor TEXT,
  subcuenta_ingreso TEXT,
  subcuenta_gasto TEXT,
  PRIMARY KEY (codigo_empresa, ejercicio, tercero_id)
);
"""


class GestorSQLite:
    """
    Gestor de datos respaldado por SQLite, manteniendo la API de GestorPlantillas.
    """

    def __init__(self, db_path: str | Path, json_seed: str | Path | None = None):
        self.db_path = Path(db_path)
        _ensure_dir(self.db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        if json_seed:
            self._maybe_seed_from_json(json_seed)

    # ---------- utilidades internas ----------
    def _init_schema(self):
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._ensure_column("empresas", "cuenta_bancaria", "TEXT")
        self._ensure_column("empresas", "cuentas_bancarias", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "forma_pago", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "cuenta_bancaria", "TEXT")
        self._ensure_column("terceros_empresas", "subcuenta_ingreso", "TEXT")
        self._ensure_column("terceros_empresas", "subcuenta_gasto", "TEXT")
        self.conn.commit()

    def _ensure_column(self, table: str, column: str, col_type: str):
        cur = self.conn.execute(f"PRAGMA table_info({table})")
        cols = {r[1] for r in cur.fetchall()}
        if column in cols:
            return
        self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

    def _maybe_seed_from_json(self, json_seed):
        try:
            cur = self.conn.execute("SELECT COUNT(*) AS n FROM empresas")
            if cur.fetchone()["n"]:
                return
        except Exception:
            return
        jp = Path(json_seed)
        if not jp.exists():
            return
        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        # mapa codigo->ejercicio para cubrir datos sin ejercicio en plantillas antiguas
        map_ej = {}
        for e in data.get("empresas", []):
            ce = e.get("codigo")
            ej = _ej_val(e.get("ejercicio"))
            if ce is not None and ej is not None:
                map_ej.setdefault(ce, ej)
        # Empresas
        for e in data.get("empresas", []):
            self.upsert_empresa(e)
        # Bancos
        for b in data.get("bancos", []):
            if b.get("ejercicio") is None and b.get("codigo_empresa") in map_ej:
                b = dict(b, ejercicio=map_ej[b.get("codigo_empresa")])
            self.upsert_banco(b)
        # Plantillas emitidas / recibidas
        for p in data.get("facturas_emitidas", []):
            if p.get("ejercicio") is None and p.get("codigo_empresa") in map_ej:
                p = dict(p, ejercicio=map_ej[p.get("codigo_empresa")])
            self.upsert_emitida(p)
        for p in data.get("facturas_recibidas", []):
            if p.get("ejercicio") is None and p.get("codigo_empresa") in map_ej:
                p = dict(p, ejercicio=map_ej[p.get("codigo_empresa")])
            self.upsert_recibida(p)
        # Facturas emitidas docs
        for f in data.get("facturas_emitidas_docs", []):
            if f.get("ejercicio") is None and f.get("codigo_empresa") in map_ej:
                f = dict(f, ejercicio=map_ej[f.get("codigo_empresa")])
            self.upsert_factura_emitida(f)
        # Terceros
        for t in data.get("terceros", []):
            self.upsert_tercero(t)
        for rel in data.get("terceros_empresas", []):
            if rel.get("ejercicio") is None and rel.get("codigo_empresa") in map_ej:
                rel = dict(rel, ejercicio=map_ej[rel.get("codigo_empresa")])
            self.upsert_tercero_empresa(rel)

    def _row_to_dict(self, row):
        return dict(row) if row else None

    def _clonar_plantillas_si_hace_falta(self, codigo: str, ejercicio_dest: int | None):
        """
        Si se crea un nuevo ejercicio de una empresa, replica sus plantillas
        (bancos/emitidas/recibidas) desde el ultimo ejercicio existente.
        """
        ej_dest = _ej_val(ejercicio_dest)
        if ej_dest is None:
            return

        def _ej_origen(table: str) -> int | None:
            cur = self.conn.execute(
                f"SELECT DISTINCT ejercicio FROM {table} WHERE codigo_empresa=?",
                (codigo,),
            )
            otros = [r[0] for r in cur.fetchall() if r[0] != ej_dest]
            return max(otros) if otros else None

        ej_src = _ej_origen("bancos")
        ej_src_emit = _ej_origen("facturas_emitidas")
        ej_src_rec = _ej_origen("facturas_recibidas")

        # Usa el ejercicio mas reciente disponible de cada tipo
        if ej_src is not None:
            for b in self.listar_bancos(codigo, ej_src):
                nb = dict(b, codigo_empresa=codigo, ejercicio=ej_dest)
                self.upsert_banco(nb)
        if ej_src_emit is not None:
            for p in self.listar_emitidas(codigo, ej_src_emit):
                np = dict(p, codigo_empresa=codigo, ejercicio=ej_dest)
                self.upsert_emitida(np)
        if ej_src_rec is not None:
            for p in self.listar_recibidas(codigo, ej_src_rec):
                np = dict(p, codigo_empresa=codigo, ejercicio=ej_dest)
                self.upsert_recibida(np)

    # ---------- EMPRESAS ----------
    def listar_empresas(self):
        cur = self.conn.execute(
            "SELECT * FROM empresas ORDER BY codigo, ejercicio"
        )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def listar_ejercicios_empresa(self, codigo: str):
        cur = self.conn.execute(
            "SELECT ejercicio FROM empresas WHERE codigo=? ORDER BY ejercicio",
            (codigo,),
        )
        return [r["ejercicio"] for r in cur.fetchall()]

    def get_empresa(self, codigo: str, ejercicio: int | None = None):
        if ejercicio is None:
            cur = self.conn.execute(
                "SELECT * FROM empresas WHERE codigo = ? ORDER BY ejercicio DESC LIMIT 1",
                (codigo,),
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM empresas WHERE codigo = ? AND ejercicio = ?",
                (codigo, _ej_val(ejercicio)),
            )
        return self._row_to_dict(cur.fetchone())

    def upsert_empresa(self, emp: dict):
        existe = self.get_empresa(emp.get("codigo"), emp.get("ejercicio"))
        self.conn.execute(
            """
            INSERT INTO empresas (codigo, ejercicio, nombre, digitos_plan, serie_emitidas,
                siguiente_num_emitidas, cuenta_bancaria, cuentas_bancarias, cif, direccion, cp, poblacion, provincia, telefono, email, logo_path)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(codigo, ejercicio) DO UPDATE SET
                nombre=excluded.nombre,
                digitos_plan=excluded.digitos_plan,
                serie_emitidas=excluded.serie_emitidas,
                siguiente_num_emitidas=excluded.siguiente_num_emitidas,
                cuenta_bancaria=excluded.cuenta_bancaria,
                cuentas_bancarias=excluded.cuentas_bancarias,
                cif=excluded.cif,
                direccion=excluded.direccion,
                cp=excluded.cp,
                poblacion=excluded.poblacion,
                provincia=excluded.provincia,
                telefono=excluded.telefono,
                email=excluded.email,
                logo_path=excluded.logo_path
            """,
            (
                emp.get("codigo"),
                _ej_val(emp.get("ejercicio")),
                emp.get("nombre"),
                emp.get("digitos_plan"),
                emp.get("serie_emitidas"),
                emp.get("siguiente_num_emitidas"),
                emp.get("cuenta_bancaria"),
                emp.get("cuentas_bancarias"),
                emp.get("cif"),
                emp.get("direccion"),
                emp.get("cp"),
                emp.get("poblacion"),
                emp.get("provincia"),
                emp.get("telefono"),
                emp.get("email"),
                emp.get("logo_path"),
            ),
        )
        self.conn.commit()
        if not existe:
            self._clonar_plantillas_si_hace_falta(emp.get("codigo"), emp.get("ejercicio"))

    def copiar_empresa(self, codigo_origen: str, ejercicio_origen: int, nueva_empresa: dict):
        if not self.get_empresa(codigo_origen, ejercicio_origen):
            raise ValueError(f"No existe la empresa {codigo_origen} ({ejercicio_origen})")
        if self.get_empresa(nueva_empresa.get("codigo"), nueva_empresa.get("ejercicio")):
            raise ValueError("Ya existe la empresa destino.")
        self.upsert_empresa(nueva_empresa)
        # copiar plantillas
        ej_dst = _ej_val(nueva_empresa.get("ejercicio"))
        for b in self.listar_bancos(codigo_origen, ejercicio_origen):
            nb = dict(b)
            nb.update({"codigo_empresa": nueva_empresa["codigo"], "ejercicio": ej_dst})
            self.upsert_banco(nb)
        for p in self.listar_emitidas(codigo_origen, ejercicio_origen):
            np = dict(p)
            np.update({"codigo_empresa": nueva_empresa["codigo"], "ejercicio": ej_dst})
            self.upsert_emitida(np)
        for p in self.listar_recibidas(codigo_origen, ejercicio_origen):
            np = dict(p)
            np.update({"codigo_empresa": nueva_empresa["codigo"], "ejercicio": ej_dst})
            self.upsert_recibida(np)
        for rel in self.listar_terceros_empresa(codigo_origen, ejercicio_origen):
            nr = dict(rel)
            nr.update({"codigo_empresa": nueva_empresa["codigo"], "ejercicio": ej_dst})
            self.upsert_tercero_empresa(nr)

    def eliminar_empresa(self, codigo: str, ejercicio: int):
        eje = _ej_val(ejercicio)
        for table in (
            "bancos",
            "facturas_emitidas",
            "facturas_recibidas",
            "facturas_emitidas_docs",
            "terceros_empresas",
        ):
            self.conn.execute(
                f"DELETE FROM {table} WHERE codigo_empresa=? AND ejercicio=?",
                (codigo, eje),
            )
        self.conn.execute(
            "DELETE FROM empresas WHERE codigo=? AND ejercicio=?",
            (codigo, eje),
        )
        self.conn.commit()

    # ---------- BANCOS ----------
    def listar_bancos(self, codigo_empresa: str, ejercicio: int):
        cur = self.conn.execute(
            "SELECT * FROM bancos WHERE codigo_empresa=? AND ejercicio=? ORDER BY banco",
            (codigo_empresa, _ej_val(ejercicio)),
        )
        out = []
        for r in cur.fetchall():
            d = self._row_to_dict(r)
            d["conceptos"] = json.loads(d.get("conceptos_json") or "[]")
            d["excel"] = json.loads(d.get("excel_json") or "{}")
            d.pop("conceptos_json", None)
            d.pop("excel_json", None)
            out.append(d)
        return out

    def upsert_banco(self, plantilla):
        eje = _ej_val(plantilla.get("ejercicio"))
        if eje is None:
            eje = 0
        self.conn.execute(
            """
            INSERT INTO bancos (codigo_empresa, ejercicio, banco, subcuenta_banco, subcuenta_por_defecto, conceptos_json, excel_json)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(codigo_empresa, ejercicio, banco) DO UPDATE SET
                subcuenta_banco=excluded.subcuenta_banco,
                subcuenta_por_defecto=excluded.subcuenta_por_defecto,
                conceptos_json=excluded.conceptos_json,
                excel_json=excluded.excel_json
            """,
            (
                plantilla.get("codigo_empresa"),
                eje,
                plantilla.get("banco"),
                plantilla.get("subcuenta_banco"),
                plantilla.get("subcuenta_por_defecto"),
                json.dumps(plantilla.get("conceptos", []), ensure_ascii=False),
                json.dumps(plantilla.get("excel", {}), ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def eliminar_banco(self, codigo_empresa: str, banco: str, ejercicio: int):
        self.conn.execute(
            "DELETE FROM bancos WHERE codigo_empresa=? AND ejercicio=? AND banco=?",
            (codigo_empresa, _ej_val(ejercicio), banco),
        )
        self.conn.commit()

    # ---------- EMITIDAS (plantillas) ----------
    def listar_emitidas(self, codigo_empresa: str, ejercicio: int):
        cur = self.conn.execute(
            "SELECT * FROM facturas_emitidas WHERE codigo_empresa=? AND ejercicio=? ORDER BY nombre",
            (codigo_empresa, _ej_val(ejercicio)),
        )
        out = []
        for r in cur.fetchall():
            d = self._row_to_dict(r)
            d["excel"] = json.loads(d.get("excel_json") or "{}")
            d.pop("excel_json", None)
            out.append(d)
        return out

    def upsert_emitida(self, plantilla):
        eje = _ej_val(plantilla.get("ejercicio"))
        if eje is None:
            eje = 0
        self.conn.execute(
            """
            INSERT INTO facturas_emitidas (codigo_empresa, ejercicio, nombre, cuenta_cliente_prefijo,
                cuenta_ingreso_por_defecto, cuenta_iva_repercutido_defecto, excel_json)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(codigo_empresa, ejercicio, nombre) DO UPDATE SET
                cuenta_cliente_prefijo=excluded.cuenta_cliente_prefijo,
                cuenta_ingreso_por_defecto=excluded.cuenta_ingreso_por_defecto,
                cuenta_iva_repercutido_defecto=excluded.cuenta_iva_repercutido_defecto,
                excel_json=excluded.excel_json
            """,
            (
                plantilla.get("codigo_empresa"),
                eje,
                plantilla.get("nombre"),
                plantilla.get("cuenta_cliente_prefijo"),
                plantilla.get("cuenta_ingreso_por_defecto"),
                plantilla.get("cuenta_iva_repercutido_defecto"),
                json.dumps(plantilla.get("excel", {}), ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def eliminar_emitida(self, codigo_empresa: str, nombre: str, ejercicio: int):
        self.conn.execute(
            "DELETE FROM facturas_emitidas WHERE codigo_empresa=? AND ejercicio=? AND nombre=?",
            (codigo_empresa, _ej_val(ejercicio), nombre),
        )
        self.conn.commit()

    # ---------- FACTURAS EMITIDAS (DOCUMENTOS) ----------
    def listar_facturas_emitidas(self, codigo_empresa: str, ejercicio: int):
        cur = self.conn.execute(
            "SELECT * FROM facturas_emitidas_docs WHERE codigo_empresa=? AND ejercicio=? ORDER BY fecha_asiento, numero",
            (codigo_empresa, _ej_val(ejercicio)),
        )
        out = []
        for r in cur.fetchall():
            d = self._row_to_dict(r)
            d["lineas"] = json.loads(d.get("lineas_json") or "[]")
            d["generada"] = bool(d.get("generada"))
            d.pop("lineas_json", None)
            out.append(d)
        return out

    def upsert_factura_emitida(self, factura: dict):
        fid = factura.get("id") or str(int(time.time() * 1000))
        factura["id"] = fid
        eje = _ej_val(factura.get("ejercicio"))
        if eje is None:
            eje = 0
        self.conn.execute(
            """
            INSERT INTO facturas_emitidas_docs
            (id, codigo_empresa, ejercicio, tercero_id, serie, numero, numero_largo_sii,
             fecha_asiento, fecha_expedicion, fecha_operacion, nif, nombre, descripcion,
             subcuenta_cliente, forma_pago, cuenta_bancaria, generada, fecha_generacion, lineas_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                codigo_empresa=excluded.codigo_empresa,
                ejercicio=excluded.ejercicio,
                tercero_id=excluded.tercero_id,
                serie=excluded.serie,
                numero=excluded.numero,
                numero_largo_sii=excluded.numero_largo_sii,
                fecha_asiento=excluded.fecha_asiento,
                fecha_expedicion=excluded.fecha_expedicion,
                fecha_operacion=excluded.fecha_operacion,
                nif=excluded.nif,
                nombre=excluded.nombre,
                descripcion=excluded.descripcion,
                subcuenta_cliente=excluded.subcuenta_cliente,
                forma_pago=excluded.forma_pago,
                cuenta_bancaria=excluded.cuenta_bancaria,
                generada=excluded.generada,
                fecha_generacion=excluded.fecha_generacion,
                lineas_json=excluded.lineas_json
            """,
            (
                fid,
                factura.get("codigo_empresa"),
                eje,
                factura.get("tercero_id"),
                factura.get("serie"),
                factura.get("numero"),
                factura.get("numero_largo_sii"),
                factura.get("fecha_asiento"),
                factura.get("fecha_expedicion"),
                factura.get("fecha_operacion"),
                factura.get("nif"),
                factura.get("nombre"),
                factura.get("descripcion"),
                factura.get("subcuenta_cliente"),
                factura.get("forma_pago"),
                factura.get("cuenta_bancaria"),
                1 if factura.get("generada") else 0,
                factura.get("fecha_generacion"),
                json.dumps(factura.get("lineas", []), ensure_ascii=False),
            ),
        )
        self.conn.commit()
        return fid

    def eliminar_factura_emitida(self, codigo_empresa: str, factura_id: str, ejercicio: int):
        self.conn.execute(
            "DELETE FROM facturas_emitidas_docs WHERE codigo_empresa=? AND ejercicio=? AND id=?",
            (codigo_empresa, _ej_val(ejercicio), factura_id),
        )
        self.conn.commit()

    def marcar_facturas_emitidas_generadas(self, codigo_empresa: str, ids: list, fecha: str, ejercicio: int):
        ids = ids or []
        if not ids:
            return
        qmarks = ",".join("?" for _ in ids)
        self.conn.execute(
            f"UPDATE facturas_emitidas_docs SET generada=1, fecha_generacion=? WHERE codigo_empresa=? AND ejercicio=? AND id IN ({qmarks})",
            (fecha, codigo_empresa, _ej_val(ejercicio), *ids),
        )
        self.conn.commit()

    # ---------- RECIBIDAS (plantillas) ----------
    def listar_recibidas(self, codigo_empresa: str, ejercicio: int):
        cur = self.conn.execute(
            "SELECT * FROM facturas_recibidas WHERE codigo_empresa=? AND ejercicio=? ORDER BY nombre",
            (codigo_empresa, _ej_val(ejercicio)),
        )
        out = []
        for r in cur.fetchall():
            d = self._row_to_dict(r)
            d["excel"] = json.loads(d.get("excel_json") or "{}")
            d.pop("excel_json", None)
            out.append(d)
        return out

    def upsert_recibida(self, plantilla):
        eje = _ej_val(plantilla.get("ejercicio"))
        if eje is None:
            eje = 0
        self.conn.execute(
            """
            INSERT INTO facturas_recibidas (codigo_empresa, ejercicio, nombre, cuenta_proveedor_prefijo,
                cuenta_gasto_por_defecto, cuenta_iva_soportado_defecto, excel_json)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(codigo_empresa, ejercicio, nombre) DO UPDATE SET
                cuenta_proveedor_prefijo=excluded.cuenta_proveedor_prefijo,
                cuenta_gasto_por_defecto=excluded.cuenta_gasto_por_defecto,
                cuenta_iva_soportado_defecto=excluded.cuenta_iva_soportado_defecto,
                excel_json=excluded.excel_json
            """,
            (
                plantilla.get("codigo_empresa"),
                eje,
                plantilla.get("nombre"),
                plantilla.get("cuenta_proveedor_prefijo"),
                plantilla.get("cuenta_gasto_por_defecto"),
                plantilla.get("cuenta_iva_soportado_defecto"),
                json.dumps(plantilla.get("excel", {}), ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def eliminar_recibida(self, codigo_empresa: str, nombre: str, ejercicio: int):
        self.conn.execute(
            "DELETE FROM facturas_recibidas WHERE codigo_empresa=? AND ejercicio=? AND nombre=?",
            (codigo_empresa, _ej_val(ejercicio), nombre),
        )
        self.conn.commit()

    # ---------- TERCEROS (global) ----------
    def listar_terceros(self):
        cur = self.conn.execute("SELECT * FROM terceros ORDER BY nombre")
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def upsert_tercero(self, tercero: dict):
        tid = tercero.get("id") or str(int(time.time() * 1000))
        tercero["id"] = tid
        self.conn.execute(
            """
            INSERT INTO terceros (id, nif, nombre, direccion, cp, poblacion, provincia, telefono, email, contacto, tipo)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
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
                tipo=excluded.tipo
            """,
            (
                tid,
                tercero.get("nif"),
                tercero.get("nombre"),
                tercero.get("direccion"),
                tercero.get("cp"),
                tercero.get("poblacion"),
                tercero.get("provincia"),
                tercero.get("telefono"),
                tercero.get("email"),
                tercero.get("contacto"),
                tercero.get("tipo"),
            ),
        )
        self.conn.commit()
        return tid

    def eliminar_tercero(self, tercero_id: str):
        self.conn.execute("DELETE FROM terceros WHERE id=?", (tercero_id,))
        self.conn.execute("DELETE FROM terceros_empresas WHERE tercero_id=?", (tercero_id,))
        self.conn.commit()

    # ---------- TERCEROS x EMPRESA ----------
    def listar_terceros_empresa(self, codigo_empresa: str, ejercicio: int):
        cur = self.conn.execute(
            "SELECT * FROM terceros_empresas WHERE codigo_empresa=? AND ejercicio=?",
            (codigo_empresa, _ej_val(ejercicio)),
        )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def listar_terceros_por_empresa(self, codigo_empresa: str, ejercicio: int):
        cur = self.conn.execute(
            """
            SELECT t.*, te.subcuenta_cliente, te.subcuenta_proveedor
            FROM terceros t
            JOIN terceros_empresas te ON te.tercero_id = t.id
            WHERE te.codigo_empresa=? AND te.ejercicio=?
            ORDER BY t.nombre
            """,
            (codigo_empresa, _ej_val(ejercicio)),
        )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def get_tercero_empresa(self, codigo_empresa: str, tercero_id: str, ejercicio: int):
        cur = self.conn.execute(
            "SELECT * FROM terceros_empresas WHERE codigo_empresa=? AND ejercicio=? AND tercero_id=?",
            (codigo_empresa, _ej_val(ejercicio), tercero_id),
        )
        return self._row_to_dict(cur.fetchone())

    def upsert_tercero_empresa(self, rel: dict):
        eje = _ej_val(rel.get("ejercicio"))
        if eje is None:
            eje = 0
        self.conn.execute(
            """
            INSERT INTO terceros_empresas (codigo_empresa, ejercicio, tercero_id, subcuenta_cliente, subcuenta_proveedor, subcuenta_ingreso, subcuenta_gasto)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(codigo_empresa, ejercicio, tercero_id) DO UPDATE SET
                subcuenta_cliente=excluded.subcuenta_cliente,
                subcuenta_proveedor=excluded.subcuenta_proveedor,
                subcuenta_ingreso=excluded.subcuenta_ingreso,
                subcuenta_gasto=excluded.subcuenta_gasto
            """,
            (
                rel.get("codigo_empresa"),
                eje,
                rel.get("tercero_id"),
                rel.get("subcuenta_cliente"),
                rel.get("subcuenta_proveedor"),
                rel.get("subcuenta_ingreso"),
                rel.get("subcuenta_gasto"),
            ),
        )
        self.conn.commit()

    def copiar_terceros_empresa(
        self,
        codigo_empresa: str,
        ejercicio_origen: int,
        ejercicio_destino: int,
        sobrescribir: bool = False,
    ):
        ej_src = _ej_val(ejercicio_origen)
        ej_dst = _ej_val(ejercicio_destino)
        if ej_src is None or ej_dst is None or ej_src == ej_dst:
            return 0, 0
        copiados = 0
        omitidos = 0
        for rel in self.listar_terceros_empresa(codigo_empresa, ej_src):
            if not sobrescribir:
                existe = self.get_tercero_empresa(codigo_empresa, rel.get("tercero_id"), ej_dst)
                if existe:
                    omitidos += 1
                    continue
            nr = dict(rel)
            nr["codigo_empresa"] = codigo_empresa
            nr["ejercicio"] = ej_dst
            self.upsert_tercero_empresa(nr)
            copiados += 1
        return copiados, omitidos
