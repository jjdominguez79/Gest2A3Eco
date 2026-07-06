import json
import sqlite3
import time
import re
from datetime import datetime
from pathlib import Path

from services.terceros_empresa_fiscal_service import validate_tercero_empresa_rel
from utils.validaciones import inferir_pais_desde_identificacion, normalizar_codigo_pais


def _ej_val(v):
    try:
        return int(v)
    except Exception:
        return None


def _codigo_empresa_a3(v) -> str:
    raw = str(v or "").strip().upper()
    if raw.startswith("E"):
        raw = raw[1:]
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ""
    return f"E{digits.zfill(5)}"


def _ensure_dir(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


class DatabaseOpenError(RuntimeError):
    def __init__(self, db_path: Path, action: str, original: Exception):
        self.db_path = Path(db_path)
        self.action = action
        self.original = original
        super().__init__(f"No se pudo {action} la base de datos SQLite en '{self.db_path}': {original}")


SCHEMA = """
CREATE TABLE IF NOT EXISTS empresas (
  codigo TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  nombre TEXT,
  digitos_plan INTEGER,
  serie_emitidas TEXT,
  siguiente_num_emitidas INTEGER,
  serie_emitidas_rect TEXT,
  siguiente_num_emitidas_rect INTEGER,
  pdf_ref_seq INTEGER,
  cuenta_bancaria TEXT,
  cuentas_bancarias TEXT,
  cif TEXT,
  direccion TEXT,
  cp TEXT,
  poblacion TEXT,
  provincia TEXT,
  pais TEXT,
  telefono TEXT,
  email TEXT,
  logo_path TEXT,
  logo_max_width_mm REAL,
  logo_max_height_mm REAL,
  activo INTEGER DEFAULT 1,
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
  cuenta_retenciones_irpf TEXT,
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
CREATE TABLE IF NOT EXISTS facturas_recibidas_docs (
  id TEXT PRIMARY KEY,
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  tercero_id TEXT,
  origen_path TEXT,
  pdf_path TEXT,
  texto_ocr TEXT,
  estado_ocr TEXT,
  estado_validacion TEXT,
  estado_contable TEXT,
  proveedor_nif TEXT,
  proveedor_nombre TEXT,
  numero_factura TEXT,
  fecha_factura TEXT,
  fecha_operacion TEXT,
  fecha_asiento TEXT,
  descripcion TEXT,
  moneda_codigo TEXT,
  base_imponible REAL,
  cuota_iva REAL,
  cuota_recargo REAL,
  cuota_retencion REAL,
  total REAL,
  cuenta_gasto TEXT,
  cuenta_iva TEXT,
  cuenta_proveedor TEXT,
  proveedor_tipo_operacion_iva TEXT,
  proveedor_iva_deducible INTEGER,
  proveedor_porcentaje_deduccion_iva REAL,
  pdf_ref TEXT,
  numero_asiento TEXT,
  generada INTEGER DEFAULT 0,
  fecha_generacion TEXT,
  confianza_ocr REAL,
  datos_extra_json TEXT,
  lineas_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facturas_recibidas_docs_empresa
  ON facturas_recibidas_docs(codigo_empresa, ejercicio, fecha_asiento);
CREATE TABLE IF NOT EXISTS asientos_contables (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  documento_id TEXT NOT NULL,
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  fecha_asiento TEXT,
  numero_asiento TEXT,
  descripcion TEXT,
  estado TEXT,
  total_debe REAL,
  total_haber REAL,
  lineas_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(documento_id),
  FOREIGN KEY (documento_id) REFERENCES facturas_recibidas_docs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_asientos_contables_empresa
  ON asientos_contables(codigo_empresa, ejercicio, fecha_asiento);
CREATE TABLE IF NOT EXISTS facturas_emitidas_docs (
  id TEXT PRIMARY KEY,
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  tercero_id TEXT,
  serie TEXT,
  numero TEXT,
  numero_largo_sii TEXT,
  numero_asiento TEXT,
  fecha_asiento TEXT,
  fecha_expedicion TEXT,
  fecha_operacion TEXT,
  tipo_operacion TEXT,
  modelo_fiscal TEXT,
  nif TEXT,
  nombre TEXT,
  descripcion TEXT,
  observaciones TEXT,
  subcuenta_cliente TEXT,
  forma_pago TEXT,
  cuenta_bancaria TEXT,
  plantilla_word TEXT,
  plantilla_emitidas TEXT,
  pdf_path TEXT,
  pdf_ref TEXT,
  pdf_path_a3 TEXT,
  retencion_aplica INTEGER,
  retencion_pct REAL,
  retencion_base REAL,
  retencion_importe REAL,
  descuento_total_tipo TEXT,
  descuento_total_valor REAL,
  moneda_codigo TEXT,
  moneda_simbolo TEXT,
  enviado INTEGER DEFAULT 0,
  fecha_envio TEXT,
  canal_envio TEXT,
  generada INTEGER DEFAULT 0,
  fecha_generacion TEXT,
  lineas_json TEXT,
  facturae_xml_path TEXT,
  facturae_generated_at TEXT,
  facturae_status TEXT,
  facturae_error TEXT
);
CREATE TABLE IF NOT EXISTS albaranes_emitidas_docs (
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
  observaciones TEXT,
  subcuenta_cliente TEXT,
  forma_pago TEXT,
  cuenta_bancaria TEXT,
  pdf_path TEXT,
  pdf_ref TEXT,
  retencion_aplica INTEGER,
  retencion_pct REAL,
  retencion_base REAL,
  retencion_importe REAL,
  moneda_codigo TEXT,
  moneda_simbolo TEXT,
  facturado INTEGER DEFAULT 0,
  factura_id TEXT,
  fecha_facturacion TEXT,
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
  cliente_tipo_operacion_iva TEXT DEFAULT 'INTERIOR_IVA',
  cliente_intracomunitaria_clase TEXT,
  cliente_iva_deducible INTEGER DEFAULT 0,
  cliente_porcentaje_deduccion_iva REAL,
  proveedor_tipo_operacion_iva TEXT DEFAULT 'INTERIOR_DEDUCIBLE',
  proveedor_intracomunitaria_clase TEXT,
  proveedor_iva_deducible INTEGER DEFAULT 1,
  proveedor_porcentaje_deduccion_iva REAL DEFAULT 100,
  facturae_es_administracion_publica INTEGER DEFAULT 0,
  facturae_dir3_oficina_contable TEXT,
  facturae_dir3_organo_gestor TEXT,
  facturae_dir3_unidad_tramitadora TEXT,
  facturae_dir3_organo_proponente TEXT,
  facturae_referencia_expediente TEXT,
  facturae_referencia_contrato TEXT,
  facturae_referencia_pedido TEXT,
  PRIMARY KEY (codigo_empresa, ejercicio, tercero_id)
);
CREATE TABLE IF NOT EXISTS plan_cuentas (
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  cuenta TEXT NOT NULL,
  descripcion TEXT,
  PRIMARY KEY (codigo_empresa, ejercicio, cuenta)
);
CREATE INDEX IF NOT EXISTS idx_plan_cuentas_empresa
  ON plan_cuentas(codigo_empresa, ejercicio);
CREATE TABLE IF NOT EXISTS cuentas_bancarias (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  descripcion TEXT,
  iban TEXT,
  subcuenta_contable TEXT,
  origen TEXT,
  principal INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cuentas_bancarias_empresa
  ON cuentas_bancarias(codigo_empresa, ejercicio);
-- Legacy documental retirado de la aplicacion activa.
-- Estas tablas se conservan para compatibilidad con bases de datos existentes.
CREATE TABLE IF NOT EXISTS plantillas_documentos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  nombre TEXT NOT NULL,
  tipo_documento TEXT,
  descripcion TEXT,
  ruta_template TEXT NOT NULL,
  variables_json TEXT,
  activa INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(codigo_empresa, ejercicio, nombre)
);
CREATE INDEX IF NOT EXISTS idx_plantillas_documentos_empresa
  ON plantillas_documentos(codigo_empresa, ejercicio, nombre);
CREATE TABLE IF NOT EXISTS intervinientes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  tipo_persona TEXT,
  nombre_razon_social TEXT,
  nif TEXT,
  domicilio TEXT,
  municipio TEXT,
  provincia TEXT,
  cp TEXT,
  telefono TEXT,
  email TEXT,
  representante TEXT,
  cargo TEXT,
  cliente_id TEXT,
  es_cliente_habitual INTEGER NOT NULL DEFAULT 0,
  observaciones TEXT
);
CREATE INDEX IF NOT EXISTS idx_intervinientes_empresa
  ON intervinientes(codigo_empresa, ejercicio, nombre_razon_social);
CREATE TABLE IF NOT EXISTS operaciones (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  titulo TEXT NOT NULL,
  tipo_operacion TEXT,
  cliente_id TEXT,
  fecha_creacion TEXT,
  descripcion TEXT,
  estado TEXT
);
CREATE INDEX IF NOT EXISTS idx_operaciones_empresa
  ON operaciones(codigo_empresa, ejercicio, titulo);
CREATE TABLE IF NOT EXISTS operacion_intervinientes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  operacion_id INTEGER NOT NULL,
  interviniente_id INTEGER NOT NULL,
  rol TEXT,
  FOREIGN KEY (operacion_id) REFERENCES operaciones(id) ON DELETE CASCADE,
  FOREIGN KEY (interviniente_id) REFERENCES intervinientes(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS documentos_generados (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  plantilla_id INTEGER,
  cliente_id TEXT,
  operacion_id INTEGER,
  titulo_documento TEXT NOT NULL,
  fecha_generacion TEXT,
  ruta_docx TEXT,
  ruta_pdf TEXT,
  estado TEXT,
  observaciones TEXT,
  json_datos_generacion TEXT,
  FOREIGN KEY (plantilla_id) REFERENCES plantillas_documentos(id) ON DELETE SET NULL,
  FOREIGN KEY (operacion_id) REFERENCES operaciones(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_documentos_generados_empresa
  ON documentos_generados(codigo_empresa, ejercicio, fecha_generacion);
CREATE TABLE IF NOT EXISTS documento_intervinientes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  documento_id INTEGER NOT NULL,
  interviniente_id INTEGER NOT NULL,
  rol_en_documento TEXT,
  FOREIGN KEY (documento_id) REFERENCES documentos_generados(id) ON DELETE CASCADE,
  FOREIGN KEY (interviniente_id) REFERENCES intervinientes(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS series_emitidas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  nombre TEXT NOT NULL,
  siguiente_num INTEGER NOT NULL DEFAULT 1,
  es_rectificativa INTEGER NOT NULL DEFAULT 0,
  activa INTEGER NOT NULL DEFAULT 1,
  UNIQUE(codigo_empresa, ejercicio, nombre)
);
CREATE INDEX IF NOT EXISTS idx_series_emitidas_empresa
  ON series_emitidas(codigo_empresa, ejercicio);
"""

AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  nombre TEXT NOT NULL,
  rol TEXT NOT NULL CHECK (rol IN ('admin', 'empleado', 'cliente')),
  activo INTEGER NOT NULL DEFAULT 1,
  must_change_password INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usuarios_empresas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario_id INTEGER NOT NULL,
  empresa_codigo TEXT NOT NULL,
  permiso TEXT NOT NULL CHECK (permiso IN ('ninguno', 'lectura', 'escritura')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(usuario_id, empresa_codigo),
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_usuarios_username ON usuarios(username);
CREATE INDEX IF NOT EXISTS idx_usuarios_empresas_usuario ON usuarios_empresas(usuario_id);
CREATE INDEX IF NOT EXISTS idx_usuarios_empresas_empresa ON usuarios_empresas(empresa_codigo);
"""


class GestorSQLite:
    """
    Gestor de datos respaldado por SQLite, manteniendo la API de GestorPlantillas.
    """

    def __init__(self, db_path: str | Path, json_seed: str | Path | None = None):
        self.db_path = Path(db_path)
        try:
            _ensure_dir(self.db_path)
        except Exception as exc:
            raise DatabaseOpenError(self.db_path, "preparar la carpeta de", exc) from exc
        try:
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute("PRAGMA busy_timeout = 5000")
            self.conn.row_factory = sqlite3.Row
            self._init_schema()
            self._migrate_terceros_global()
            self._migrate_maestro_subcuentas()
            self._migrate_notificaciones()
            self._migrate_seguridad_social()
            if json_seed:
                self._maybe_seed_from_json(json_seed)
        except Exception as exc:
            try:
                self.conn.close()
            except Exception:
                pass
            raise DatabaseOpenError(self.db_path, "abrir", exc) from exc

    # ---------- utilidades internas ----------
    def _init_schema(self):
        self.conn.executescript(SCHEMA + AUTH_SCHEMA)
        self.conn.commit()
        self._ensure_column("empresas", "cuenta_bancaria", "TEXT")
        self._ensure_column("empresas", "cuentas_bancarias", "TEXT")
        self._ensure_column("empresas", "pdf_ref_seq", "INTEGER")
        self._ensure_column("empresas", "serie_emitidas_rect", "TEXT")
        self._ensure_column("empresas", "siguiente_num_emitidas_rect", "INTEGER")
        self._ensure_column("empresas", "logo_max_width_mm", "REAL")
        self._ensure_column("empresas", "logo_max_height_mm", "REAL")
        self._ensure_column("empresas", "pais", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "forma_pago", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "cuenta_bancaria", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "plantilla_word", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "plantilla_emitidas", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "numero_asiento", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "pdf_path", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "pdf_ref", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "pdf_path_a3", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "retencion_aplica", "INTEGER")
        self._ensure_column("facturas_emitidas_docs", "retencion_pct", "REAL")
        self._ensure_column("facturas_emitidas_docs", "retencion_base", "REAL")
        self._ensure_column("facturas_emitidas_docs", "retencion_importe", "REAL")
        self._ensure_column("facturas_emitidas_docs", "descuento_total_tipo", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "descuento_total_valor", "REAL")
        self._ensure_column("facturas_emitidas_docs", "moneda_codigo", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "moneda_simbolo", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "enviado", "INTEGER")
        self._ensure_column("facturas_emitidas_docs", "fecha_envio", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "canal_envio", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "observaciones", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "tipo_operacion", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "modelo_fiscal", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "estado_contable", "TEXT")
        self.conn.execute(
            "UPDATE facturas_emitidas_docs SET tipo_operacion='01' WHERE tipo_operacion IS NULL OR TRIM(tipo_operacion)=''"
        )
        self.conn.commit()
        self._ensure_column("facturas_emitidas", "cuenta_retenciones_irpf", "TEXT")
        self._ensure_column("albaranes_emitidas_docs", "forma_pago", "TEXT")
        self._ensure_column("albaranes_emitidas_docs", "cuenta_bancaria", "TEXT")
        self._ensure_column("albaranes_emitidas_docs", "pdf_path", "TEXT")
        self._ensure_column("albaranes_emitidas_docs", "pdf_ref", "TEXT")
        self._ensure_column("albaranes_emitidas_docs", "retencion_aplica", "INTEGER")
        self._ensure_column("albaranes_emitidas_docs", "retencion_pct", "REAL")
        self._ensure_column("albaranes_emitidas_docs", "retencion_base", "REAL")
        self._ensure_column("albaranes_emitidas_docs", "retencion_importe", "REAL")
        self._ensure_column("albaranes_emitidas_docs", "moneda_codigo", "TEXT")
        self._ensure_column("albaranes_emitidas_docs", "moneda_simbolo", "TEXT")
        self._ensure_column("albaranes_emitidas_docs", "observaciones", "TEXT")
        self._ensure_column("albaranes_emitidas_docs", "tipo_operacion", "TEXT")
        self._ensure_column("albaranes_emitidas_docs", "plantilla_emitidas", "TEXT")
        self._ensure_column("albaranes_emitidas_docs", "plantilla_word", "TEXT")
        self._ensure_column("empresas", "activo", "INTEGER")
        self._ensure_column("albaranes_emitidas_docs", "facturado", "INTEGER")
        self._ensure_column("albaranes_emitidas_docs", "factura_id", "TEXT")
        self._ensure_column("albaranes_emitidas_docs", "fecha_facturacion", "TEXT")
        self._ensure_column("terceros_empresas", "subcuenta_ingreso", "TEXT")
        self._ensure_column("terceros_empresas", "subcuenta_gasto", "TEXT")
        self._ensure_column("terceros_empresas", "cliente_tipo_operacion_iva", "TEXT")
        self._ensure_column("terceros_empresas", "cliente_intracomunitaria_clase", "TEXT")
        self._ensure_column("terceros_empresas", "cliente_iva_deducible", "INTEGER")
        self._ensure_column("terceros_empresas", "cliente_porcentaje_deduccion_iva", "REAL")
        self._ensure_column("terceros_empresas", "proveedor_tipo_operacion_iva", "TEXT")
        self._ensure_column("terceros_empresas", "proveedor_intracomunitaria_clase", "TEXT")
        self._ensure_column("terceros_empresas", "proveedor_iva_deducible", "INTEGER")
        self._ensure_column("terceros_empresas", "proveedor_porcentaje_deduccion_iva", "REAL")
        self._ensure_column("terceros_empresas", "facturae_es_administracion_publica", "INTEGER")
        self._ensure_column("terceros_empresas", "facturae_dir3_oficina_contable", "TEXT")
        self._ensure_column("terceros_empresas", "facturae_dir3_organo_gestor", "TEXT")
        self._ensure_column("terceros_empresas", "facturae_dir3_unidad_tramitadora", "TEXT")
        self._ensure_column("terceros_empresas", "facturae_dir3_organo_proponente", "TEXT")
        self._ensure_column("terceros_empresas", "facturae_referencia_expediente", "TEXT")
        self._ensure_column("terceros_empresas", "facturae_referencia_contrato", "TEXT")
        self._ensure_column("terceros_empresas", "facturae_referencia_pedido", "TEXT")
        self.conn.commit()
        self.conn.execute(
            "UPDATE terceros_empresas SET cliente_tipo_operacion_iva='INTERIOR_IVA' "
            "WHERE cliente_tipo_operacion_iva IS NULL OR TRIM(cliente_tipo_operacion_iva)=''"
        )
        self.conn.execute(
            "UPDATE terceros_empresas SET cliente_iva_deducible=0 "
            "WHERE cliente_iva_deducible IS NULL"
        )
        self.conn.execute(
            "UPDATE terceros_empresas SET proveedor_tipo_operacion_iva='INTERIOR_DEDUCIBLE' "
            "WHERE proveedor_tipo_operacion_iva IS NULL OR TRIM(proveedor_tipo_operacion_iva)=''"
        )
        self.conn.execute(
            "UPDATE terceros_empresas SET proveedor_iva_deducible=1 "
            "WHERE proveedor_iva_deducible IS NULL"
        )
        self.conn.execute(
            "UPDATE terceros_empresas SET proveedor_porcentaje_deduccion_iva=100 "
            "WHERE proveedor_porcentaje_deduccion_iva IS NULL"
        )
        self.conn.execute(
            "UPDATE terceros_empresas SET proveedor_porcentaje_deduccion_iva=0 "
            "WHERE COALESCE(proveedor_iva_deducible, 0)=0"
        )
        self.conn.execute(
            "UPDATE empresas SET pais='ES' "
            "WHERE (pais IS NULL OR TRIM(pais)='') AND cif IS NOT NULL AND TRIM(cif)!=''"
        )
        self.conn.commit()
        self.conn.execute("UPDATE terceros SET tipo=NULL")
        self.conn.commit()
        self._ensure_column("usuarios", "must_change_password", "INTEGER")
        self.conn.commit()
        # Migración: crear tabla plan_cuentas si no existe (idempotente via SCHEMA)
        self.conn.executescript(
            "CREATE TABLE IF NOT EXISTS plan_cuentas ("
            "  codigo_empresa TEXT NOT NULL,"
            "  ejercicio INTEGER NOT NULL,"
            "  cuenta TEXT NOT NULL,"
            "  descripcion TEXT,"
            "  PRIMARY KEY (codigo_empresa, ejercicio, cuenta)"
            ");"
            "CREATE INDEX IF NOT EXISTS idx_plan_cuentas_empresa"
            "  ON plan_cuentas(codigo_empresa, ejercicio);"
        )
        self.conn.commit()
        self.conn.executescript(
            "CREATE TABLE IF NOT EXISTS cuentas_bancarias ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  codigo_empresa TEXT NOT NULL,"
            "  ejercicio INTEGER NOT NULL,"
            "  descripcion TEXT,"
            "  iban TEXT,"
            "  subcuenta_contable TEXT,"
            "  origen TEXT,"
            "  principal INTEGER NOT NULL DEFAULT 0,"
            "  created_at TEXT NOT NULL,"
            "  updated_at TEXT NOT NULL"
            ");"
            "CREATE INDEX IF NOT EXISTS idx_cuentas_bancarias_empresa"
            "  ON cuentas_bancarias(codigo_empresa, ejercicio);"
        )
        self.conn.commit()
        self._ensure_column("facturas_emitidas_docs", "borrador", "INTEGER")
        self._ensure_column("facturas_emitidas_docs", "subcuenta_ingreso", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "subcuenta_iva", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "subcuenta_retencion", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "facturae_xml_path", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "facturae_generated_at", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "facturae_status", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "facturae_error", "TEXT")
        self.conn.executescript(
            "CREATE TABLE IF NOT EXISTS series_emitidas ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  codigo_empresa TEXT NOT NULL,"
            "  ejercicio INTEGER NOT NULL,"
            "  nombre TEXT NOT NULL,"
            "  siguiente_num INTEGER NOT NULL DEFAULT 1,"
            "  es_rectificativa INTEGER NOT NULL DEFAULT 0,"
            "  activa INTEGER NOT NULL DEFAULT 1,"
            "  UNIQUE(codigo_empresa, ejercicio, nombre)"
            ");"
            "CREATE INDEX IF NOT EXISTS idx_series_emitidas_empresa"
            "  ON series_emitidas(codigo_empresa, ejercicio);"
        )
        self.conn.commit()
        self._migrate_series_emitidas()
        # Fase 1: campos nuevos en facturas_recibidas_docs
        self._ensure_column("facturas_recibidas_docs", "tipo_documento", "TEXT")
        self._ensure_column("facturas_recibidas_docs", "tipo_operacion", "TEXT")
        self._ensure_column("facturas_recibidas_docs", "proveedor_tipo_operacion_iva", "TEXT")
        self._ensure_column("facturas_recibidas_docs", "proveedor_iva_deducible", "INTEGER")
        self._ensure_column("facturas_recibidas_docs", "proveedor_porcentaje_deduccion_iva", "REAL")
        self._ensure_column("facturas_recibidas_docs", "fecha_vencimiento", "TEXT")
        self._ensure_column("facturas_recibidas_docs", "fecha_contabilizacion", "TEXT")
        self._ensure_column("facturas_recibidas_docs", "fecha_ocr", "TEXT")
        self._ensure_column("facturas_recibidas_docs", "fecha_validacion", "TEXT")
        self._ensure_column("facturas_recibidas_docs", "lote_generacion", "TEXT")
        self._ensure_column("facturas_recibidas_docs", "error_mensaje", "TEXT")
        self.conn.execute(
            "UPDATE facturas_recibidas_docs SET proveedor_tipo_operacion_iva='INTERIOR_DEDUCIBLE' "
            "WHERE proveedor_tipo_operacion_iva IS NULL OR TRIM(proveedor_tipo_operacion_iva)=''"
        )
        self.conn.execute(
            "UPDATE facturas_recibidas_docs SET proveedor_iva_deducible=1 "
            "WHERE proveedor_iva_deducible IS NULL"
        )
        self.conn.execute(
            "UPDATE facturas_recibidas_docs SET proveedor_porcentaje_deduccion_iva=100 "
            "WHERE proveedor_porcentaje_deduccion_iva IS NULL"
        )
        self.conn.commit()
        # Fase 1: tabla de líneas fiscales OCR
        self.conn.executescript(
            "CREATE TABLE IF NOT EXISTS ocr_lineas_fiscales ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  doc_id TEXT NOT NULL,"
            "  orden INTEGER NOT NULL DEFAULT 0,"
            "  tipo_iva REAL,"
            "  base_imponible REAL,"
            "  cuota_iva REAL,"
            "  tipo_recargo REAL,"
            "  cuota_recargo REAL,"
            "  tipo_retencion REAL,"
            "  cuota_retencion REAL,"
            "  cuenta_base TEXT,"
            "  cuenta_iva TEXT,"
            "  cuenta_retencion TEXT,"
            "  tipo_operacion_linea TEXT,"
            "  FOREIGN KEY (doc_id) REFERENCES facturas_recibidas_docs(id) ON DELETE CASCADE"
            ");"
            "CREATE INDEX IF NOT EXISTS idx_ocr_lineas_fiscales_doc"
            "  ON ocr_lineas_fiscales(doc_id, orden);"
        )
        self.conn.commit()
        # ── Fase 2: columnas nuevas en terceros (maestro global enriquecido) ──────
        self._ensure_column("terceros", "nif_normalizado", "TEXT")
        self._ensure_column("terceros", "nombre_legal", "TEXT")
        self._ensure_column("terceros", "nombre_comercial", "TEXT")
        self._ensure_column("terceros", "tipo_identificacion", "TEXT")
        self._ensure_column("terceros", "pais", "TEXT")
        self._ensure_column("terceros", "codigo_postal", "TEXT")
        self._ensure_column("terceros", "observaciones", "TEXT")
        self._ensure_column("terceros", "origen", "TEXT")
        self._ensure_column("terceros", "activo", "INTEGER")
        self._ensure_column("terceros", "fecha_creacion", "TEXT")
        self._ensure_column("terceros", "fecha_actualizacion", "TEXT")
        self.conn.execute(
            "UPDATE terceros SET nombre_legal=nombre WHERE nombre_legal IS NULL AND nombre IS NOT NULL"
        )
        self.conn.execute(
            "UPDATE terceros SET nif_normalizado=UPPER(REPLACE(REPLACE(nif,'-',''),' ',''))"
            " WHERE nif_normalizado IS NULL AND nif IS NOT NULL AND TRIM(nif)!=''"
        )
        self.conn.execute("UPDATE terceros SET activo=1 WHERE activo IS NULL")
        self.conn.commit()
        # ── Fase 2: columnas nuevas en ocr_lineas_fiscales ────────────────────────
        self._ensure_column("ocr_lineas_fiscales", "cuota_iva_manual", "INTEGER")
        self._ensure_column("ocr_lineas_fiscales", "cuota_recargo_manual", "INTEGER")
        self._ensure_column("ocr_lineas_fiscales", "subcuenta_base_id", "TEXT")
        self._ensure_column("ocr_lineas_fiscales", "subcuenta_iva_id", "TEXT")
        self._ensure_column("ocr_lineas_fiscales", "subcuenta_recargo_id", "TEXT")
        self._ensure_column("ocr_lineas_fiscales", "observaciones", "TEXT")
        # ── Fase 2: columnas nuevas en plan_cuentas ───────────────────────────────
        self._ensure_column("plan_cuentas", "tipo_cuenta", "TEXT")
        self._ensure_column("plan_cuentas", "tercero_id", "TEXT")
        self._ensure_column("plan_cuentas", "pendiente_alta_a3", "INTEGER")
        self._ensure_column("plan_cuentas", "origen_cuenta", "TEXT")
        self._ensure_column("plan_cuentas", "activo", "INTEGER")
        self.conn.commit()
        # ── Fase 2: tabla maestro_subcuentas_empresa ──────────────────────────────
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS maestro_subcuentas_empresa (
                id                                INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_empresa                    TEXT NOT NULL,
                tercero_id                        TEXT,
                subcuenta                         TEXT NOT NULL,
                nombre_subcuenta                  TEXT,
                tipo_subcuenta                    TEXT,
                tipo_operacion_predeterminada     TEXT,
                cuenta_gasto_predeterminada_id    TEXT,
                cuenta_ingreso_predeterminada_id  TEXT,
                cuenta_iva_predeterminada_id      TEXT,
                cuenta_retencion_predeterminada_id TEXT,
                nif_snapshot                      TEXT,
                activo                            INTEGER NOT NULL DEFAULT 1,
                origen                            TEXT DEFAULT 'manual',
                fecha_importacion                 TEXT,
                creado_en_gest2a3eco              INTEGER NOT NULL DEFAULT 0,
                pendiente_alta_a3                 INTEGER NOT NULL DEFAULT 0,
                fecha_alta_a3                     TEXT,
                lote_alta_a3                      TEXT,
                observaciones                     TEXT,
                created_at                        TEXT,
                updated_at                        TEXT,
                UNIQUE(codigo_empresa, subcuenta)
            );
            CREATE INDEX IF NOT EXISTS idx_mse_empresa_tercero
                ON maestro_subcuentas_empresa(codigo_empresa, tercero_id);
            CREATE INDEX IF NOT EXISTS idx_mse_empresa_tipo
                ON maestro_subcuentas_empresa(codigo_empresa, tipo_subcuenta);
            CREATE INDEX IF NOT EXISTS idx_mse_empresa_nif
                ON maestro_subcuentas_empresa(codigo_empresa, nif_snapshot);
        """)
        self.conn.commit()
        # ── Fase 2: tabla retenciones por documento OCR ───────────────────────────
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS captura_documental_retenciones (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                documento_id           TEXT NOT NULL,
                base_retencion         REAL NOT NULL DEFAULT 0.0,
                tipo_retencion         REAL NOT NULL DEFAULT 0.0,
                cuota_retencion        REAL NOT NULL DEFAULT 0.0,
                cuota_retencion_manual INTEGER NOT NULL DEFAULT 0,
                tipo_retencion_fiscal  TEXT,
                subcuenta_retencion_id TEXT,
                observaciones          TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_cdr_documento
                ON captura_documental_retenciones(documento_id);
        """)
        self.conn.commit()
        # ── Fase 3: tablas del nuevo modulo OCR tipado ───────────────────────────
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS documentos_ocr (
                id               TEXT PRIMARY KEY,
                empresa_id       TEXT NOT NULL,
                ruta_original    TEXT,
                nombre_archivo   TEXT,
                hash_archivo     TEXT,
                tipo_documento   TEXT,
                estado           TEXT,
                fecha_alta       TEXT,
                fecha_procesado  TEXT,
                motor_ocr        TEXT,
                confianza_global REAL,
                error_ocr        TEXT,
                texto_extraido   TEXT,
                json_ocr         TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_doc_ocr_hash
                ON documentos_ocr(empresa_id, hash_archivo);
            CREATE INDEX IF NOT EXISTS idx_doc_ocr_empresa
                ON documentos_ocr(empresa_id, estado);

            CREATE TABLE IF NOT EXISTS facturas_recibidas_ocr (
                id                TEXT PRIMARY KEY,
                documento_id      TEXT NOT NULL REFERENCES documentos_ocr(id) ON DELETE CASCADE,
                empresa_id        TEXT NOT NULL,
                proveedor_id      TEXT,
                nif_proveedor     TEXT,
                nombre_proveedor  TEXT,
                numero_factura    TEXT,
                fecha_factura     TEXT,
                fecha_operacion   TEXT,
                fecha_vencimiento TEXT,
                total_factura     REAL,
                base_total        REAL,
                iva_total         REAL,
                retencion_total   REAL,
                estado_validacion TEXT DEFAULT 'pendiente',
                observaciones     TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_fro_unicidad
                ON facturas_recibidas_ocr(empresa_id, nif_proveedor, numero_factura, fecha_factura, total_factura);
            CREATE INDEX IF NOT EXISTS idx_fro_empresa
                ON facturas_recibidas_ocr(empresa_id, estado_validacion);

            CREATE TABLE IF NOT EXISTS facturas_recibidas_ocr_lineas_iva (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                factura_id          TEXT NOT NULL REFERENCES facturas_recibidas_ocr(id) ON DELETE CASCADE,
                tipo_iva            REAL,
                base                REAL,
                cuota_iva           REAL,
                tipo_recargo        REAL,
                cuota_recargo       REAL,
                deducible           INTEGER DEFAULT 1,
                porcentaje_deduccion REAL DEFAULT 100,
                cuenta_gasto        TEXT,
                tipo_operacion_iva  TEXT DEFAULT 'INTERIOR_DEDUCIBLE'
            );
            CREATE INDEX IF NOT EXISTS idx_froli_factura
                ON facturas_recibidas_ocr_lineas_iva(factura_id);

            CREATE TABLE IF NOT EXISTS facturas_recibidas_ocr_retenciones (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                factura_id          TEXT NOT NULL REFERENCES facturas_recibidas_ocr(id) ON DELETE CASCADE,
                base_retencion      REAL DEFAULT 0,
                tipo_retencion      REAL DEFAULT 0,
                importe_retencion   REAL DEFAULT 0,
                clase_retencion     TEXT DEFAULT 'PROFESIONAL'
            );
            CREATE INDEX IF NOT EXISTS idx_fror_factura
                ON facturas_recibidas_ocr_retenciones(factura_id);

            CREATE TABLE IF NOT EXISTS ocr_correcciones (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                factura_id       TEXT NOT NULL,
                campo            TEXT,
                valor_ocr        TEXT,
                valor_corregido  TEXT,
                fecha_correccion TEXT,
                usuario          TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_ocr_corr_factura
                ON ocr_correcciones(factura_id);
        """)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS cuotas_periodicas (
                id              TEXT PRIMARY KEY,
                codigo_empresa  TEXT NOT NULL,
                ejercicio       INTEGER NOT NULL,
                tercero_id      TEXT,
                nif             TEXT,
                nombre          TEXT,
                descripcion     TEXT,
                serie           TEXT,
                periodicidad    TEXT NOT NULL DEFAULT 'mensual',
                fecha_inicio    TEXT,
                fecha_fin       TEXT,
                activa          INTEGER NOT NULL DEFAULT 1,
                subcuenta_cliente TEXT,
                cuenta_bancaria TEXT,
                forma_pago      TEXT,
                plantilla_word  TEXT,
                plantilla_emitidas TEXT,
                tipo_operacion  TEXT DEFAULT '01',
                modelo_fiscal   TEXT,
                retencion_aplica INTEGER DEFAULT 0,
                retencion_pct   REAL,
                descuento_total_tipo TEXT,
                descuento_total_valor REAL,
                moneda_codigo   TEXT,
                moneda_simbolo  TEXT,
                observaciones   TEXT,
                lineas_json     TEXT,
                created_at      TEXT,
                updated_at      TEXT
            );
            CREATE TABLE IF NOT EXISTS cuotas_periodicas_generadas (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                cuota_id    TEXT NOT NULL,
                periodo     TEXT NOT NULL,
                factura_id  TEXT,
                fecha_registro TEXT,
                UNIQUE(cuota_id, periodo)
            );
        """)
        self.conn.commit()

    def _ensure_column(self, table: str, column: str, col_type: str):
        cur = self.conn.execute(f"PRAGMA table_info({table})")
        cols = {r[1] for r in cur.fetchall()}
        if column in cols:
            return
        self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

    def _utc_now(self) -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat()

    def _migrate_series_emitidas(self):
        """Migra series existentes en empresas a la tabla series_emitidas si aun no existen."""
        try:
            cur = self.conn.execute("SELECT codigo, ejercicio, serie_emitidas, siguiente_num_emitidas, serie_emitidas_rect, siguiente_num_emitidas_rect FROM empresas")
            rows = cur.fetchall()
        except Exception:
            return
        for row in rows:
            codigo = row[0]
            ejercicio = row[1]
            if not codigo or ejercicio is None:
                continue
            count = self.conn.execute(
                "SELECT COUNT(*) FROM series_emitidas WHERE codigo_empresa=? AND ejercicio=?",
                (codigo, ejercicio)
            ).fetchone()[0]
            if count > 0:
                continue
            serie = str(row[2] or "A").strip() or "A"
            sig = int(row[3] or 1)
            serie_rect = str(row[4] or "R").strip() or "R"
            sig_rect = int(row[5] or 1)
            self.conn.execute(
                "INSERT OR IGNORE INTO series_emitidas (codigo_empresa, ejercicio, nombre, siguiente_num, es_rectificativa, activa) VALUES (?,?,?,?,0,1)",
                (codigo, ejercicio, serie, sig)
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO series_emitidas (codigo_empresa, ejercicio, nombre, siguiente_num, es_rectificativa, activa) VALUES (?,?,?,?,1,1)",
                (codigo, ejercicio, serie_rect, sig_rect)
            )
        self.conn.commit()

    # ── Series emitidas ─────────────────────────────────────────────────────

    def listar_series_emitidas(self, codigo: str, ejercicio: int, es_rectificativa: int | None = None):
        """Devuelve lista de series para una empresa+ejercicio."""
        if es_rectificativa is None:
            cur = self.conn.execute(
                "SELECT id, nombre, siguiente_num, es_rectificativa, activa FROM series_emitidas WHERE codigo_empresa=? AND ejercicio=? ORDER BY es_rectificativa, nombre",
                (codigo, _ej_val(ejercicio))
            )
        else:
            cur = self.conn.execute(
                "SELECT id, nombre, siguiente_num, es_rectificativa, activa FROM series_emitidas WHERE codigo_empresa=? AND ejercicio=? AND es_rectificativa=? ORDER BY nombre",
                (codigo, _ej_val(ejercicio), int(es_rectificativa))
            )
        return [dict(r) for r in cur.fetchall()]

    def upsert_serie_emitida(self, codigo: str, ejercicio: int, nombre: str, siguiente_num: int = 1, es_rectificativa: int = 0, activa: int = 1) -> int:
        """Crea o actualiza una serie. Devuelve el id."""
        self.conn.execute(
            """INSERT INTO series_emitidas (codigo_empresa, ejercicio, nombre, siguiente_num, es_rectificativa, activa)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(codigo_empresa, ejercicio, nombre) DO UPDATE SET
                 siguiente_num=excluded.siguiente_num,
                 es_rectificativa=excluded.es_rectificativa,
                 activa=excluded.activa""",
            (codigo, _ej_val(ejercicio), nombre, int(siguiente_num), int(es_rectificativa), int(activa))
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM series_emitidas WHERE codigo_empresa=? AND ejercicio=? AND nombre=?",
            (codigo, _ej_val(ejercicio), nombre)
        ).fetchone()
        return row[0] if row else None

    def eliminar_serie_emitida(self, serie_id: int):
        self.conn.execute("DELETE FROM series_emitidas WHERE id=?", (serie_id,))
        self.conn.commit()

    def incrementar_serie_num(self, codigo: str, ejercicio: int, nombre: str) -> int:
        """Incrementa el contador de la serie y devuelve el nuevo valor."""
        self.conn.execute(
            "UPDATE series_emitidas SET siguiente_num = siguiente_num + 1 WHERE codigo_empresa=? AND ejercicio=? AND nombre=?",
            (codigo, _ej_val(ejercicio), nombre)
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT siguiente_num FROM series_emitidas WHERE codigo_empresa=? AND ejercicio=? AND nombre=?",
            (codigo, _ej_val(ejercicio), nombre)
        ).fetchone()
        return row[0] if row else 1

    def get_siguiente_serie_num(self, codigo: str, ejercicio: int, nombre: str) -> int:
        row = self.conn.execute(
            "SELECT siguiente_num FROM series_emitidas WHERE codigo_empresa=? AND ejercicio=? AND nombre=?",
            (codigo, _ej_val(ejercicio), nombre)
        ).fetchone()
        return row[0] if row else 1

    def ensure_series_emitidas(self, codigo: str, ejercicio: int):
        """Asegura que existan series para empresa+ejercicio. Crea series por defecto si no existen."""
        count = self.conn.execute(
            "SELECT COUNT(*) FROM series_emitidas WHERE codigo_empresa=? AND ejercicio=?",
            (codigo, _ej_val(ejercicio))
        ).fetchone()[0]
        if count > 0:
            return
        emp = self.get_empresa(codigo, ejercicio)
        if not emp:
            return
        serie = str(emp.get("serie_emitidas") or "A").strip() or "A"
        sig = int(emp.get("siguiente_num_emitidas") or 1)
        serie_rect = str(emp.get("serie_emitidas_rect") or "R").strip() or "R"
        sig_rect = int(emp.get("siguiente_num_emitidas_rect") or 1)
        self.conn.execute(
            "INSERT OR IGNORE INTO series_emitidas (codigo_empresa, ejercicio, nombre, siguiente_num, es_rectificativa, activa) VALUES (?,?,?,?,0,1)",
            (codigo, _ej_val(ejercicio), serie, sig)
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO series_emitidas (codigo_empresa, ejercicio, nombre, siguiente_num, es_rectificativa, activa) VALUES (?,?,?,?,1,1)",
            (codigo, _ej_val(ejercicio), serie_rect, sig_rect)
        )
        self.conn.commit()

    def _migrate_terceros_global(self):
        try:
            cur = self.conn.execute(
                "SELECT codigo_empresa, tercero_id, ejercicio FROM terceros_empresas ORDER BY codigo_empresa, tercero_id, ejercicio DESC"
            )
            rows = cur.fetchall()
        except Exception:
            return
        if not rows:
            return
        best = {}
        for r in rows:
            key = (r["codigo_empresa"], r["tercero_id"])
            if key in best:
                continue
            if r["ejercicio"] == 0:
                best[key] = 0
            else:
                best[key] = r["ejercicio"]
        for (codigo, tid), eje in best.items():
            if eje == 0:
                self.conn.execute(
                    "DELETE FROM terceros_empresas WHERE codigo_empresa=? AND tercero_id=? AND ejercicio<>0",
                    (codigo, tid),
                )
                continue
            self.conn.execute(
                "UPDATE terceros_empresas SET ejercicio=0 WHERE codigo_empresa=? AND tercero_id=? AND ejercicio=?",
                (codigo, tid, eje),
            )
            self.conn.execute(
                "DELETE FROM terceros_empresas WHERE codigo_empresa=? AND tercero_id=? AND ejercicio<>0",
                (codigo, tid),
            )
        self.conn.commit()

    def _migrate_maestro_subcuentas(self):
        """Puebla maestro_subcuentas_empresa desde terceros_empresas (idempotente via INSERT OR IGNORE)."""
        try:
            rows = self.conn.execute(
                """SELECT te.codigo_empresa, te.tercero_id,
                          te.subcuenta_cliente, te.subcuenta_proveedor,
                          te.subcuenta_ingreso, te.subcuenta_gasto,
                          t.nif, t.nombre
                   FROM terceros_empresas te
                   LEFT JOIN terceros t ON t.id = te.tercero_id
                   WHERE te.ejercicio = 0"""
            ).fetchall()
        except Exception:
            return
        now = self._utc_now()
        campo_tipo = {
            "subcuenta_proveedor": "proveedor",
            "subcuenta_cliente": "cliente",
            "subcuenta_ingreso": "ingreso",
            "subcuenta_gasto": "gasto",
        }
        for r in rows:
            for campo, tipo in campo_tipo.items():
                subcuenta = r[campo]
                if not subcuenta or not str(subcuenta).strip():
                    continue
                nif = r["nif"] or ""
                nif_norm = nif.upper().replace("-", "").replace(" ", "") if nif else ""
                self.conn.execute(
                    """INSERT OR IGNORE INTO maestro_subcuentas_empresa
                       (codigo_empresa, tercero_id, subcuenta, nombre_subcuenta, tipo_subcuenta,
                        nif_snapshot, activo, origen, creado_en_gest2a3eco, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,1,'importacion_a3',0,?,?)""",
                    (r["codigo_empresa"], r["tercero_id"], str(subcuenta).strip(),
                     r["nombre"], tipo, nif_norm, now, now),
                )
        self.conn.commit()

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

    def _normalize_empresa_activo(self, emp: dict | None):
        if not emp:
            return emp
        if "activo" not in emp or emp.get("activo") is None:
            emp["activo"] = 1
        if emp.get("digitos_plan") is None:
            emp["digitos_plan"] = 8
        return emp

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
        out = [self._row_to_dict(r) for r in cur.fetchall()]
        return [self._normalize_empresa_activo(e) for e in out]

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
        return self._normalize_empresa_activo(self._row_to_dict(cur.fetchone()))

    def upsert_empresa(self, emp: dict):
        existe = self.get_empresa(emp.get("codigo"), emp.get("ejercicio"))
        self.conn.execute(
            """
            INSERT INTO empresas (codigo, ejercicio, nombre, digitos_plan, serie_emitidas,
                siguiente_num_emitidas, serie_emitidas_rect, siguiente_num_emitidas_rect,
                pdf_ref_seq, cuenta_bancaria, cuentas_bancarias, cif, direccion, cp, poblacion, provincia, pais, telefono, email,
                logo_path, logo_max_width_mm, logo_max_height_mm, activo, naf)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(codigo, ejercicio) DO UPDATE SET
                nombre=excluded.nombre,
                digitos_plan=excluded.digitos_plan,
                serie_emitidas=excluded.serie_emitidas,
                siguiente_num_emitidas=excluded.siguiente_num_emitidas,
                serie_emitidas_rect=excluded.serie_emitidas_rect,
                siguiente_num_emitidas_rect=excluded.siguiente_num_emitidas_rect,
                pdf_ref_seq=excluded.pdf_ref_seq,
                cuenta_bancaria=excluded.cuenta_bancaria,
                cuentas_bancarias=excluded.cuentas_bancarias,
                cif=excluded.cif,
                direccion=excluded.direccion,
                cp=excluded.cp,
                poblacion=excluded.poblacion,
                provincia=excluded.provincia,
                pais=excluded.pais,
                telefono=excluded.telefono,
                email=excluded.email,
                logo_path=excluded.logo_path,
                logo_max_width_mm=excluded.logo_max_width_mm,
                logo_max_height_mm=excluded.logo_max_height_mm,
                activo=excluded.activo,
                naf=excluded.naf
            """,
            (
                emp.get("codigo"),
                _ej_val(emp.get("ejercicio")),
                emp.get("nombre"),
                emp.get("digitos_plan"),
                emp.get("serie_emitidas"),
                emp.get("siguiente_num_emitidas"),
                emp.get("serie_emitidas_rect"),
                emp.get("siguiente_num_emitidas_rect"),
                emp.get("pdf_ref_seq"),
                emp.get("cuenta_bancaria"),
                emp.get("cuentas_bancarias"),
                emp.get("cif"),
                emp.get("direccion"),
                emp.get("cp"),
                emp.get("poblacion"),
                emp.get("provincia"),
                emp.get("pais"),
                emp.get("telefono"),
                emp.get("email"),
                emp.get("logo_path"),
                emp.get("logo_max_width_mm"),
                emp.get("logo_max_height_mm"),
                1 if emp.get("activo", True) else 0,
                emp.get("naf"),
            ),
        )
        self.conn.commit()
        if not existe:
            self._clonar_plantillas_si_hace_falta(emp.get("codigo"), emp.get("ejercicio"))

    # ---------- Seguridad Social: NAF / CCC ----------
    def _migrate_seguridad_social(self):
        self._ensure_column("empresas", "naf", "TEXT")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS empresa_ccc (
                id             TEXT PRIMARY KEY,
                codigo_empresa TEXT NOT NULL,
                ccc            TEXT NOT NULL,
                descripcion    TEXT,
                activo         INTEGER NOT NULL DEFAULT 1,
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_empresa_ccc_emp
                ON empresa_ccc(codigo_empresa, activo);
            CREATE TABLE IF NOT EXISTS cert_solicitudes (
                id              TEXT PRIMARY KEY,
                codigo_empresa  TEXT NOT NULL,
                tipo            TEXT NOT NULL,
                organismo       TEXT,
                estado          TEXT NOT NULL DEFAULT 'PENDIENTE',
                resultado       TEXT,
                fecha_solicitud TEXT,
                fecha_obtencion TEXT,
                pdf_path        TEXT,
                referencia      TEXT,
                mensaje         TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_cert_sol_emp
                ON cert_solicitudes(codigo_empresa, tipo, estado);
            """
        )
        self.conn.commit()

    def listar_ccc(self, codigo_empresa: str, solo_activos: bool = False) -> list:
        sql = "SELECT * FROM empresa_ccc WHERE codigo_empresa=?"
        params = [codigo_empresa]
        if solo_activos:
            sql += " AND activo=1"
        sql += " ORDER BY ccc"
        cur = self.conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def upsert_ccc(self, ccc: dict) -> str:
        import uuid as _uuid
        now = self._utc_now()
        cid = str(ccc.get("id") or _uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO empresa_ccc (id, codigo_empresa, ccc, descripcion, activo, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                ccc         = excluded.ccc,
                descripcion = excluded.descripcion,
                activo      = excluded.activo,
                updated_at  = excluded.updated_at
            """,
            (
                cid,
                ccc.get("codigo_empresa"),
                (ccc.get("ccc") or "").strip(),
                ccc.get("descripcion"),
                int(ccc.get("activo", 1)),
                ccc.get("created_at", now),
                now,
            ),
        )
        self.conn.commit()
        return cid

    def eliminar_ccc(self, codigo_empresa: str, ccc_id: str) -> None:
        self.conn.execute(
            "DELETE FROM empresa_ccc WHERE id=? AND codigo_empresa=?",
            (ccc_id, codigo_empresa),
        )
        self.conn.commit()

    # ---------- Solicitudes / obtencion de certificados administrativos ----------
    def listar_cert_solicitudes(self, codigo_empresa: str, tipo: str | None = None) -> list:
        sql = "SELECT * FROM cert_solicitudes WHERE codigo_empresa=?"
        params = [codigo_empresa]
        if tipo:
            sql += " AND tipo=?"
            params.append(tipo)
        sql += " ORDER BY fecha_solicitud DESC, created_at DESC"
        cur = self.conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def upsert_cert_solicitud(self, sol: dict) -> str:
        import uuid as _uuid
        now = self._utc_now()
        sid = str(sol.get("id") or _uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO cert_solicitudes
                (id, codigo_empresa, tipo, organismo, estado, resultado,
                 fecha_solicitud, fecha_obtencion, pdf_path, referencia, mensaje,
                 created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                tipo            = excluded.tipo,
                organismo       = excluded.organismo,
                estado          = excluded.estado,
                resultado       = excluded.resultado,
                fecha_solicitud = excluded.fecha_solicitud,
                fecha_obtencion = excluded.fecha_obtencion,
                pdf_path        = excluded.pdf_path,
                referencia      = excluded.referencia,
                mensaje         = excluded.mensaje,
                updated_at      = excluded.updated_at
            """,
            (
                sid, sol.get("codigo_empresa"), sol.get("tipo"), sol.get("organismo"),
                sol.get("estado", "PENDIENTE"), sol.get("resultado"),
                sol.get("fecha_solicitud"), sol.get("fecha_obtencion"),
                sol.get("pdf_path"), sol.get("referencia"), sol.get("mensaje"),
                sol.get("created_at", now), now,
            ),
        )
        self.conn.commit()
        return sid

    def eliminar_cert_solicitud(self, codigo_empresa: str, sid: str) -> None:
        self.conn.execute(
            "DELETE FROM cert_solicitudes WHERE id=? AND codigo_empresa=?",
            (sid, codigo_empresa),
        )
        self.conn.commit()

    def listar_cert_solicitudes_global(self, filtros: dict | None = None) -> list:
        sql = """
            SELECT s.*, e.nombre AS empresa_nombre, e.cif AS empresa_cif, e.email AS empresa_email
            FROM cert_solicitudes s
            LEFT JOIN (SELECT codigo, nombre, cif, email, MAX(ejercicio) AS ejercicio
                       FROM empresas GROUP BY codigo) e ON e.codigo = s.codigo_empresa
            WHERE 1=1
        """
        params: list = []
        filtros = filtros or {}
        if filtros.get("codigo_empresa"):
            sql += " AND s.codigo_empresa=?"
            params.append(filtros["codigo_empresa"])
        if filtros.get("tipo"):
            sql += " AND s.tipo=?"
            params.append(filtros["tipo"])
        if filtros.get("estado"):
            sql += " AND s.estado=?"
            params.append(filtros["estado"])
        sql += " ORDER BY s.fecha_solicitud DESC, s.created_at DESC"
        cur = self.conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def next_pdf_ref(self, codigo_empresa: str, ejercicio: int | None = None) -> str:
        eje = _ej_val(ejercicio)
        row = self.get_empresa(codigo_empresa, eje)
        if not row and eje is not None:
            row = self.get_empresa(codigo_empresa, None)
        if not row:
            raise ValueError(f"Empresa no encontrada para generar referencia PDF: {codigo_empresa}")

        seq = int(row.get("pdf_ref_seq") or 0)
        if seq <= 0:
            cur = self.conn.execute(
                "SELECT pdf_ref FROM facturas_emitidas_docs WHERE codigo_empresa=? AND pdf_ref IS NOT NULL AND TRIM(pdf_ref)<>''",
                (codigo_empresa,),
            )
            for item in cur.fetchall():
                ref = str(item["pdf_ref"] or "").strip()
                base = ref.split("@", 1)[0]
                match = re.match(r"^E(\d{1,8})$", base, re.IGNORECASE)
                if match:
                    seq = max(seq, int(match.group(1)))

        seq += 1
        self.conn.execute(
            "UPDATE empresas SET pdf_ref_seq=? WHERE codigo=? AND ejercicio=?",
            (seq, str(row.get("codigo") or codigo_empresa), _ej_val(row.get("ejercicio"))),
        )
        self.conn.commit()
        return f"E{seq:08d}"

    # ── Plan de Cuentas ──────────────────────────────────────────────────────

    def upsert_plan_cuentas(self, codigo_empresa: str, ejercicio: int,
                             cuentas: list[dict]) -> int:
        """
        Reemplaza el plan de cuentas completo de una empresa/ejercicio.
        Cada elemento de 'cuentas' debe tener {'cuenta': str, 'descripcion': str}.
        Devuelve el número de cuentas guardadas.
        """
        eje = _ej_val(ejercicio)
        self.conn.execute(
            "DELETE FROM plan_cuentas WHERE codigo_empresa=? AND ejercicio=?",
            (codigo_empresa, eje),
        )
        normalized = []
        seen = set()
        for c in cuentas or []:
            cuenta = str(c.get("cuenta", "")).strip()
            if not cuenta or cuenta in seen:
                continue
            seen.add(cuenta)
            normalized.append((codigo_empresa, eje, cuenta, str(c.get("descripcion", "")).strip()))
        if normalized:
            self.conn.executemany(
                "INSERT OR REPLACE INTO plan_cuentas (codigo_empresa, ejercicio, cuenta, descripcion)"
                " VALUES (?, ?, ?, ?)",
                normalized,
            )
        self.conn.commit()
        return len(normalized)

    def get_plan_cuentas(self, codigo_empresa: str, ejercicio: int) -> list[dict]:
        """Devuelve el plan de cuentas de una empresa/ejercicio ordenado por cuenta."""
        eje = _ej_val(ejercicio)
        cur = self.conn.execute(
            "SELECT cuenta, descripcion FROM plan_cuentas"
            " WHERE codigo_empresa=? AND ejercicio=?"
            " ORDER BY CAST(cuenta AS INTEGER), cuenta",
            (codigo_empresa, eje),
        )
        return [dict(r) for r in cur.fetchall()]

    def buscar_cuentas_en_plan(self, codigo_empresa: str, ejercicio: int, prefijo: str) -> list[str]:
        """Devuelve cuentas del plan que empiezan por 'prefijo'. Util para propuesta de subcuenta."""
        eje = _ej_val(ejercicio)
        cur = self.conn.execute(
            "SELECT cuenta FROM plan_cuentas WHERE codigo_empresa=? AND ejercicio=? AND cuenta LIKE ?",
            (codigo_empresa, eje, prefijo + "%"),
        )
        return [r[0] for r in cur.fetchall()]

    def get_plan_cuentas_con_terceros(self, codigo_empresa: str, ejercicio: int) -> list[dict]:
        """
        Devuelve las subcuentas (≥4 dígitos) del plan de cuentas junto con el nombre
        y NIF del tercero asignado (si existe), usando las subcuentas definidas en
        terceros_empresas (cliente, proveedor, ingreso o gasto).
        """
        eje = _ej_val(ejercicio)
        cur = self.conn.execute(
            """
            SELECT
                pc.cuenta,
                pc.descripcion,
                t.nombre  AS tercero_nombre,
                t.nif     AS tercero_nif
            FROM plan_cuentas pc
            LEFT JOIN terceros_empresas te
                   ON te.codigo_empresa = pc.codigo_empresa
                  AND (te.subcuenta_cliente   = pc.cuenta
                    OR te.subcuenta_proveedor = pc.cuenta
                    OR te.subcuenta_ingreso   = pc.cuenta
                    OR te.subcuenta_gasto     = pc.cuenta)
            LEFT JOIN terceros t ON t.id = te.tercero_id
            WHERE pc.codigo_empresa = ?
              AND pc.ejercicio = ?
            GROUP BY pc.cuenta
            ORDER BY CAST(pc.cuenta AS INTEGER), pc.cuenta
            """,
            (codigo_empresa, eje),
        )
        return [dict(r) for r in cur.fetchall()]

    # ── Cuentas Bancarias ───────────────────────────────────────────────────

    def listar_cuentas_bancarias(self, codigo_empresa: str, ejercicio: int) -> list[dict]:
        eje = _ej_val(ejercicio)
        cur = self.conn.execute(
            """
            SELECT id, codigo_empresa, ejercicio, descripcion, iban, subcuenta_contable, origen, principal
            FROM cuentas_bancarias
            WHERE codigo_empresa=? AND ejercicio=?
            ORDER BY principal DESC, id ASC
            """,
            (codigo_empresa, eje),
        )
        return [self._row_to_dict(row) for row in cur.fetchall()]

    def reemplazar_cuentas_bancarias(self, codigo_empresa: str, ejercicio: int, cuentas: list[dict]) -> int:
        eje = _ej_val(ejercicio)
        now = self._utc_now()
        # Borra TODOS los registros de la empresa (cualquier ejercicio) antes de insertar
        # para evitar que registros en otros ejercicios reaparezcan tras un borrado
        self.conn.execute(
            "DELETE FROM cuentas_bancarias WHERE codigo_empresa=?",
            (codigo_empresa,),
        )
        inserted = 0
        for idx, cuenta in enumerate(cuentas or []):
            descripcion = str(cuenta.get("descripcion") or "").strip()
            iban = str(cuenta.get("iban") or "").strip()
            subcuenta = str(cuenta.get("subcuenta_contable") or "").strip()
            origen = str(cuenta.get("origen") or "").strip()
            if not (descripcion or iban or subcuenta):
                continue
            principal = 1 if cuenta.get("principal") or idx == 0 else 0
            self.conn.execute(
                """
                INSERT INTO cuentas_bancarias
                (codigo_empresa, ejercicio, descripcion, iban, subcuenta_contable, origen, principal, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (codigo_empresa, eje, descripcion, iban, subcuenta, origen, principal, now, now),
            )
            inserted += 1
        self.conn.commit()
        return inserted

    def eliminar_plan_cuentas(self, codigo_empresa: str, ejercicio: int) -> None:
        """Elimina el plan de cuentas de una empresa/ejercicio."""
        eje = _ej_val(ejercicio)
        self.conn.execute(
            "DELETE FROM plan_cuentas WHERE codigo_empresa=? AND ejercicio=?",
            (codigo_empresa, eje),
        )
        self.conn.commit()

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
            "albaranes_emitidas_docs",
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

    def normalizar_codigos_empresas_a3(self) -> dict:
        rows = self.listar_empresas()
        mapping = {}
        seen = set()
        for row in rows:
            old_code = str(row.get("codigo") or "")
            new_code = _codigo_empresa_a3(old_code)
            if not new_code:
                continue
            key = (new_code, _ej_val(row.get("ejercicio")))
            if key in seen and old_code != new_code:
                raise ValueError(f"Conflicto al normalizar codigos: {old_code} y otra empresa pasan a {new_code}.")
            seen.add(key)
            if old_code != new_code:
                mapping[old_code] = new_code

        code_tables = (
            ("empresas", "codigo"),
            ("bancos", "codigo_empresa"),
            ("facturas_emitidas", "codigo_empresa"),
            ("facturas_recibidas", "codigo_empresa"),
            ("facturas_emitidas_docs", "codigo_empresa"),
            ("albaranes_emitidas_docs", "codigo_empresa"),
            ("terceros_empresas", "codigo_empresa"),
            ("usuarios_empresas", "empresa_codigo"),
        )
        for table, column in code_tables:
            cur = self.conn.execute(f"SELECT DISTINCT {column} FROM {table}")
            for (value,) in cur.fetchall():
                old_code = str(value or "")
                new_code = _codigo_empresa_a3(old_code)
                if old_code and new_code and old_code != new_code:
                    mapping.setdefault(old_code, new_code)
        if not mapping:
            return {"updated_companies": 0, "mapping": {}}
        with self.conn:
            for old_code, new_code in mapping.items():
                for table, column in code_tables:
                    self.conn.execute(
                        f"UPDATE {table} SET {column}=? WHERE {column}=?",
                        (new_code, old_code),
                    )
        return {"updated_companies": len(mapping), "mapping": mapping}

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
                cuenta_ingreso_por_defecto, cuenta_iva_repercutido_defecto, cuenta_retenciones_irpf, excel_json)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(codigo_empresa, ejercicio, nombre) DO UPDATE SET
                cuenta_cliente_prefijo=excluded.cuenta_cliente_prefijo,
                cuenta_ingreso_por_defecto=excluded.cuenta_ingreso_por_defecto,
                cuenta_iva_repercutido_defecto=excluded.cuenta_iva_repercutido_defecto,
                cuenta_retenciones_irpf=excluded.cuenta_retenciones_irpf,
                excel_json=excluded.excel_json
            """,
            (
                plantilla.get("codigo_empresa"),
                eje,
                plantilla.get("nombre"),
                plantilla.get("cuenta_cliente_prefijo"),
                plantilla.get("cuenta_ingreso_por_defecto"),
                plantilla.get("cuenta_iva_repercutido_defecto"),
                plantilla.get("cuenta_retenciones_irpf"),
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
    def enviar_facturas_emitidas_a_contabilidad(self, codigo_empresa: str, ejercicio: int, ids: list):
        """Marca las facturas como pendientes de generar suenlace en el módulo de contabilidad."""
        ids = ids or []
        if not ids:
            return
        qmarks = ",".join("?" for _ in ids)
        self.conn.execute(
            f"UPDATE facturas_emitidas_docs SET estado_contable='pendiente' WHERE codigo_empresa=? AND ejercicio=? AND (estado_contable IS NULL OR estado_contable='') AND id IN ({qmarks})",
            (codigo_empresa, _ej_val(ejercicio), *ids),
        )
        self.conn.commit()

    def listar_facturas_emitidas_en_contabilidad(self, codigo_empresa: str, ejercicio: int):
        """Devuelve las facturas emitidas con estado_contable pendiente o generado."""
        cur = self.conn.execute(
            "SELECT * FROM facturas_emitidas_docs WHERE codigo_empresa=? AND ejercicio=? AND estado_contable IS NOT NULL AND estado_contable != '' ORDER BY fecha_asiento, numero",
            (codigo_empresa, _ej_val(ejercicio)),
        )
        out = []
        for r in cur.fetchall():
            d = self._row_to_dict(r)
            d["lineas"] = json.loads(d.get("lineas_json") or "[]")
            d["generada"] = bool(d.get("generada"))
            d["enviado"] = bool(d.get("enviado"))
            d["retencion_aplica"] = bool(d.get("retencion_aplica"))
            d["borrador"] = bool(d.get("borrador"))
            self._normalizar_campos_factura_emitida(d)
            d.pop("lineas_json", None)
            out.append(d)
        return out

    def quitar_facturas_emitidas_de_contabilidad(self, codigo_empresa: str, ejercicio: int, ids: list):
        """Quita del modulo de contabilidad las facturas en estado pendiente (sin suenlace generado)."""
        ids = ids or []
        if not ids:
            return 0
        qmarks = ",".join("?" for _ in ids)
        cur = self.conn.execute(
            f"UPDATE facturas_emitidas_docs SET estado_contable=NULL WHERE codigo_empresa=? AND ejercicio=? AND estado_contable='pendiente' AND id IN ({qmarks})",
            (codigo_empresa, _ej_val(ejercicio), *ids),
        )
        self.conn.commit()
        return cur.rowcount

    def resetear_facturas_emitidas_generadas(self, codigo_empresa: str, ejercicio: int, ids: list):
        """Revierte el estado 'generado' a NULL para permitir regenerar el suenlace."""
        ids = ids or []
        if not ids:
            return 0
        qmarks = ",".join("?" for _ in ids)
        cur = self.conn.execute(
            f"UPDATE facturas_emitidas_docs SET estado_contable=NULL WHERE codigo_empresa=? AND ejercicio=? AND estado_contable='generado' AND id IN ({qmarks})",
            (codigo_empresa, _ej_val(ejercicio), *ids),
        )
        self.conn.commit()
        return cur.rowcount

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
            d["enviado"] = bool(d.get("enviado"))
            d["retencion_aplica"] = bool(d.get("retencion_aplica"))
            d["borrador"] = bool(d.get("borrador"))
            self._normalizar_campos_factura_emitida(d)
            d.pop("lineas_json", None)
            out.append(d)
        return out

    def listar_facturas_emitidas_global(self, codigo_empresa: str, ejercicio: int | None = None, tercero_id: str | None = None):
        params = [codigo_empresa]
        where = ["codigo_empresa=?"]
        if ejercicio is not None:
            where.append("ejercicio=?")
            params.append(_ej_val(ejercicio))
        if tercero_id:
            where.append("tercero_id=?")
            params.append(tercero_id)
        sql = "SELECT * FROM facturas_emitidas_docs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ejercicio, fecha_asiento, numero"
        cur = self.conn.execute(sql, tuple(params))
        out = []
        for r in cur.fetchall():
            d = self._row_to_dict(r)
            d["lineas"] = json.loads(d.get("lineas_json") or "[]")
            d["generada"] = bool(d.get("generada"))
            d["enviado"] = bool(d.get("enviado"))
            d["retencion_aplica"] = bool(d.get("retencion_aplica"))
            self._normalizar_campos_factura_emitida(d)
            d.pop("lineas_json", None)
            out.append(d)
        return out

    def listar_facturas_emitidas_todas(self, codigo_empresa: str | None = None, ejercicio: int | None = None, tercero_id: str | None = None):
        params = []
        where = []
        if codigo_empresa:
            where.append("codigo_empresa=?")
            params.append(codigo_empresa)
        if ejercicio is not None:
            where.append("ejercicio=?")
            params.append(_ej_val(ejercicio))
        if tercero_id:
            where.append("tercero_id=?")
            params.append(tercero_id)
        sql = "SELECT * FROM facturas_emitidas_docs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY codigo_empresa, ejercicio, fecha_asiento, numero"
        cur = self.conn.execute(sql, tuple(params))
        out = []
        for r in cur.fetchall():
            d = self._row_to_dict(r)
            d["lineas"] = json.loads(d.get("lineas_json") or "[]")
            d["generada"] = bool(d.get("generada"))
            d["enviado"] = bool(d.get("enviado"))
            d["retencion_aplica"] = bool(d.get("retencion_aplica"))
            self._normalizar_campos_factura_emitida(d)
            d.pop("lineas_json", None)
            out.append(d)
        return out

    def _normalizar_campos_factura_emitida(self, factura: dict):
        if not str(factura.get("tipo_operacion") or "").strip():
            factura["tipo_operacion"] = "01"

    def listar_ejercicios_facturas_emitidas(self, codigo_empresa: str):
        cur = self.conn.execute(
            "SELECT DISTINCT ejercicio FROM facturas_emitidas_docs WHERE codigo_empresa=? ORDER BY ejercicio",
            (codigo_empresa,),
        )
        return [r["ejercicio"] for r in cur.fetchall() if r["ejercicio"] is not None]

    def listar_clientes_facturas_emitidas(self, codigo_empresa: str, ejercicio: int | None = None):
        params = [codigo_empresa]
        where = ["codigo_empresa=?"]
        if ejercicio is not None:
            where.append("ejercicio=?")
            params.append(_ej_val(ejercicio))
        sql = "SELECT tercero_id, nombre, nif FROM facturas_emitidas_docs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY nombre"
        cur = self.conn.execute(sql, tuple(params))
        seen = {}
        for r in cur.fetchall():
            tid = str(r["tercero_id"] or "").strip()
            key = tid or str(r["nombre"] or "").strip().upper()
            if not key:
                continue
            if key in seen:
                continue
            seen[key] = {
                "tercero_id": tid,
                "nombre": r["nombre"] or "",
                "nif": r["nif"] or "",
            }
        out = list(seen.values())
        out.sort(key=lambda d: (d.get("nombre") or "").lower())
        return out

    def upsert_factura_emitida(self, factura: dict):
        fid = factura.get("id") or str(int(time.time() * 1000))
        factura["id"] = fid
        self._normalizar_campos_factura_emitida(factura)
        eje = _ej_val(factura.get("ejercicio"))
        if eje is None:
            eje = 0
        self.conn.execute(
            """
            INSERT INTO facturas_emitidas_docs
            (id, codigo_empresa, ejercicio, tercero_id, serie, numero, numero_largo_sii, numero_asiento,
             fecha_asiento, fecha_expedicion, fecha_operacion, tipo_operacion, modelo_fiscal, nif, nombre, descripcion, observaciones,
             subcuenta_cliente, forma_pago, cuenta_bancaria, plantilla_word, plantilla_emitidas, pdf_path, pdf_ref, pdf_path_a3, retencion_aplica, retencion_pct,
             retencion_base, retencion_importe, descuento_total_tipo, descuento_total_valor, moneda_codigo, moneda_simbolo, enviado, fecha_envio, canal_envio, generada, fecha_generacion, lineas_json, borrador,
             subcuenta_ingreso, subcuenta_iva, subcuenta_retencion, facturae_xml_path, facturae_generated_at, facturae_status, facturae_error)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                codigo_empresa=excluded.codigo_empresa,
                ejercicio=excluded.ejercicio,
                tercero_id=excluded.tercero_id,
                serie=excluded.serie,
                numero=excluded.numero,
                numero_largo_sii=excluded.numero_largo_sii,
                numero_asiento=excluded.numero_asiento,
                fecha_asiento=excluded.fecha_asiento,
                fecha_expedicion=excluded.fecha_expedicion,
                fecha_operacion=excluded.fecha_operacion,
                tipo_operacion=excluded.tipo_operacion,
                modelo_fiscal=excluded.modelo_fiscal,
                nif=excluded.nif,
                nombre=excluded.nombre,
                descripcion=excluded.descripcion,
                observaciones=excluded.observaciones,
                subcuenta_cliente=excluded.subcuenta_cliente,
                forma_pago=excluded.forma_pago,
                cuenta_bancaria=excluded.cuenta_bancaria,
                plantilla_word=excluded.plantilla_word,
                plantilla_emitidas=excluded.plantilla_emitidas,
                pdf_path=excluded.pdf_path,
                pdf_ref=excluded.pdf_ref,
                pdf_path_a3=excluded.pdf_path_a3,
                retencion_aplica=excluded.retencion_aplica,
                retencion_pct=excluded.retencion_pct,
                retencion_base=excluded.retencion_base,
                retencion_importe=excluded.retencion_importe,
                descuento_total_tipo=excluded.descuento_total_tipo,
                descuento_total_valor=excluded.descuento_total_valor,
                moneda_codigo=excluded.moneda_codigo,
                moneda_simbolo=excluded.moneda_simbolo,
                enviado=excluded.enviado,
                fecha_envio=excluded.fecha_envio,
                canal_envio=excluded.canal_envio,
                generada=excluded.generada,
                fecha_generacion=excluded.fecha_generacion,
                lineas_json=excluded.lineas_json,
                borrador=excluded.borrador,
                subcuenta_ingreso=excluded.subcuenta_ingreso,
                subcuenta_iva=excluded.subcuenta_iva,
                subcuenta_retencion=excluded.subcuenta_retencion,
                facturae_xml_path=excluded.facturae_xml_path,
                facturae_generated_at=excluded.facturae_generated_at,
                facturae_status=excluded.facturae_status,
                facturae_error=excluded.facturae_error
            """,
            (
                fid,
                factura.get("codigo_empresa"),
                eje,
                factura.get("tercero_id"),
                factura.get("serie"),
                factura.get("numero"),
                factura.get("numero_largo_sii"),
                factura.get("numero_asiento"),
                factura.get("fecha_asiento"),
                factura.get("fecha_expedicion"),
                factura.get("fecha_operacion"),
                factura.get("tipo_operacion"),
                factura.get("modelo_fiscal"),
                factura.get("nif"),
                factura.get("nombre"),
                factura.get("descripcion"),
                factura.get("observaciones"),
                factura.get("subcuenta_cliente"),
                factura.get("forma_pago"),
                factura.get("cuenta_bancaria"),
                factura.get("plantilla_word"),
                factura.get("plantilla_emitidas"),
                factura.get("pdf_path"),
                factura.get("pdf_ref"),
                factura.get("pdf_path_a3"),
                1 if factura.get("retencion_aplica") else 0,
                factura.get("retencion_pct"),
                factura.get("retencion_base"),
                factura.get("retencion_importe"),
                factura.get("descuento_total_tipo"),
                factura.get("descuento_total_valor"),
                factura.get("moneda_codigo"),
                factura.get("moneda_simbolo"),
                1 if factura.get("enviado") else 0,
                factura.get("fecha_envio"),
                factura.get("canal_envio"),
                1 if factura.get("generada") else 0,
                factura.get("fecha_generacion"),
                json.dumps(factura.get("lineas", []), ensure_ascii=False),
                1 if factura.get("borrador") else 0,
                factura.get("subcuenta_ingreso"),
                factura.get("subcuenta_iva"),
                factura.get("subcuenta_retencion"),
                factura.get("facturae_xml_path"),
                factura.get("facturae_generated_at"),
                factura.get("facturae_status"),
                factura.get("facturae_error"),
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
        self.conn.execute(
            f"UPDATE facturas_emitidas_docs SET estado_contable='generado' WHERE codigo_empresa=? AND ejercicio=? AND estado_contable='pendiente' AND id IN ({qmarks})",
            (codigo_empresa, _ej_val(ejercicio), *ids),
        )
        self.conn.commit()

    def desmarcar_facturas_emitidas_generadas(self, codigo_empresa: str, ids: list, ejercicio: int):
        ids = ids or []
        if not ids:
            return
        qmarks = ",".join("?" for _ in ids)
        self.conn.execute(
            f"UPDATE facturas_emitidas_docs SET generada=0, fecha_generacion='' WHERE codigo_empresa=? AND ejercicio=? AND id IN ({qmarks})",
            (codigo_empresa, _ej_val(ejercicio), *ids),
        )
        self.conn.commit()

    def marcar_factura_emitida_enviada(self, codigo_empresa: str, factura_id: str, fecha: str, canal: str | None, ejercicio: int):
        self.conn.execute(
            "UPDATE facturas_emitidas_docs SET enviado=1, fecha_envio=?, canal_envio=? WHERE codigo_empresa=? AND ejercicio=? AND id=?",
            (fecha, canal, codigo_empresa, _ej_val(ejercicio), factura_id),
        )
        self.conn.commit()

    # ---------- ALBARANES EMITIDOS ----------
    def listar_albaranes_emitidas(self, codigo_empresa: str, ejercicio: int):
        cur = self.conn.execute(
            "SELECT * FROM albaranes_emitidas_docs WHERE codigo_empresa=? AND ejercicio=? ORDER BY fecha_asiento, numero",
            (codigo_empresa, _ej_val(ejercicio)),
        )
        out = []
        for r in cur.fetchall():
            d = self._row_to_dict(r)
            d["lineas"] = json.loads(d.get("lineas_json") or "[]")
            d["facturado"] = bool(d.get("facturado"))
            d["retencion_aplica"] = bool(d.get("retencion_aplica"))
            d.pop("lineas_json", None)
            out.append(d)
        return out

    def upsert_albaran_emitida(self, albaran: dict):
        aid = albaran.get("id") or str(int(time.time() * 1000))
        albaran["id"] = aid
        eje = _ej_val(albaran.get("ejercicio"))
        if eje is None:
            eje = 0
        self.conn.execute(
            """
            INSERT INTO albaranes_emitidas_docs
            (id, codigo_empresa, ejercicio, tercero_id, serie, numero, numero_largo_sii,
             fecha_asiento, fecha_expedicion, fecha_operacion, nif, nombre, descripcion, observaciones,
             subcuenta_cliente, forma_pago, cuenta_bancaria, pdf_path, pdf_ref, retencion_aplica, retencion_pct,
             retencion_base, retencion_importe, moneda_codigo, moneda_simbolo, facturado, factura_id, fecha_facturacion,
             tipo_operacion, plantilla_emitidas, plantilla_word, lineas_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                observaciones=excluded.observaciones,
                subcuenta_cliente=excluded.subcuenta_cliente,
                forma_pago=excluded.forma_pago,
                cuenta_bancaria=excluded.cuenta_bancaria,
                pdf_path=excluded.pdf_path,
                pdf_ref=excluded.pdf_ref,
                retencion_aplica=excluded.retencion_aplica,
                retencion_pct=excluded.retencion_pct,
                retencion_base=excluded.retencion_base,
                retencion_importe=excluded.retencion_importe,
                moneda_codigo=excluded.moneda_codigo,
                moneda_simbolo=excluded.moneda_simbolo,
                facturado=excluded.facturado,
                factura_id=excluded.factura_id,
                fecha_facturacion=excluded.fecha_facturacion,
                tipo_operacion=excluded.tipo_operacion,
                plantilla_emitidas=excluded.plantilla_emitidas,
                plantilla_word=excluded.plantilla_word,
                lineas_json=excluded.lineas_json
            """,
            (
                aid,
                albaran.get("codigo_empresa"),
                eje,
                albaran.get("tercero_id"),
                albaran.get("serie"),
                albaran.get("numero"),
                albaran.get("numero_largo_sii"),
                albaran.get("fecha_asiento"),
                albaran.get("fecha_expedicion"),
                albaran.get("fecha_operacion"),
                albaran.get("nif"),
                albaran.get("nombre"),
                albaran.get("descripcion"),
                albaran.get("observaciones"),
                albaran.get("subcuenta_cliente"),
                albaran.get("forma_pago"),
                albaran.get("cuenta_bancaria"),
                albaran.get("pdf_path"),
                albaran.get("pdf_ref"),
                1 if albaran.get("retencion_aplica") else 0,
                albaran.get("retencion_pct"),
                albaran.get("retencion_base"),
                albaran.get("retencion_importe"),
                albaran.get("moneda_codigo"),
                albaran.get("moneda_simbolo"),
                1 if albaran.get("facturado") else 0,
                albaran.get("factura_id"),
                albaran.get("fecha_facturacion"),
                albaran.get("tipo_operacion") or "01",
                albaran.get("plantilla_emitidas"),
                albaran.get("plantilla_word"),
                json.dumps(albaran.get("lineas", []), ensure_ascii=False),
            ),
        )
        self.conn.commit()
        return aid

    def eliminar_albaran_emitida(self, codigo_empresa: str, albaran_id: str, ejercicio: int):
        self.conn.execute(
            "DELETE FROM albaranes_emitidas_docs WHERE codigo_empresa=? AND ejercicio=? AND id=?",
            (codigo_empresa, _ej_val(ejercicio), albaran_id),
        )
        self.conn.commit()

    def marcar_albaranes_facturados(self, codigo_empresa: str, ids: list, factura_id: str, fecha: str, ejercicio: int):
        ids = ids or []
        if not ids:
            return
        qmarks = ",".join("?" for _ in ids)
        self.conn.execute(
            f"UPDATE albaranes_emitidas_docs SET facturado=1, factura_id=?, fecha_facturacion=? WHERE codigo_empresa=? AND ejercicio=? AND id IN ({qmarks})",
            (factura_id, fecha, codigo_empresa, _ej_val(ejercicio), *ids),
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

    # ---------- RECIBIDAS (documentos OCR / contabilidad) ----------
    def listar_facturas_recibidas_docs(self, codigo_empresa: str, ejercicio: int):
        cur = self.conn.execute(
            """
            SELECT d.*, a.id AS asiento_id, a.estado AS asiento_estado, a.total_debe, a.total_haber
            FROM facturas_recibidas_docs d
            LEFT JOIN asientos_contables a ON a.documento_id = d.id
            WHERE d.codigo_empresa=? AND d.ejercicio=?
            ORDER BY d.fecha_asiento DESC, d.updated_at DESC
            """,
            (codigo_empresa, _ej_val(ejercicio)),
        )
        return [self._row_to_factura_recibida_doc(r) for r in cur.fetchall()]

    def listar_facturas_recibidas_docs_filtrado(self, codigo_empresa: str, ejercicio: int, estado: str | None = None):
        """Devuelve documentos OCR filtrados por estado compuesto (bandeja).

        estado puede ser:
          'procesando'            -> estado_ocr IN ('pendiente', 'procesando')
          'error'                 -> estado_ocr = 'error'
          'pendiente_revision'    -> estado_ocr = 'procesado' AND estado_validacion = 'pendiente'
          'pendiente_contabilizar'-> estado_validacion = 'validada' AND estado_contable = 'pendiente_contabilizar'
          'contabilizada'         -> estado_contable = 'contabilizada'
          None                    -> todos
        """
        base_sql = """
            SELECT d.*, a.id AS asiento_id, a.estado AS asiento_estado, a.total_debe, a.total_haber
            FROM facturas_recibidas_docs d
            LEFT JOIN asientos_contables a ON a.documento_id = d.id
            WHERE d.codigo_empresa=? AND d.ejercicio=?
        """
        params: list = [codigo_empresa, _ej_val(ejercicio)]
        if estado == "procesando":
            base_sql += " AND d.estado_ocr IN ('pendiente', 'procesando')"
        elif estado == "error":
            base_sql += " AND d.estado_ocr = 'error'"
        elif estado == "pendiente_revision":
            base_sql += " AND d.estado_ocr = 'procesado' AND (d.estado_validacion IS NULL OR d.estado_validacion = 'pendiente')"
        elif estado == "pendiente_contabilizar":
            base_sql += " AND d.estado_validacion = 'validada' AND d.estado_contable = 'pendiente_contabilizar'"
        elif estado == "contabilizada":
            base_sql += " AND d.estado_contable = 'contabilizada'"
        base_sql += " ORDER BY d.updated_at DESC"
        cur = self.conn.execute(base_sql, params)
        return [self._row_to_factura_recibida_doc(r) for r in cur.fetchall()]

    def get_factura_recibida_doc(self, doc_id: str):
        cur = self.conn.execute(
            """
            SELECT d.*, a.id AS asiento_id, a.estado AS asiento_estado, a.total_debe, a.total_haber
            FROM facturas_recibidas_docs d
            LEFT JOIN asientos_contables a ON a.documento_id = d.id
            WHERE d.id=?
            """,
            (str(doc_id),),
        )
        return self._row_to_factura_recibida_doc(cur.fetchone())

    def upsert_factura_recibida_doc(self, doc: dict):
        now = self._utc_now()
        doc_id = str(doc.get("id") or int(time.time() * 1000))
        doc["id"] = doc_id
        doc["proveedor_tipo_operacion_iva"] = (
            doc.get("proveedor_tipo_operacion_iva") or "INTERIOR_DEDUCIBLE"
        )
        if doc.get("proveedor_iva_deducible") is None:
            doc["proveedor_iva_deducible"] = 1
        if doc.get("proveedor_porcentaje_deduccion_iva") is None:
            doc["proveedor_porcentaje_deduccion_iva"] = 100.0
        self.conn.execute(
            """
            INSERT INTO facturas_recibidas_docs
            (id, codigo_empresa, ejercicio, tercero_id, origen_path, pdf_path, texto_ocr, estado_ocr, estado_validacion,
             estado_contable, proveedor_nif, proveedor_nombre, numero_factura, fecha_factura, fecha_operacion, fecha_asiento,
             descripcion, moneda_codigo, base_imponible, cuota_iva, cuota_recargo, cuota_retencion, total, cuenta_gasto,
             cuenta_iva, cuenta_proveedor, proveedor_tipo_operacion_iva, proveedor_iva_deducible, proveedor_porcentaje_deduccion_iva,
             pdf_ref, numero_asiento, generada, fecha_generacion, confianza_ocr, datos_extra_json,
             lineas_json, tipo_documento, tipo_operacion, fecha_vencimiento, fecha_contabilizacion,
             fecha_ocr, fecha_validacion, lote_generacion, error_mensaje,
             created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                codigo_empresa=excluded.codigo_empresa,
                ejercicio=excluded.ejercicio,
                tercero_id=excluded.tercero_id,
                origen_path=excluded.origen_path,
                pdf_path=excluded.pdf_path,
                texto_ocr=excluded.texto_ocr,
                estado_ocr=excluded.estado_ocr,
                estado_validacion=excluded.estado_validacion,
                estado_contable=excluded.estado_contable,
                proveedor_nif=excluded.proveedor_nif,
                proveedor_nombre=excluded.proveedor_nombre,
                numero_factura=excluded.numero_factura,
                fecha_factura=excluded.fecha_factura,
                fecha_operacion=excluded.fecha_operacion,
                fecha_asiento=excluded.fecha_asiento,
                descripcion=excluded.descripcion,
                moneda_codigo=excluded.moneda_codigo,
                base_imponible=excluded.base_imponible,
                cuota_iva=excluded.cuota_iva,
                cuota_recargo=excluded.cuota_recargo,
                cuota_retencion=excluded.cuota_retencion,
                total=excluded.total,
                cuenta_gasto=excluded.cuenta_gasto,
                cuenta_iva=excluded.cuenta_iva,
                cuenta_proveedor=excluded.cuenta_proveedor,
                proveedor_tipo_operacion_iva=excluded.proveedor_tipo_operacion_iva,
                proveedor_iva_deducible=excluded.proveedor_iva_deducible,
                proveedor_porcentaje_deduccion_iva=excluded.proveedor_porcentaje_deduccion_iva,
                pdf_ref=excluded.pdf_ref,
                numero_asiento=excluded.numero_asiento,
                generada=excluded.generada,
                fecha_generacion=excluded.fecha_generacion,
                confianza_ocr=excluded.confianza_ocr,
                datos_extra_json=excluded.datos_extra_json,
                lineas_json=excluded.lineas_json,
                tipo_documento=excluded.tipo_documento,
                tipo_operacion=excluded.tipo_operacion,
                fecha_vencimiento=excluded.fecha_vencimiento,
                fecha_contabilizacion=excluded.fecha_contabilizacion,
                fecha_ocr=excluded.fecha_ocr,
                fecha_validacion=excluded.fecha_validacion,
                lote_generacion=excluded.lote_generacion,
                error_mensaje=excluded.error_mensaje,
                updated_at=excluded.updated_at
            """,
            (
                doc_id,
                doc.get("codigo_empresa"),
                _ej_val(doc.get("ejercicio")) or 0,
                doc.get("tercero_id"),
                doc.get("origen_path"),
                doc.get("pdf_path"),
                doc.get("texto_ocr"),
                doc.get("estado_ocr"),
                doc.get("estado_validacion"),
                doc.get("estado_contable"),
                doc.get("proveedor_nif"),
                doc.get("proveedor_nombre"),
                doc.get("numero_factura"),
                doc.get("fecha_factura"),
                doc.get("fecha_operacion"),
                doc.get("fecha_asiento"),
                doc.get("descripcion"),
                doc.get("moneda_codigo"),
                doc.get("base_imponible"),
                doc.get("cuota_iva"),
                doc.get("cuota_recargo"),
                doc.get("cuota_retencion"),
                doc.get("total"),
                doc.get("cuenta_gasto"),
                doc.get("cuenta_iva"),
                doc.get("cuenta_proveedor"),
                doc.get("proveedor_tipo_operacion_iva"),
                doc.get("proveedor_iva_deducible"),
                doc.get("proveedor_porcentaje_deduccion_iva"),
                doc.get("pdf_ref"),
                doc.get("numero_asiento"),
                1 if doc.get("generada") else 0,
                doc.get("fecha_generacion"),
                doc.get("confianza_ocr"),
                json.dumps(doc.get("datos_extra") or {}, ensure_ascii=False),
                json.dumps(doc.get("lineas") or [], ensure_ascii=False),
                doc.get("tipo_documento") or "factura_recibida",
                doc.get("tipo_operacion") or "interior",
                doc.get("fecha_vencimiento"),
                doc.get("fecha_contabilizacion"),
                doc.get("fecha_ocr"),
                doc.get("fecha_validacion"),
                doc.get("lote_generacion"),
                doc.get("error_mensaje"),
                doc.get("created_at") or now,
                now,
            ),
        )
        self.conn.commit()
        return doc_id

    def eliminar_factura_recibida_doc(self, doc_id: str):
        self.conn.execute("DELETE FROM facturas_recibidas_docs WHERE id=?", (str(doc_id),))
        self.conn.commit()

    # ---------- LÍNEAS FISCALES OCR ----------

    def listar_ocr_lineas_doc(self, doc_id: str) -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM ocr_lineas_fiscales WHERE doc_id=? ORDER BY orden",
            (str(doc_id),),
        )
        return [dict(r) for r in cur.fetchall()]

    def upsert_ocr_linea(self, linea: dict) -> int:
        linea_id = linea.get("id")
        if linea_id:
            self.conn.execute(
                """
                UPDATE ocr_lineas_fiscales SET
                    orden=?, tipo_iva=?, base_imponible=?, cuota_iva=?,
                    tipo_recargo=?, cuota_recargo=?, tipo_retencion=?, cuota_retencion=?,
                    cuenta_base=?, cuenta_iva=?, cuenta_retencion=?, tipo_operacion_linea=?
                WHERE id=?
                """,
                (
                    linea.get("orden", 0),
                    linea.get("tipo_iva"),
                    linea.get("base_imponible"),
                    linea.get("cuota_iva"),
                    linea.get("tipo_recargo"),
                    linea.get("cuota_recargo"),
                    linea.get("tipo_retencion"),
                    linea.get("cuota_retencion"),
                    linea.get("cuenta_base"),
                    linea.get("cuenta_iva"),
                    linea.get("cuenta_retencion"),
                    linea.get("tipo_operacion_linea"),
                    linea_id,
                ),
            )
            self.conn.commit()
            return linea_id
        cur = self.conn.execute(
            """
            INSERT INTO ocr_lineas_fiscales
            (doc_id, orden, tipo_iva, base_imponible, cuota_iva,
             tipo_recargo, cuota_recargo, tipo_retencion, cuota_retencion,
             cuenta_base, cuenta_iva, cuenta_retencion, tipo_operacion_linea)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(linea["doc_id"]),
                linea.get("orden", 0),
                linea.get("tipo_iva"),
                linea.get("base_imponible"),
                linea.get("cuota_iva"),
                linea.get("tipo_recargo"),
                linea.get("cuota_recargo"),
                linea.get("tipo_retencion"),
                linea.get("cuota_retencion"),
                linea.get("cuenta_base"),
                linea.get("cuenta_iva"),
                linea.get("cuenta_retencion"),
                linea.get("tipo_operacion_linea"),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def eliminar_ocr_linea(self, linea_id: int):
        self.conn.execute("DELETE FROM ocr_lineas_fiscales WHERE id=?", (linea_id,))
        self.conn.commit()

    def reemplazar_ocr_lineas_doc(self, doc_id: str, lineas: list[dict]):
        """Borra todas las líneas del documento y las reinserta en orden."""
        self.conn.execute("DELETE FROM ocr_lineas_fiscales WHERE doc_id=?", (str(doc_id),))
        for idx, linea in enumerate(lineas):
            linea = dict(linea)
            linea.pop("id", None)
            linea["doc_id"] = str(doc_id)
            linea["orden"] = idx
            self.conn.execute(
                """
                INSERT INTO ocr_lineas_fiscales
                (doc_id, orden, tipo_iva, base_imponible, cuota_iva,
                 tipo_recargo, cuota_recargo, tipo_retencion, cuota_retencion,
                 cuenta_base, cuenta_iva, cuenta_retencion, tipo_operacion_linea)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    linea["doc_id"],
                    linea["orden"],
                    linea.get("tipo_iva"),
                    linea.get("base_imponible"),
                    linea.get("cuota_iva"),
                    linea.get("tipo_recargo"),
                    linea.get("cuota_recargo"),
                    linea.get("tipo_retencion"),
                    linea.get("cuota_retencion"),
                    linea.get("cuenta_base"),
                    linea.get("cuenta_iva"),
                    linea.get("cuenta_retencion"),
                    linea.get("tipo_operacion_linea"),
                ),
            )
        self.conn.commit()

    def get_asiento_contable_por_documento(self, documento_id: str):
        cur = self.conn.execute(
            "SELECT * FROM asientos_contables WHERE documento_id=?",
            (str(documento_id),),
        )
        return self._row_to_asiento_contable(cur.fetchone())

    def listar_asientos_contables(self, codigo_empresa: str, ejercicio: int):
        cur = self.conn.execute(
            """
            SELECT a.*, d.proveedor_nombre, d.numero_factura
            FROM asientos_contables a
            LEFT JOIN facturas_recibidas_docs d ON d.id = a.documento_id
            WHERE a.codigo_empresa=? AND a.ejercicio=?
            ORDER BY a.fecha_asiento DESC, a.updated_at DESC
            """,
            (codigo_empresa, _ej_val(ejercicio)),
        )
        return [self._row_to_asiento_contable(r) for r in cur.fetchall()]

    def upsert_asiento_contable(self, asiento: dict):
        now = self._utc_now()
        self.conn.execute(
            """
            INSERT INTO asientos_contables
            (documento_id, codigo_empresa, ejercicio, fecha_asiento, numero_asiento, descripcion, estado,
             total_debe, total_haber, lineas_json, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(documento_id) DO UPDATE SET
                codigo_empresa=excluded.codigo_empresa,
                ejercicio=excluded.ejercicio,
                fecha_asiento=excluded.fecha_asiento,
                numero_asiento=excluded.numero_asiento,
                descripcion=excluded.descripcion,
                estado=excluded.estado,
                total_debe=excluded.total_debe,
                total_haber=excluded.total_haber,
                lineas_json=excluded.lineas_json,
                updated_at=excluded.updated_at
            """,
            (
                asiento.get("documento_id"),
                asiento.get("codigo_empresa"),
                _ej_val(asiento.get("ejercicio")) or 0,
                asiento.get("fecha_asiento"),
                asiento.get("numero_asiento"),
                asiento.get("descripcion"),
                asiento.get("estado"),
                asiento.get("total_debe"),
                asiento.get("total_haber"),
                json.dumps(asiento.get("lineas") or [], ensure_ascii=False),
                asiento.get("created_at") or now,
                now,
            ),
        )
        self.conn.commit()

    def _row_to_factura_recibida_doc(self, row):
        item = self._row_to_dict(row)
        if not item:
            return None
        item["generada"] = bool(item.get("generada"))
        item["lineas"] = json.loads(item.get("lineas_json") or "[]")
        item["datos_extra"] = json.loads(item.get("datos_extra_json") or "{}")
        item.pop("lineas_json", None)
        item.pop("datos_extra_json", None)
        return item

    def _row_to_asiento_contable(self, row):
        item = self._row_to_dict(row)
        if not item:
            return None
        item["lineas"] = json.loads(item.get("lineas_json") or "[]")
        item.pop("lineas_json", None)
        return item

    # ---------- TERCEROS (global) ----------
    def get_tercero(self, tercero_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM terceros WHERE id=?", (str(tercero_id),)).fetchone()
        return self._row_to_dict(row) if row else None

    def get_tercero_by_nif(self, nif: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM terceros WHERE nif=? LIMIT 1", (str(nif).strip(),)).fetchone()
        return self._row_to_dict(row) if row else None

    def get_tercero_by_nif_normalizado(self, nif_normalizado: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM terceros WHERE nif_normalizado=? LIMIT 1",
            (str(nif_normalizado).strip().upper(),)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def listar_terceros(self):
        cur = self.conn.execute("SELECT * FROM terceros ORDER BY nombre")
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def upsert_tercero(self, tercero: dict):
        tid = tercero.get("id") or str(int(time.time() * 1000))
        tercero["id"] = tid
        nif = tercero.get("nif")
        nif_norm = tercero.get("nif_normalizado")
        if nif_norm is None:
            nif_norm = re.sub(r"[^A-Za-z0-9]", "", str(nif or "")).upper() or None
        pais = normalizar_codigo_pais(tercero.get("pais"))
        if not pais:
            pais = inferir_pais_desde_identificacion(nif)
        nombre = tercero.get("nombre")
        self.conn.execute(
            """
            INSERT INTO terceros (
                id, nif, nombre, direccion, cp, poblacion, provincia, telefono, email, contacto, tipo,
                nif_normalizado, nombre_legal, nombre_comercial, tipo_identificacion, pais,
                codigo_postal, observaciones, origen, activo, fecha_creacion, fecha_actualizacion
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?,?)
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
                tipo=excluded.tipo,
                nif_normalizado=excluded.nif_normalizado,
                nombre_legal=excluded.nombre_legal,
                nombre_comercial=excluded.nombre_comercial,
                tipo_identificacion=excluded.tipo_identificacion,
                pais=excluded.pais,
                codigo_postal=excluded.codigo_postal,
                observaciones=excluded.observaciones,
                origen=excluded.origen,
                activo=excluded.activo,
                fecha_actualizacion=excluded.fecha_actualizacion
            """,
            (
                tid,
                nif,
                nombre,
                tercero.get("direccion"),
                tercero.get("cp"),
                tercero.get("poblacion"),
                tercero.get("provincia"),
                tercero.get("telefono"),
                tercero.get("email"),
                tercero.get("contacto"),
                None,
                nif_norm,
                tercero.get("nombre_legal") or nombre,
                tercero.get("nombre_comercial"),
                tercero.get("tipo_identificacion"),
                pais or None,
                tercero.get("codigo_postal") or tercero.get("cp"),
                tercero.get("observaciones"),
                tercero.get("origen"),
                1 if tercero.get("activo", True) else 0,
                tercero.get("fecha_creacion") or self._utc_now(),
                tercero.get("fecha_actualizacion") or self._utc_now(),
            ),
        )
        self.conn.commit()
        return tid

    def eliminar_tercero(self, tercero_id: str):
        tid = str(tercero_id)
        cur = self.conn.execute(
            "SELECT COUNT(1) AS n FROM facturas_emitidas_docs WHERE tercero_id=?",
            (tid,),
        )
        if (cur.fetchone() or {}).get("n"):
            raise ValueError("No se puede eliminar el tercero: tiene facturas emitidas asociadas.")
        try:
            cur = self.conn.execute(
                "SELECT COUNT(1) AS n FROM albaranes_emitidas_docs WHERE tercero_id=?",
                (tid,),
            )
            if (cur.fetchone() or {}).get("n"):
                raise ValueError("No se puede eliminar el tercero: tiene albaranes asociados.")
        except sqlite3.OperationalError:
            pass
        self.conn.execute("DELETE FROM terceros WHERE id=?", (tercero_id,))
        self.conn.execute("DELETE FROM terceros_empresas WHERE tercero_id=?", (tercero_id,))
        self.conn.commit()

    # ---------- TERCEROS x EMPRESA ----------
    def listar_terceros_empresa(self, codigo_empresa: str, ejercicio: int):
        cur = self.conn.execute(
            "SELECT * FROM terceros_empresas WHERE codigo_empresa=? AND ejercicio=0",
            (codigo_empresa,),
        )
        rows = [self._row_to_dict(r) for r in cur.fetchall()]
        if rows:
            return rows
        cur = self.conn.execute(
            "SELECT * FROM terceros_empresas WHERE codigo_empresa=?",
            (codigo_empresa,),
        )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def listar_terceros_por_empresa(self, codigo_empresa: str, ejercicio: int):
        cur = self.conn.execute(
            """
            SELECT t.*, te.subcuenta_cliente, te.subcuenta_proveedor, te.subcuenta_ingreso, te.subcuenta_gasto,
                   te.cliente_tipo_operacion_iva, te.cliente_intracomunitaria_clase, te.cliente_iva_deducible, te.cliente_porcentaje_deduccion_iva,
                   te.proveedor_tipo_operacion_iva, te.proveedor_intracomunitaria_clase, te.proveedor_iva_deducible, te.proveedor_porcentaje_deduccion_iva,
                   te.facturae_es_administracion_publica, te.facturae_dir3_oficina_contable, te.facturae_dir3_organo_gestor,
                   te.facturae_dir3_unidad_tramitadora, te.facturae_dir3_organo_proponente, te.facturae_referencia_expediente,
                   te.facturae_referencia_contrato, te.facturae_referencia_pedido,
                   te.ejercicio
            FROM terceros t
            JOIN terceros_empresas te ON te.tercero_id = t.id
            WHERE te.codigo_empresa=? AND (te.ejercicio=0 OR te.ejercicio=?)
            ORDER BY t.nombre
            """,
            (codigo_empresa, _ej_val(ejercicio)),
        )
        rows = [self._row_to_dict(r) for r in cur.fetchall()]
        if not rows:
            cur = self.conn.execute(
                """
                SELECT t.*, te.subcuenta_cliente, te.subcuenta_proveedor, te.subcuenta_ingreso, te.subcuenta_gasto,
                       te.cliente_tipo_operacion_iva, te.cliente_intracomunitaria_clase, te.cliente_iva_deducible, te.cliente_porcentaje_deduccion_iva,
                       te.proveedor_tipo_operacion_iva, te.proveedor_intracomunitaria_clase, te.proveedor_iva_deducible, te.proveedor_porcentaje_deduccion_iva,
                       te.facturae_es_administracion_publica, te.facturae_dir3_oficina_contable, te.facturae_dir3_organo_gestor,
                       te.facturae_dir3_unidad_tramitadora, te.facturae_dir3_organo_proponente, te.facturae_referencia_expediente,
                       te.facturae_referencia_contrato, te.facturae_referencia_pedido,
                       te.ejercicio
                FROM terceros t
                JOIN terceros_empresas te ON te.tercero_id = t.id
                WHERE te.codigo_empresa=?
                ORDER BY t.nombre
                """,
                (codigo_empresa,),
            )
            rows = [self._row_to_dict(r) for r in cur.fetchall()]
        # Preferimos ejercicio 0 si existe
        by_id = {}
        for r in rows:
            tid = str(r.get("id"))
            cur_best = by_id.get(tid)
            if not cur_best:
                by_id[tid] = r
                continue
            ej = r.get("ejercicio")
            if ej == 0:
                by_id[tid] = r
        return list(by_id.values())

    def get_tercero_empresa(self, codigo_empresa: str, tercero_id: str, ejercicio: int):
        cur = self.conn.execute(
            "SELECT * FROM terceros_empresas WHERE codigo_empresa=? AND ejercicio=0 AND tercero_id=?",
            (codigo_empresa, tercero_id),
        )
        row = cur.fetchone()
        if row:
            return self._row_to_dict(row)
        cur = self.conn.execute(
            "SELECT * FROM terceros_empresas WHERE codigo_empresa=? AND tercero_id=? ORDER BY ejercicio DESC LIMIT 1",
            (codigo_empresa, tercero_id),
        )
        return self._row_to_dict(cur.fetchone())

    def upsert_tercero_empresa(self, rel: dict):
        eje = 0
        rel = validate_tercero_empresa_rel(rel)
        self.conn.execute(
            """
            INSERT INTO terceros_empresas (
                codigo_empresa, ejercicio, tercero_id,
                subcuenta_cliente, subcuenta_proveedor, subcuenta_ingreso, subcuenta_gasto,
                cliente_tipo_operacion_iva, cliente_intracomunitaria_clase, cliente_iva_deducible, cliente_porcentaje_deduccion_iva,
                proveedor_tipo_operacion_iva, proveedor_intracomunitaria_clase, proveedor_iva_deducible, proveedor_porcentaje_deduccion_iva,
                facturae_es_administracion_publica, facturae_dir3_oficina_contable, facturae_dir3_organo_gestor,
                facturae_dir3_unidad_tramitadora, facturae_dir3_organo_proponente, facturae_referencia_expediente,
                facturae_referencia_contrato, facturae_referencia_pedido
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(codigo_empresa, ejercicio, tercero_id) DO UPDATE SET
                subcuenta_cliente=excluded.subcuenta_cliente,
                subcuenta_proveedor=excluded.subcuenta_proveedor,
                subcuenta_ingreso=excluded.subcuenta_ingreso,
                subcuenta_gasto=excluded.subcuenta_gasto,
                cliente_tipo_operacion_iva=excluded.cliente_tipo_operacion_iva,
                cliente_intracomunitaria_clase=excluded.cliente_intracomunitaria_clase,
                cliente_iva_deducible=excluded.cliente_iva_deducible,
                cliente_porcentaje_deduccion_iva=excluded.cliente_porcentaje_deduccion_iva,
                proveedor_tipo_operacion_iva=excluded.proveedor_tipo_operacion_iva,
                proveedor_intracomunitaria_clase=excluded.proveedor_intracomunitaria_clase,
                proveedor_iva_deducible=excluded.proveedor_iva_deducible,
                proveedor_porcentaje_deduccion_iva=excluded.proveedor_porcentaje_deduccion_iva,
                facturae_es_administracion_publica=excluded.facturae_es_administracion_publica,
                facturae_dir3_oficina_contable=excluded.facturae_dir3_oficina_contable,
                facturae_dir3_organo_gestor=excluded.facturae_dir3_organo_gestor,
                facturae_dir3_unidad_tramitadora=excluded.facturae_dir3_unidad_tramitadora,
                facturae_dir3_organo_proponente=excluded.facturae_dir3_organo_proponente,
                facturae_referencia_expediente=excluded.facturae_referencia_expediente,
                facturae_referencia_contrato=excluded.facturae_referencia_contrato,
                facturae_referencia_pedido=excluded.facturae_referencia_pedido
            """,
            (
                rel.get("codigo_empresa"),
                eje,
                rel.get("tercero_id"),
                rel.get("subcuenta_cliente"),
                rel.get("subcuenta_proveedor"),
                rel.get("subcuenta_ingreso"),
                rel.get("subcuenta_gasto"),
                rel.get("cliente_tipo_operacion_iva"),
                rel.get("cliente_intracomunitaria_clase"),
                rel.get("cliente_iva_deducible"),
                rel.get("cliente_porcentaje_deduccion_iva"),
                rel.get("proveedor_tipo_operacion_iva"),
                rel.get("proveedor_intracomunitaria_clase"),
                rel.get("proveedor_iva_deducible"),
                rel.get("proveedor_porcentaje_deduccion_iva"),
                1 if rel.get("facturae_es_administracion_publica") else 0,
                rel.get("facturae_dir3_oficina_contable"),
                rel.get("facturae_dir3_organo_gestor"),
                rel.get("facturae_dir3_unidad_tramitadora"),
                rel.get("facturae_dir3_organo_proponente"),
                rel.get("facturae_referencia_expediente"),
                rel.get("facturae_referencia_contrato"),
                rel.get("facturae_referencia_pedido"),
            ),
        )
        self.conn.commit()

    def listar_empresas_de_tercero(self, tercero_id: str):
        cur = self.conn.execute(
            "SELECT DISTINCT codigo_empresa FROM terceros_empresas WHERE tercero_id=?",
            (str(tercero_id),),
        )
        codigos = [r["codigo_empresa"] for r in cur.fetchall()]
        if not codigos:
            return []
        q = ",".join("?" for _ in codigos)
        cur = self.conn.execute(
            f"SELECT codigo, nombre, ejercicio FROM empresas WHERE codigo IN ({q}) ORDER BY codigo, ejercicio DESC",
            tuple(codigos),
        )
        rows = [self._row_to_dict(r) for r in cur.fetchall()]
        by_codigo = {}
        for r in rows:
            codigo = r.get("codigo")
            if codigo not in by_codigo:
                by_codigo[codigo] = r
        return list(by_codigo.values())

    def eliminar_tercero_empresa(self, codigo_empresa: str, tercero_id: str):
        tid = str(tercero_id)
        cur = self.conn.execute(
            "SELECT COUNT(1) AS n FROM facturas_emitidas_docs WHERE codigo_empresa=? AND tercero_id=?",
            (codigo_empresa, tid),
        )
        row = cur.fetchone()
        if row and row["n"]:
            raise ValueError("No se puede eliminar: hay facturas emitidas de este tercero en la empresa.")
        try:
            cur = self.conn.execute(
                "SELECT COUNT(1) AS n FROM albaranes_emitidas_docs WHERE codigo_empresa=? AND tercero_id=?",
                (codigo_empresa, tid),
            )
            row = cur.fetchone()
            if row and row["n"]:
                raise ValueError("No se puede eliminar: hay albaranes de este tercero en la empresa.")
        except sqlite3.OperationalError:
            pass
        self.conn.execute(
            "DELETE FROM terceros_empresas WHERE codigo_empresa=? AND tercero_id=?",
            (codigo_empresa, tid),
        )
        self.conn.commit()

    def copiar_terceros_empresa(
        self,
        codigo_empresa: str,
        ejercicio_origen: int,
        ejercicio_destino: int,
        sobrescribir: bool = False,
    ):
        # Los terceros por empresa son globales para todos los ejercicios.
        return 0, 0
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

    # ---------- LEGACY DOCUMENTAL (retirado de la aplicacion activa) ----------
    def listar_plantillas_documentos(self, codigo_empresa: str, ejercicio: int):
        cur = self.conn.execute(
            "SELECT * FROM plantillas_documentos WHERE codigo_empresa=? AND ejercicio=? ORDER BY LOWER(nombre)",
            (codigo_empresa, _ej_val(ejercicio)),
        )
        out = []
        for row in cur.fetchall():
            item = self._row_to_dict(row)
            item["variables"] = json.loads(item.get("variables_json") or "[]")
            item.pop("variables_json", None)
            out.append(item)
        return out

    def get_plantilla_documento(self, plantilla_id: int):
        cur = self.conn.execute("SELECT * FROM plantillas_documentos WHERE id=?", (int(plantilla_id),))
        row = self._row_to_dict(cur.fetchone())
        if not row:
            return None
        row["variables"] = json.loads(row.get("variables_json") or "[]")
        row.pop("variables_json", None)
        return row

    def upsert_plantilla_documento(self, plantilla: dict):
        now = self._utc_now()
        plantilla_id = plantilla.get("id")
        if plantilla_id:
            self.conn.execute(
                """
                UPDATE plantillas_documentos
                SET nombre=?, tipo_documento=?, descripcion=?, ruta_template=?, variables_json=?, activa=?, updated_at=?
                WHERE id=?
                """,
                (
                    plantilla.get("nombre"),
                    plantilla.get("tipo_documento"),
                    plantilla.get("descripcion"),
                    plantilla.get("ruta_template"),
                    json.dumps(plantilla.get("variables", []), ensure_ascii=False),
                    1 if plantilla.get("activa", True) else 0,
                    now,
                    int(plantilla_id),
                ),
            )
            self.conn.commit()
            return int(plantilla_id)
        cur = self.conn.execute(
            """
            INSERT INTO plantillas_documentos
            (codigo_empresa, ejercicio, nombre, tipo_documento, descripcion, ruta_template, variables_json, activa, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plantilla.get("codigo_empresa"),
                _ej_val(plantilla.get("ejercicio")) or 0,
                plantilla.get("nombre"),
                plantilla.get("tipo_documento"),
                plantilla.get("descripcion"),
                plantilla.get("ruta_template"),
                json.dumps(plantilla.get("variables", []), ensure_ascii=False),
                1 if plantilla.get("activa", True) else 0,
                now,
                now,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def eliminar_plantilla_documento(self, plantilla_id: int):
        self.conn.execute("DELETE FROM plantillas_documentos WHERE id=?", (int(plantilla_id),))
        self.conn.commit()

    def buscar_plantilla_documento_por_nombre(self, codigo_empresa: str, ejercicio: int, nombre: str):
        cur = self.conn.execute(
            """
            SELECT * FROM plantillas_documentos
            WHERE codigo_empresa=? AND ejercicio=? AND LOWER(nombre)=LOWER(?)
            LIMIT 1
            """,
            (codigo_empresa, _ej_val(ejercicio), str(nombre or "").strip()),
        )
        row = self._row_to_dict(cur.fetchone())
        if not row:
            return None
        row["variables"] = json.loads(row.get("variables_json") or "[]")
        row.pop("variables_json", None)
        return row

    def listar_intervinientes(self, codigo_empresa: str, ejercicio: int, *, solo_habituales: bool = False):
        sql = "SELECT * FROM intervinientes WHERE codigo_empresa=? AND ejercicio=?"
        params = [codigo_empresa, _ej_val(ejercicio)]
        if solo_habituales:
            sql += " AND es_cliente_habitual=1"
        sql += " ORDER BY LOWER(nombre_razon_social)"
        cur = self.conn.execute(sql, tuple(params))
        return [self._row_to_dict(row) for row in cur.fetchall()]

    def get_interviniente(self, interviniente_id: int):
        cur = self.conn.execute("SELECT * FROM intervinientes WHERE id=?", (int(interviniente_id),))
        return self._row_to_dict(cur.fetchone())

    def upsert_interviniente(self, interviniente: dict):
        interviniente_id = interviniente.get("id")
        if interviniente_id:
            self.conn.execute(
                """
                UPDATE intervinientes
                SET tipo_persona=?, nombre_razon_social=?, nif=?, domicilio=?, municipio=?, provincia=?, cp=?,
                    telefono=?, email=?, representante=?, cargo=?, cliente_id=?, es_cliente_habitual=?, observaciones=?
                WHERE id=?
                """,
                (
                    interviniente.get("tipo_persona"),
                    interviniente.get("nombre_razon_social"),
                    interviniente.get("nif"),
                    interviniente.get("domicilio"),
                    interviniente.get("municipio"),
                    interviniente.get("provincia"),
                    interviniente.get("cp"),
                    interviniente.get("telefono"),
                    interviniente.get("email"),
                    interviniente.get("representante"),
                    interviniente.get("cargo"),
                    interviniente.get("cliente_id"),
                    1 if interviniente.get("es_cliente_habitual") else 0,
                    interviniente.get("observaciones"),
                    int(interviniente_id),
                ),
            )
            self.conn.commit()
            return int(interviniente_id)
        cur = self.conn.execute(
            """
            INSERT INTO intervinientes
            (codigo_empresa, ejercicio, tipo_persona, nombre_razon_social, nif, domicilio, municipio, provincia, cp,
             telefono, email, representante, cargo, cliente_id, es_cliente_habitual, observaciones)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                interviniente.get("codigo_empresa"),
                _ej_val(interviniente.get("ejercicio")) or 0,
                interviniente.get("tipo_persona"),
                interviniente.get("nombre_razon_social"),
                interviniente.get("nif"),
                interviniente.get("domicilio"),
                interviniente.get("municipio"),
                interviniente.get("provincia"),
                interviniente.get("cp"),
                interviniente.get("telefono"),
                interviniente.get("email"),
                interviniente.get("representante"),
                interviniente.get("cargo"),
                interviniente.get("cliente_id"),
                1 if interviniente.get("es_cliente_habitual") else 0,
                interviniente.get("observaciones"),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def eliminar_interviniente(self, interviniente_id: int):
        self.conn.execute("DELETE FROM intervinientes WHERE id=?", (int(interviniente_id),))
        self.conn.commit()

    def listar_operaciones(self, codigo_empresa: str, ejercicio: int):
        cur = self.conn.execute(
            "SELECT * FROM operaciones WHERE codigo_empresa=? AND ejercicio=? ORDER BY fecha_creacion DESC, id DESC",
            (codigo_empresa, _ej_val(ejercicio)),
        )
        return [self._row_to_dict(row) for row in cur.fetchall()]

    def upsert_operacion(self, operacion: dict):
        operacion_id = operacion.get("id")
        if operacion_id:
            self.conn.execute(
                """
                UPDATE operaciones
                SET titulo=?, tipo_operacion=?, cliente_id=?, fecha_creacion=?, descripcion=?, estado=?
                WHERE id=?
                """,
                (
                    operacion.get("titulo"),
                    operacion.get("tipo_operacion"),
                    operacion.get("cliente_id"),
                    operacion.get("fecha_creacion"),
                    operacion.get("descripcion"),
                    operacion.get("estado"),
                    int(operacion_id),
                ),
            )
            self.conn.commit()
            return int(operacion_id)
        cur = self.conn.execute(
            """
            INSERT INTO operaciones
            (codigo_empresa, ejercicio, titulo, tipo_operacion, cliente_id, fecha_creacion, descripcion, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operacion.get("codigo_empresa"),
                _ej_val(operacion.get("ejercicio")) or 0,
                operacion.get("titulo"),
                operacion.get("tipo_operacion"),
                operacion.get("cliente_id"),
                operacion.get("fecha_creacion"),
                operacion.get("descripcion"),
                operacion.get("estado"),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def set_operacion_intervinientes(self, operacion_id: int, items: list[dict]):
        self.conn.execute("DELETE FROM operacion_intervinientes WHERE operacion_id=?", (int(operacion_id),))
        for item in items or []:
            self.conn.execute(
                "INSERT INTO operacion_intervinientes (operacion_id, interviniente_id, rol) VALUES (?, ?, ?)",
                (int(operacion_id), int(item.get("interviniente_id")), item.get("rol")),
            )
        self.conn.commit()

    def listar_documentos_generados(self, codigo_empresa: str, ejercicio: int):
        cur = self.conn.execute(
            """
            SELECT d.*, p.nombre AS plantilla_nombre
            FROM documentos_generados d
            LEFT JOIN plantillas_documentos p ON p.id = d.plantilla_id
            WHERE d.codigo_empresa=? AND d.ejercicio=?
            ORDER BY d.fecha_generacion DESC, d.id DESC
            """,
            (codigo_empresa, _ej_val(ejercicio)),
        )
        out = []
        for row in cur.fetchall():
            item = self._row_to_dict(row)
            item["json_datos_generacion"] = json.loads(item.get("json_datos_generacion") or "{}")
            out.append(item)
        return out

    def get_documento_generado(self, documento_id: int):
        cur = self.conn.execute(
            """
            SELECT d.*, p.nombre AS plantilla_nombre
            FROM documentos_generados d
            LEFT JOIN plantillas_documentos p ON p.id = d.plantilla_id
            WHERE d.id=?
            """,
            (int(documento_id),),
        )
        row = self._row_to_dict(cur.fetchone())
        if not row:
            return None
        row["json_datos_generacion"] = json.loads(row.get("json_datos_generacion") or "{}")
        row["intervinientes"] = self.listar_documento_intervinientes(int(documento_id))
        return row

    def upsert_documento_generado(self, documento: dict):
        documento_id = documento.get("id")
        payload_json = json.dumps(documento.get("json_datos_generacion") or {}, ensure_ascii=False)
        if documento_id:
            self.conn.execute(
                """
                UPDATE documentos_generados
                SET plantilla_id=?, cliente_id=?, operacion_id=?, titulo_documento=?, fecha_generacion=?, ruta_docx=?,
                    ruta_pdf=?, estado=?, observaciones=?, json_datos_generacion=?
                WHERE id=?
                """,
                (
                    documento.get("plantilla_id"),
                    documento.get("cliente_id"),
                    documento.get("operacion_id"),
                    documento.get("titulo_documento"),
                    documento.get("fecha_generacion"),
                    documento.get("ruta_docx"),
                    documento.get("ruta_pdf"),
                    documento.get("estado"),
                    documento.get("observaciones"),
                    payload_json,
                    int(documento_id),
                ),
            )
            self.conn.commit()
            return int(documento_id)
        cur = self.conn.execute(
            """
            INSERT INTO documentos_generados
            (codigo_empresa, ejercicio, plantilla_id, cliente_id, operacion_id, titulo_documento, fecha_generacion,
             ruta_docx, ruta_pdf, estado, observaciones, json_datos_generacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                documento.get("codigo_empresa"),
                _ej_val(documento.get("ejercicio")) or 0,
                documento.get("plantilla_id"),
                documento.get("cliente_id"),
                documento.get("operacion_id"),
                documento.get("titulo_documento"),
                documento.get("fecha_generacion"),
                documento.get("ruta_docx"),
                documento.get("ruta_pdf"),
                documento.get("estado"),
                documento.get("observaciones"),
                payload_json,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def eliminar_documento_generado(self, documento_id: int):
        self.conn.execute("DELETE FROM documentos_generados WHERE id=?", (int(documento_id),))
        self.conn.commit()

    def set_documento_intervinientes(self, documento_id: int, items: list[dict]):
        self.conn.execute("DELETE FROM documento_intervinientes WHERE documento_id=?", (int(documento_id),))
        for item in items or []:
            self.conn.execute(
                "INSERT INTO documento_intervinientes (documento_id, interviniente_id, rol_en_documento) VALUES (?, ?, ?)",
                (int(documento_id), int(item.get("interviniente_id")), item.get("rol_en_documento")),
            )
        self.conn.commit()

    def listar_documento_intervinientes(self, documento_id: int):
        cur = self.conn.execute(
            """
            SELECT di.id, di.documento_id, di.interviniente_id, di.rol_en_documento,
                   i.nombre_razon_social, i.nif, i.email, i.telefono, i.tipo_persona
            FROM documento_intervinientes di
            JOIN intervinientes i ON i.id = di.interviniente_id
            WHERE di.documento_id=?
            ORDER BY di.id
            """,
            (int(documento_id),),
        )
        return [self._row_to_dict(row) for row in cur.fetchall()]

    # ---------- USUARIOS / ACL ----------
    def hay_usuarios(self) -> bool:
        cur = self.conn.execute("SELECT COUNT(*) AS n FROM usuarios")
        row = cur.fetchone()
        return bool(row and row["n"])

    def crear_usuario_inicial_admin(self, password_hash: str) -> dict:
        now = self._utc_now()
        cur = self.conn.execute(
            """
            INSERT INTO usuarios (username, password_hash, nombre, rol, activo, must_change_password, created_at, updated_at)
            VALUES (?, ?, ?, 'admin', 1, 1, ?, ?)
            """,
            ("admin", password_hash, "Administrador", now, now),
        )
        self.conn.commit()
        return self.get_usuario(cur.lastrowid)

    def listar_usuarios(self) -> list[dict]:
        cur = self.conn.execute(
            """
            SELECT u.*,
                   SUM(CASE WHEN ue.permiso IN ('lectura', 'escritura') THEN 1 ELSE 0 END) AS empresas_asignadas
            FROM usuarios u
            LEFT JOIN usuarios_empresas ue ON ue.usuario_id = u.id
            GROUP BY u.id
            ORDER BY LOWER(u.username)
            """
        )
        return [self._row_to_dict(row) for row in cur.fetchall()]

    def get_usuario(self, user_id: int) -> dict | None:
        cur = self.conn.execute("SELECT * FROM usuarios WHERE id=?", (int(user_id),))
        return self._row_to_dict(cur.fetchone())

    def get_usuario_by_username(self, username: str) -> dict | None:
        cur = self.conn.execute(
            "SELECT * FROM usuarios WHERE LOWER(username)=LOWER(?)",
            (str(username or "").strip(),),
        )
        return self._row_to_dict(cur.fetchone())

    def upsert_usuario(self, usuario: dict) -> int:
        now = self._utc_now()
        user_id = usuario.get("id")
        if user_id:
            existing = self.get_usuario(int(user_id))
            if not existing:
                raise ValueError("Usuario no encontrado.")
            password_hash = usuario.get("password_hash") or existing.get("password_hash")
            self.conn.execute(
                """
                UPDATE usuarios
                SET username=?,
                    password_hash=?,
                    nombre=?,
                    rol=?,
                    activo=?,
                    must_change_password=?,
                    updated_at=?
                WHERE id=?
                """,
                (
                    usuario.get("username"),
                    password_hash,
                    usuario.get("nombre"),
                    usuario.get("rol"),
                    1 if usuario.get("activo", True) else 0,
                    1 if usuario.get("must_change_password") else 0,
                    now,
                    int(user_id),
                ),
            )
            self.conn.commit()
            return int(user_id)

        password_hash = usuario.get("password_hash")
        if not password_hash:
            raise ValueError("La contraseña es obligatoria al crear un usuario.")
        cur = self.conn.execute(
            """
            INSERT INTO usuarios (username, password_hash, nombre, rol, activo, must_change_password, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario.get("username"),
                password_hash,
                usuario.get("nombre"),
                usuario.get("rol"),
                1 if usuario.get("activo", True) else 0,
                1 if usuario.get("must_change_password") else 0,
                now,
                now,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def actualizar_password_usuario(self, user_id: int, password_hash: str, *, must_change_password: bool = False) -> None:
        self.conn.execute(
            "UPDATE usuarios SET password_hash=?, must_change_password=?, updated_at=? WHERE id=?",
            (password_hash, 1 if must_change_password else 0, self._utc_now(), int(user_id)),
        )
        self.conn.commit()

    def listar_permisos_usuario(self, user_id: int) -> list[dict]:
        cur = self.conn.execute(
            """
            SELECT ue.*, e.nombre AS empresa_nombre
            FROM usuarios_empresas ue
            LEFT JOIN (
                SELECT codigo, MAX(nombre) AS nombre
                FROM empresas
                GROUP BY codigo
            ) e ON e.codigo = ue.empresa_codigo
            WHERE ue.usuario_id=?
            ORDER BY ue.empresa_codigo
            """,
            (int(user_id),),
        )
        return [self._row_to_dict(row) for row in cur.fetchall()]

    def reemplazar_permisos_usuario(self, user_id: int, permisos: dict[str, str]) -> None:
        now = self._utc_now()
        self.conn.execute("DELETE FROM usuarios_empresas WHERE usuario_id=?", (int(user_id),))
        for codigo, permiso in (permisos or {}).items():
            self.conn.execute(
                """
                INSERT INTO usuarios_empresas (usuario_id, empresa_codigo, permiso, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(user_id), str(codigo), str(permiso), now, now),
            )
        self.conn.commit()

    def upsert_permiso_usuario_empresa(self, user_id: int, codigo_empresa: str, permiso: str) -> None:
        now = self._utc_now()
        self.conn.execute(
            """
            INSERT INTO usuarios_empresas (usuario_id, empresa_codigo, permiso, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(usuario_id, empresa_codigo) DO UPDATE SET
                permiso=excluded.permiso,
                updated_at=excluded.updated_at
            """,
            (int(user_id), str(codigo_empresa), str(permiso), now, now),
        )
        self.conn.commit()

    # ── Fase 2: MAESTRO SUBCUENTAS EMPRESA ───────────────────────────────────────

    def upsert_maestro_subcuenta(self, datos: dict) -> int:
        """Inserta o actualiza una subcuenta en el maestro. Devuelve el id."""
        now = self._utc_now()
        sub_id = datos.get("id")
        if sub_id:
            self.conn.execute(
                """UPDATE maestro_subcuentas_empresa SET
                       tercero_id=?, nombre_subcuenta=?, tipo_subcuenta=?,
                       tipo_operacion_predeterminada=?,
                       cuenta_gasto_predeterminada_id=?,
                       cuenta_ingreso_predeterminada_id=?,
                       cuenta_iva_predeterminada_id=?,
                       cuenta_retencion_predeterminada_id=?,
                       nif_snapshot=?, activo=?, origen=?,
                       pendiente_alta_a3=?, lote_alta_a3=?,
                       fecha_alta_a3=?, observaciones=?, updated_at=?
                   WHERE id=?""",
                (
                    datos.get("tercero_id"), datos.get("nombre_subcuenta"),
                    datos.get("tipo_subcuenta"),
                    datos.get("tipo_operacion_predeterminada"),
                    datos.get("cuenta_gasto_predeterminada_id"),
                    datos.get("cuenta_ingreso_predeterminada_id"),
                    datos.get("cuenta_iva_predeterminada_id"),
                    datos.get("cuenta_retencion_predeterminada_id"),
                    datos.get("nif_snapshot"),
                    int(datos.get("activo", 1)),
                    datos.get("origen", "manual"),
                    int(datos.get("pendiente_alta_a3", 0)),
                    datos.get("lote_alta_a3"),
                    datos.get("fecha_alta_a3"),
                    datos.get("observaciones"),
                    now, int(sub_id),
                ),
            )
            self.conn.commit()
            return int(sub_id)
        self.conn.execute(
            """INSERT INTO maestro_subcuentas_empresa
               (codigo_empresa, tercero_id, subcuenta, nombre_subcuenta, tipo_subcuenta,
                tipo_operacion_predeterminada, cuenta_gasto_predeterminada_id,
                cuenta_ingreso_predeterminada_id, cuenta_iva_predeterminada_id,
                cuenta_retencion_predeterminada_id, nif_snapshot, activo, origen,
                fecha_importacion, creado_en_gest2a3eco, pendiente_alta_a3,
                observaciones, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(codigo_empresa, subcuenta) DO UPDATE SET
                   tercero_id=excluded.tercero_id,
                   nombre_subcuenta=excluded.nombre_subcuenta,
                   tipo_subcuenta=excluded.tipo_subcuenta,
                   tipo_operacion_predeterminada=excluded.tipo_operacion_predeterminada,
                   cuenta_gasto_predeterminada_id=excluded.cuenta_gasto_predeterminada_id,
                   cuenta_ingreso_predeterminada_id=excluded.cuenta_ingreso_predeterminada_id,
                   cuenta_iva_predeterminada_id=excluded.cuenta_iva_predeterminada_id,
                   cuenta_retencion_predeterminada_id=excluded.cuenta_retencion_predeterminada_id,
                   nif_snapshot=excluded.nif_snapshot,
                   activo=excluded.activo,
                   origen=excluded.origen,
                   pendiente_alta_a3=excluded.pendiente_alta_a3,
                   observaciones=excluded.observaciones,
                   updated_at=excluded.updated_at""",
            (
                datos.get("codigo_empresa"), datos.get("tercero_id"),
                datos.get("subcuenta"), datos.get("nombre_subcuenta"),
                datos.get("tipo_subcuenta"),
                datos.get("tipo_operacion_predeterminada"),
                datos.get("cuenta_gasto_predeterminada_id"),
                datos.get("cuenta_ingreso_predeterminada_id"),
                datos.get("cuenta_iva_predeterminada_id"),
                datos.get("cuenta_retencion_predeterminada_id"),
                datos.get("nif_snapshot"),
                int(datos.get("activo", 1)),
                datos.get("origen", "manual"),
                datos.get("fecha_importacion"),
                int(datos.get("creado_en_gest2a3eco", 0)),
                int(datos.get("pendiente_alta_a3", 0)),
                datos.get("observaciones"),
                now, now,
            ),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM maestro_subcuentas_empresa WHERE codigo_empresa=? AND subcuenta=?",
            (datos.get("codigo_empresa"), datos.get("subcuenta")),
        ).fetchone()
        return row[0] if row else None

    def get_maestro_subcuenta_por_subcuenta(self, codigo_empresa: str, subcuenta: str) -> dict | None:
        cur = self.conn.execute(
            "SELECT * FROM maestro_subcuentas_empresa WHERE codigo_empresa=? AND subcuenta=?",
            (str(codigo_empresa), str(subcuenta)),
        )
        return self._row_to_dict(cur.fetchone())

    def listar_maestro_subcuentas_empresa(
        self, codigo_empresa: str, tipo: str | None = None, activo: bool | None = True
    ) -> list:
        clauses = ["codigo_empresa=?"]
        params: list = [str(codigo_empresa)]
        if tipo:
            clauses.append("tipo_subcuenta=?")
            params.append(str(tipo))
        if activo is not None:
            clauses.append("activo=?")
            params.append(1 if activo else 0)
        where = " AND ".join(clauses)
        cur = self.conn.execute(
            f"SELECT * FROM maestro_subcuentas_empresa WHERE {where} ORDER BY subcuenta",
            params,
        )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def listar_maestro_subcuentas_por_tercero(self, codigo_empresa: str, tercero_id: str) -> list:
        cur = self.conn.execute(
            "SELECT * FROM maestro_subcuentas_empresa"
            " WHERE codigo_empresa=? AND tercero_id=? ORDER BY subcuenta",
            (str(codigo_empresa), str(tercero_id)),
        )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def listar_maestro_subcuentas_por_nif(self, codigo_empresa: str, nif: str) -> list:
        nif_norm = nif.upper().replace("-", "").replace(" ", "") if nif else ""
        cur = self.conn.execute(
            "SELECT * FROM maestro_subcuentas_empresa"
            " WHERE codigo_empresa=? AND nif_snapshot=? ORDER BY subcuenta",
            (str(codigo_empresa), nif_norm),
        )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def listar_subcuentas_facturacion(
        self,
        codigo_empresa: str,
        tipos: list[str] | tuple[str, ...],
        activo: bool | None = True,
        subcuenta: str | None = None,
    ) -> list[dict]:
        tipos_norm = [str(t).strip() for t in (tipos or []) if str(t).strip()]
        if not tipos_norm:
            return []
        placeholders = ",".join("?" for _ in tipos_norm)
        clauses = [
            "m.codigo_empresa=?",
            f"m.tipo_subcuenta IN ({placeholders})",
        ]
        params: list = [str(codigo_empresa), *tipos_norm]
        if activo is not None:
            clauses.append("m.activo=?")
            params.append(1 if activo else 0)
        if subcuenta is not None:
            clauses.append("m.subcuenta=?")
            params.append(str(subcuenta))
        where = " AND ".join(clauses)
        cur = self.conn.execute(
            f"""
            SELECT
                m.*,
                t.id AS tercero_global_id,
                t.nif AS tercero_nif,
                t.nombre AS tercero_nombre,
                t.nombre_legal AS tercero_nombre_legal,
                te.subcuenta_cliente,
                te.subcuenta_proveedor,
                te.subcuenta_ingreso,
                te.subcuenta_gasto,
                te.cliente_tipo_operacion_iva,
                te.cliente_intracomunitaria_clase,
                te.cliente_iva_deducible,
                te.cliente_porcentaje_deduccion_iva,
                te.proveedor_tipo_operacion_iva,
                te.proveedor_intracomunitaria_clase,
                te.proveedor_iva_deducible,
                te.proveedor_porcentaje_deduccion_iva
            FROM maestro_subcuentas_empresa m
            LEFT JOIN terceros t
                   ON t.id = m.tercero_id
            LEFT JOIN terceros_empresas te
                   ON te.codigo_empresa = m.codigo_empresa
                  AND te.tercero_id = m.tercero_id
                  AND te.ejercicio = 0
            WHERE {where}
            ORDER BY m.subcuenta
            """,
            params,
        )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def marcar_maestro_subcuenta_alta_a3(self, subcuenta_id: int, lote: str | None = None) -> None:
        now = self._utc_now()
        self.conn.execute(
            "UPDATE maestro_subcuentas_empresa"
            " SET pendiente_alta_a3=0, fecha_alta_a3=?, lote_alta_a3=?, updated_at=? WHERE id=?",
            (now, lote, now, int(subcuenta_id)),
        )
        self.conn.commit()

    def get_referencias_subcuenta_en_facturas(self, codigo_empresa: str, subcuenta: str) -> list[dict]:
        codigo = str(codigo_empresa or "").strip()
        cuenta = str(subcuenta or "").strip()
        if not codigo or not cuenta:
            return []

        refs: list[dict] = []
        emitidas = self.conn.execute(
            """
            SELECT id, ejercicio, serie, numero, nombre
            FROM facturas_emitidas_docs
            WHERE codigo_empresa=? AND subcuenta_cliente=?
            ORDER BY ejercicio, serie, numero, id
            """,
            (codigo, cuenta),
        ).fetchall()
        for row in emitidas:
            refs.append(
                {
                    "tipo": "factura_emitida",
                    "id": row["id"],
                    "ejercicio": row["ejercicio"],
                    "descripcion": f"Factura emitida {str(row['serie'] or '').strip()}{str(row['numero'] or '').strip()}".strip(),
                    "nombre": row["nombre"] or "",
                }
            )

        recibidas = self.conn.execute(
            """
            SELECT id, ejercicio, numero_factura, proveedor_nombre,
                   cuenta_gasto, cuenta_iva, cuenta_proveedor
            FROM facturas_recibidas_docs
            WHERE codigo_empresa=?
              AND (cuenta_gasto=? OR cuenta_iva=? OR cuenta_proveedor=?)
            ORDER BY ejercicio, numero_factura, id
            """,
            (codigo, cuenta, cuenta, cuenta),
        ).fetchall()
        for row in recibidas:
            campos = []
            if str(row["cuenta_gasto"] or "").strip() == cuenta:
                campos.append("gasto")
            if str(row["cuenta_iva"] or "").strip() == cuenta:
                campos.append("IVA")
            if str(row["cuenta_proveedor"] or "").strip() == cuenta:
                campos.append("proveedor")
            refs.append(
                {
                    "tipo": "factura_recibida",
                    "id": row["id"],
                    "ejercicio": row["ejercicio"],
                    "descripcion": f"Factura recibida {str(row['numero_factura'] or '').strip()}".strip(),
                    "nombre": row["proveedor_nombre"] or "",
                    "campos": campos,
                }
            )

        ocr_lineas = self.conn.execute(
            """
            SELECT o.doc_id, d.ejercicio, d.numero_factura, d.proveedor_nombre,
                   o.cuenta_base, o.cuenta_iva, o.cuenta_retencion
            FROM ocr_lineas_fiscales o
            JOIN facturas_recibidas_docs d ON d.id = o.doc_id
            WHERE d.codigo_empresa=?
              AND (o.cuenta_base=? OR o.cuenta_iva=? OR o.cuenta_retencion=?)
            ORDER BY d.ejercicio, d.numero_factura, o.doc_id
            """,
            (codigo, cuenta, cuenta, cuenta),
        ).fetchall()
        vistos = {(r["tipo"], str(r["id"])) for r in refs}
        for row in ocr_lineas:
            key = ("factura_recibida", str(row["doc_id"]))
            if key in vistos:
                continue
            campos = []
            if str(row["cuenta_base"] or "").strip() == cuenta:
                campos.append("base")
            if str(row["cuenta_iva"] or "").strip() == cuenta:
                campos.append("IVA")
            if str(row["cuenta_retencion"] or "").strip() == cuenta:
                campos.append("retencion")
            refs.append(
                {
                    "tipo": "factura_recibida",
                    "id": row["doc_id"],
                    "ejercicio": row["ejercicio"],
                    "descripcion": f"Factura recibida {str(row['numero_factura'] or '').strip()}".strip(),
                    "nombre": row["proveedor_nombre"] or "",
                    "campos": campos,
                }
            )
        return refs

    def eliminar_maestro_subcuenta(self, subcuenta_id: int) -> None:
        row = self.conn.execute(
            "SELECT codigo_empresa, subcuenta, tipo_subcuenta, tercero_id FROM maestro_subcuentas_empresa WHERE id=?",
            (int(subcuenta_id),),
        ).fetchone()
        if not row:
            return
        refs = self.get_referencias_subcuenta_en_facturas(row["codigo_empresa"], row["subcuenta"])
        if refs:
            detalle = []
            for ref in refs[:5]:
                label = ref.get("descripcion") or "Factura"
                nombre = str(ref.get("nombre") or "").strip()
                if nombre:
                    label = f"{label} ({nombre})"
                detalle.append(f"- {label}")
            raise ValueError(
                f"No se puede eliminar la subcuenta {row['subcuenta']} porque esta usada en facturas.\n\n"
                + "\n".join(detalle)
            )
        tercero_id = str(row["tercero_id"] or "").strip()
        if tercero_id:
            field_map = {
                "cliente": "subcuenta_cliente",
                "deudor": "subcuenta_cliente",
                "proveedor": "subcuenta_proveedor",
                "acreedor": "subcuenta_proveedor",
                "ingreso": "subcuenta_ingreso",
                "gasto": "subcuenta_gasto",
            }
            field_name = field_map.get(str(row["tipo_subcuenta"] or "").strip())
            if field_name:
                self.conn.execute(
                    f"""
                    UPDATE terceros_empresas
                    SET {field_name}=NULL
                    WHERE codigo_empresa=? AND tercero_id=? AND {field_name}=?
                    """,
                    (row["codigo_empresa"], tercero_id, row["subcuenta"]),
                )
        self.conn.execute(
            "DELETE FROM maestro_subcuentas_empresa WHERE id=?", (int(subcuenta_id),)
        )
        self.conn.commit()

    # ── Fase 2: RETENCIONES DE DOCUMENTO OCR ─────────────────────────────────────

    def upsert_captura_retencion(self, datos: dict) -> int:
        """Inserta o actualiza una retención de documento OCR. Devuelve el id."""
        ret_id = datos.get("id")
        if ret_id:
            self.conn.execute(
                """UPDATE captura_documental_retenciones SET
                       base_retencion=?, tipo_retencion=?, cuota_retencion=?,
                       cuota_retencion_manual=?, tipo_retencion_fiscal=?,
                       subcuenta_retencion_id=?, observaciones=?
                   WHERE id=?""",
                (
                    float(datos.get("base_retencion") or 0),
                    float(datos.get("tipo_retencion") or 0),
                    float(datos.get("cuota_retencion") or 0),
                    int(datos.get("cuota_retencion_manual") or 0),
                    datos.get("tipo_retencion_fiscal"),
                    datos.get("subcuenta_retencion_id"),
                    datos.get("observaciones"),
                    int(ret_id),
                ),
            )
            self.conn.commit()
            return int(ret_id)
        self.conn.execute(
            """INSERT INTO captura_documental_retenciones
               (documento_id, base_retencion, tipo_retencion, cuota_retencion,
                cuota_retencion_manual, tipo_retencion_fiscal,
                subcuenta_retencion_id, observaciones)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                str(datos.get("documento_id", "")),
                float(datos.get("base_retencion") or 0),
                float(datos.get("tipo_retencion") or 0),
                float(datos.get("cuota_retencion") or 0),
                int(datos.get("cuota_retencion_manual") or 0),
                datos.get("tipo_retencion_fiscal"),
                datos.get("subcuenta_retencion_id"),
                datos.get("observaciones"),
            ),
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def listar_captura_retenciones_doc(self, documento_id: str) -> list:
        cur = self.conn.execute(
            "SELECT * FROM captura_documental_retenciones WHERE documento_id=?",
            (str(documento_id),),
        )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def reemplazar_captura_retenciones_doc(self, documento_id: str, retenciones: list) -> None:
        self.conn.execute(
            "DELETE FROM captura_documental_retenciones WHERE documento_id=?",
            (str(documento_id),),
        )
        for r in retenciones:
            self.conn.execute(
                """INSERT INTO captura_documental_retenciones
                   (documento_id, base_retencion, tipo_retencion, cuota_retencion,
                    cuota_retencion_manual, tipo_retencion_fiscal,
                    subcuenta_retencion_id, observaciones)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    str(documento_id),
                    float(r.get("base_retencion") or 0),
                    float(r.get("tipo_retencion") or 0),
                    float(r.get("cuota_retencion") or 0),
                    int(r.get("cuota_retencion_manual") or 0),
                    r.get("tipo_retencion_fiscal"),
                    r.get("subcuenta_retencion_id"),
                    r.get("observaciones"),
                ),
            )
        self.conn.commit()

    # ── CRUD: tablas del nuevo modulo OCR tipado (Fase 3) ────────────────────

    # documentos_ocr ──────────────────────────────────────────────────────────

    def upsert_documento_ocr(self, doc: dict) -> str:
        """Inserta o actualiza un documento OCR. Devuelve el id."""
        self.conn.execute(
            """
            INSERT INTO documentos_ocr
              (id, empresa_id, ruta_original, nombre_archivo, hash_archivo,
               tipo_documento, estado, fecha_alta, fecha_procesado,
               motor_ocr, confianza_global, error_ocr, texto_extraido, json_ocr)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              estado=excluded.estado,
              fecha_procesado=excluded.fecha_procesado,
              motor_ocr=excluded.motor_ocr,
              confianza_global=excluded.confianza_global,
              error_ocr=excluded.error_ocr,
              texto_extraido=excluded.texto_extraido,
              json_ocr=excluded.json_ocr
            """,
            (
                doc["id"], doc.get("empresa_id"), doc.get("ruta_original"),
                doc.get("nombre_archivo"), doc.get("hash_archivo"),
                doc.get("tipo_documento", "factura_recibida"),
                doc.get("estado", "pendiente_revision"),
                doc.get("fecha_alta"), doc.get("fecha_procesado"),
                doc.get("motor_ocr", ""), float(doc.get("confianza_global") or 0.0),
                doc.get("error_ocr", ""), doc.get("texto_extraido", ""),
                doc.get("json_ocr", ""),
            ),
        )
        self.conn.commit()
        return doc["id"]

    def get_documento_ocr(self, doc_id: str) -> dict | None:
        cur = self.conn.execute(
            "SELECT * FROM documentos_ocr WHERE id=?", (str(doc_id),)
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))

    def buscar_documento_ocr_por_hash(self, empresa_id: str, hash_archivo: str) -> dict | None:
        cur = self.conn.execute(
            "SELECT * FROM documentos_ocr WHERE empresa_id=? AND hash_archivo=?",
            (empresa_id, hash_archivo),
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))

    def listar_documentos_ocr(self, empresa_id: str, estado: str | None = None) -> list[dict]:
        if estado:
            cur = self.conn.execute(
                "SELECT * FROM documentos_ocr WHERE empresa_id=? AND estado=? ORDER BY fecha_alta DESC",
                (empresa_id, estado),
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM documentos_ocr WHERE empresa_id=? ORDER BY fecha_alta DESC",
                (empresa_id,),
            )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    # facturas_recibidas_ocr ──────────────────────────────────────────────────

    def upsert_factura_recibida_ocr(self, factura: dict) -> str:
        """Inserta o actualiza una factura recibida OCR. Devuelve el id."""
        self.conn.execute(
            """
            INSERT INTO facturas_recibidas_ocr
              (id, documento_id, empresa_id, proveedor_id, nif_proveedor,
               nombre_proveedor, numero_factura, fecha_factura, fecha_operacion,
               fecha_vencimiento, total_factura, base_total, iva_total,
               retencion_total, estado_validacion, observaciones)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              proveedor_id=excluded.proveedor_id,
              nif_proveedor=excluded.nif_proveedor,
              nombre_proveedor=excluded.nombre_proveedor,
              numero_factura=excluded.numero_factura,
              fecha_factura=excluded.fecha_factura,
              fecha_operacion=excluded.fecha_operacion,
              fecha_vencimiento=excluded.fecha_vencimiento,
              total_factura=excluded.total_factura,
              base_total=excluded.base_total,
              iva_total=excluded.iva_total,
              retencion_total=excluded.retencion_total,
              estado_validacion=excluded.estado_validacion,
              observaciones=excluded.observaciones
            """,
            (
                factura["id"], factura.get("documento_id"), factura.get("empresa_id"),
                factura.get("proveedor_id"), factura.get("nif_proveedor"),
                factura.get("nombre_proveedor"), factura.get("numero_factura"),
                factura.get("fecha_factura"), factura.get("fecha_operacion"),
                factura.get("fecha_vencimiento"),
                float(factura.get("total_factura") or 0.0),
                float(factura.get("base_total") or 0.0),
                float(factura.get("iva_total") or 0.0),
                float(factura.get("retencion_total") or 0.0),
                factura.get("estado_validacion", "pendiente"),
                factura.get("observaciones", ""),
            ),
        )
        self.conn.commit()
        return factura["id"]

    def get_factura_recibida_ocr(self, factura_id: str) -> dict | None:
        cur = self.conn.execute(
            "SELECT * FROM facturas_recibidas_ocr WHERE id=?", (str(factura_id),)
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))

    def listar_facturas_recibidas_ocr(
        self, empresa_id: str, estado: str | None = None
    ) -> list[dict]:
        if estado:
            cur = self.conn.execute(
                "SELECT * FROM facturas_recibidas_ocr WHERE empresa_id=? AND estado_validacion=? "
                "ORDER BY fecha_factura DESC",
                (empresa_id, estado),
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM facturas_recibidas_ocr WHERE empresa_id=? ORDER BY fecha_factura DESC",
                (empresa_id,),
            )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    # facturas_recibidas_ocr_lineas_iva ───────────────────────────────────────

    def upsert_linea_iva_ocr(self, linea: dict) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO facturas_recibidas_ocr_lineas_iva
              (factura_id, tipo_iva, base, cuota_iva, tipo_recargo, cuota_recargo,
               deducible, porcentaje_deduccion, cuenta_gasto, tipo_operacion_iva)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(linea["factura_id"]),
                float(linea.get("tipo_iva") or 0.0),
                float(linea.get("base") or 0.0),
                float(linea.get("cuota_iva") or 0.0),
                float(linea.get("tipo_recargo") or 0.0),
                float(linea.get("cuota_recargo") or 0.0),
                int(linea.get("deducible", 1)),
                float(linea.get("porcentaje_deduccion", 100.0)),
                linea.get("cuenta_gasto", ""),
                linea.get("tipo_operacion_iva", "INTERIOR_DEDUCIBLE"),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def listar_lineas_iva_ocr(self, factura_id: str) -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM facturas_recibidas_ocr_lineas_iva WHERE factura_id=?",
            (str(factura_id),),
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def eliminar_lineas_iva_ocr(self, factura_id: str):
        self.conn.execute(
            "DELETE FROM facturas_recibidas_ocr_lineas_iva WHERE factura_id=?",
            (str(factura_id),),
        )
        self.conn.commit()

    # facturas_recibidas_ocr_retenciones ──────────────────────────────────────

    def upsert_retencion_ocr(self, ret: dict) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO facturas_recibidas_ocr_retenciones
              (factura_id, base_retencion, tipo_retencion, importe_retencion, clase_retencion)
            VALUES (?,?,?,?,?)
            """,
            (
                str(ret["factura_id"]),
                float(ret.get("base_retencion") or 0.0),
                float(ret.get("tipo_retencion") or 0.0),
                float(ret.get("importe_retencion") or 0.0),
                ret.get("clase_retencion", "PROFESIONAL"),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def listar_retenciones_ocr(self, factura_id: str) -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM facturas_recibidas_ocr_retenciones WHERE factura_id=?",
            (str(factura_id),),
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    # ocr_correcciones ────────────────────────────────────────────────────────

    def upsert_correccion_ocr(self, corr: dict) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO ocr_correcciones
              (factura_id, campo, valor_ocr, valor_corregido, fecha_correccion, usuario)
            VALUES (?,?,?,?,?,?)
            """,
            (
                str(corr["factura_id"]),
                corr.get("campo", ""),
                corr.get("valor_ocr", ""),
                corr.get("valor_corregido", ""),
                corr.get("fecha_correccion", ""),
                corr.get("usuario", ""),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def listar_correcciones_ocr(self, factura_id: str) -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM ocr_correcciones WHERE factura_id=? ORDER BY fecha_correccion",
            (str(factura_id),),
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
        self.conn.commit()

    # ── Notificaciones Electronicas ──────────────────────────────────────────

    def _migrate_notificaciones(self):
        """Crea las tablas del modulo Notificaciones Electronicas (idempotente)."""
        self.conn.executescript("""
            -- v1: registro de envios salientes
            CREATE TABLE IF NOT EXISTS notificaciones (
                id              TEXT PRIMARY KEY,
                codigo_empresa  TEXT NOT NULL,
                ejercicio       INTEGER NOT NULL,
                tipo_documento  TEXT NOT NULL DEFAULT 'MANUAL',
                documento_id    TEXT,
                tipo_notif      TEXT NOT NULL,
                canal           TEXT NOT NULL,
                destinatario    TEXT NOT NULL,
                asunto          TEXT,
                estado          TEXT NOT NULL DEFAULT 'PENDIENTE',
                fecha_envio     TEXT,
                fecha_intento   TEXT,
                intentos        INTEGER NOT NULL DEFAULT 0,
                error_detalle   TEXT,
                payload_json    TEXT,
                respuesta_json  TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_notificaciones_empresa
                ON notificaciones(codigo_empresa, ejercicio, estado);
            CREATE TABLE IF NOT EXISTS notificaciones_config (
                codigo_empresa  TEXT NOT NULL,
                ejercicio       INTEGER NOT NULL,
                canal           TEXT NOT NULL,
                activo          INTEGER NOT NULL DEFAULT 0,
                config_json     TEXT,
                PRIMARY KEY (codigo_empresa, ejercicio, canal)
            );
            -- v2: gestion de certificados, organismos, buzones y bandeja
            CREATE TABLE IF NOT EXISTS notif_certificados (
                id              TEXT PRIMARY KEY,
                codigo_empresa  TEXT NOT NULL,
                nombre          TEXT NOT NULL,
                nif_titular     TEXT NOT NULL,
                tipo            TEXT NOT NULL DEFAULT 'PFX',
                ruta_archivo    TEXT,
                fecha_emision   TEXT,
                fecha_caducidad TEXT,
                notas           TEXT,
                activo          INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_notif_cert_empresa
                ON notif_certificados(codigo_empresa, activo);
            CREATE TABLE IF NOT EXISTS notif_organismos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo      TEXT NOT NULL UNIQUE,
                nombre      TEXT NOT NULL,
                tipo        TEXT NOT NULL DEFAULT 'AAPP',
                url_portal  TEXT,
                descripcion TEXT,
                activo      INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_notif_org_activo
                ON notif_organismos(activo);
            CREATE TABLE IF NOT EXISTS notif_buzones (
                id              TEXT PRIMARY KEY,
                codigo_empresa  TEXT NOT NULL,
                nombre          TEXT NOT NULL,
                organismo_id    INTEGER,
                tipo_buzon      TEXT NOT NULL DEFAULT 'DEH',
                nif_titular     TEXT,
                certificado_id  TEXT,
                activo          INTEGER NOT NULL DEFAULT 1,
                ultima_consulta TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                FOREIGN KEY (organismo_id)   REFERENCES notif_organismos(id),
                FOREIGN KEY (certificado_id) REFERENCES notif_certificados(id)
            );
            CREATE INDEX IF NOT EXISTS idx_notif_buzones_empresa
                ON notif_buzones(codigo_empresa, activo);
            CREATE INDEX IF NOT EXISTS idx_notif_buzones_organismo
                ON notif_buzones(organismo_id);
            CREATE TABLE IF NOT EXISTS notif_bandeja (
                id                       TEXT PRIMARY KEY,
                codigo_empresa           TEXT NOT NULL,
                ejercicio                INTEGER NOT NULL,
                buzon_id                 TEXT,
                organismo_id             INTEGER,
                asunto                   TEXT NOT NULL,
                descripcion              TEXT,
                tipo_acto                TEXT,
                referencia               TEXT,
                nif_interesado           TEXT,
                nombre_interesado        TEXT,
                fecha_puesta_disposicion TEXT,
                fecha_vencimiento        TEXT,
                fecha_aceptacion         TEXT,
                fecha_rechazo            TEXT,
                estado                   TEXT NOT NULL DEFAULT 'PENDIENTE',
                pdf_path                 TEXT,
                metadatos_json           TEXT,
                created_at               TEXT NOT NULL,
                updated_at               TEXT NOT NULL,
                FOREIGN KEY (buzon_id)      REFERENCES notif_buzones(id),
                FOREIGN KEY (organismo_id)  REFERENCES notif_organismos(id)
            );
            CREATE INDEX IF NOT EXISTS idx_notif_bandeja_empresa
                ON notif_bandeja(codigo_empresa, ejercicio, estado, fecha_puesta_disposicion);
            -- v2.1: historico de sincronizaciones
            CREATE TABLE IF NOT EXISTS notif_sync_logs (
                id              TEXT PRIMARY KEY,
                codigo_empresa  TEXT,
                organismo_id    INTEGER,
                buzon_id        TEXT,
                fecha_hora      TEXT NOT NULL,
                resultado       TEXT NOT NULL DEFAULT 'OK',
                error_detalle   TEXT,
                notificaciones_detectadas INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL,
                FOREIGN KEY (organismo_id) REFERENCES notif_organismos(id),
                FOREIGN KEY (buzon_id)     REFERENCES notif_buzones(id)
            );
            CREATE INDEX IF NOT EXISTS idx_notif_sync_logs_fecha
                ON notif_sync_logs(fecha_hora);
        """)
        # v2.1: columnas adicionales para certificados, buzones y bandeja
        self._ensure_column("notif_certificados", "password_cifrada", "TEXT")
        self._ensure_column("notif_buzones", "periodicidad_sync", "TEXT NOT NULL DEFAULT 'MANUAL'")
        self._ensure_column("notif_buzones", "modo_descarga", "TEXT NOT NULL DEFAULT 'SOLO_DETECTAR'")
        self._ensure_column("notif_buzones", "envio_automatico_cliente", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("notif_buzones", "email_aviso", "TEXT")
        self._ensure_column("notif_buzones", "responsable_interno", "TEXT")
        self._ensure_column("notif_bandeja", "responsable", "TEXT")
        self._ensure_column("notif_bandeja", "archivada", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("notif_bandeja", "enviada_cliente", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("notif_bandeja", "fecha_envio_cliente", "TEXT")
        self.conn.commit()

    def listar_notificaciones(
        self,
        codigo_empresa: str,
        ejercicio: int,
        estado: str | None = None,
        canal: str | None = None,
    ) -> list[dict]:
        sql = "SELECT * FROM notificaciones WHERE codigo_empresa=? AND ejercicio=?"
        params: list = [codigo_empresa, int(ejercicio)]
        if estado:
            sql += " AND estado=?"
            params.append(estado)
        if canal:
            sql += " AND canal=?"
            params.append(canal)
        sql += " ORDER BY created_at DESC"
        cur = self.conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def get_notificacion(self, notificacion_id: str) -> dict | None:
        cur = self.conn.execute(
            "SELECT * FROM notificaciones WHERE id=?", (notificacion_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))

    def upsert_notificacion(self, notif: dict) -> str:
        """Inserta o actualiza una notificacion. Devuelve el id."""
        now      = self._utc_now()
        notif_id = str(notif.get("id") or "")
        if not notif_id:
            raise ValueError("upsert_notificacion: el campo 'id' es obligatorio.")
        self.conn.execute(
            """
            INSERT INTO notificaciones
                (id, codigo_empresa, ejercicio, tipo_documento, documento_id,
                 tipo_notif, canal, destinatario, asunto, estado,
                 fecha_envio, fecha_intento, intentos, error_detalle,
                 payload_json, respuesta_json, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                estado         = excluded.estado,
                fecha_envio    = excluded.fecha_envio,
                fecha_intento  = excluded.fecha_intento,
                intentos       = excluded.intentos,
                error_detalle  = excluded.error_detalle,
                respuesta_json = excluded.respuesta_json,
                updated_at     = excluded.updated_at
            """,
            (
                notif_id,
                notif.get("codigo_empresa"),
                int(notif.get("ejercicio") or 0),
                notif.get("tipo_documento", "MANUAL"),
                notif.get("documento_id"),
                notif.get("tipo_notif", ""),
                notif.get("canal", ""),
                notif.get("destinatario", ""),
                notif.get("asunto"),
                notif.get("estado", "PENDIENTE"),
                notif.get("fecha_envio"),
                notif.get("fecha_intento"),
                int(notif.get("intentos") or 0),
                notif.get("error_detalle"),
                notif.get("payload_json"),
                notif.get("respuesta_json"),
                notif.get("created_at", now),
                now,
            ),
        )
        self.conn.commit()
        return notif_id

    def eliminar_notificacion(self, codigo_empresa: str, notificacion_id: str) -> None:
        self.conn.execute(
            "DELETE FROM notificaciones WHERE id=? AND codigo_empresa=?",
            (notificacion_id, codigo_empresa),
        )
        self.conn.commit()

    def get_notificaciones_config(self, codigo_empresa: str, ejercicio: int) -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM notificaciones_config WHERE codigo_empresa=? AND ejercicio=?",
            (codigo_empresa, int(ejercicio)),
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def upsert_notificaciones_config(self, config: dict) -> None:
        self.conn.execute(
            """
            INSERT INTO notificaciones_config
                (codigo_empresa, ejercicio, canal, activo, config_json)
            VALUES (?,?,?,?,?)
            ON CONFLICT(codigo_empresa, ejercicio, canal) DO UPDATE SET
                activo      = excluded.activo,
                config_json = excluded.config_json
            """,
            (
                config.get("codigo_empresa"),
                int(config.get("ejercicio") or 0),
                config.get("canal", ""),
                int(config.get("activo") or 0),
                config.get("config_json"),
            ),
        )
        self.conn.commit()

    # ── notif_certificados ───────────────────────────────────────────────────

    def listar_notif_certificados(self, codigo_empresa: str, solo_activos: bool = False) -> list[dict]:
        sql = "SELECT * FROM notif_certificados WHERE codigo_empresa=?"
        params: list = [codigo_empresa]
        if solo_activos:
            sql += " AND activo=1"
        sql += " ORDER BY nombre"
        cur = self.conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def get_notif_certificado(self, cert_id: str) -> dict | None:
        cur = self.conn.execute("SELECT * FROM notif_certificados WHERE id=?", (cert_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))

    def upsert_notif_certificado(self, cert: dict) -> str:
        import uuid as _uuid
        now     = self._utc_now()
        cert_id = str(cert.get("id") or _uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO notif_certificados
                (id, codigo_empresa, nombre, nif_titular, tipo,
                 ruta_archivo, fecha_emision, fecha_caducidad, notas, activo,
                 password_cifrada, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                nombre            = excluded.nombre,
                nif_titular       = excluded.nif_titular,
                tipo              = excluded.tipo,
                ruta_archivo      = excluded.ruta_archivo,
                fecha_emision     = excluded.fecha_emision,
                fecha_caducidad   = excluded.fecha_caducidad,
                notas             = excluded.notas,
                activo            = excluded.activo,
                password_cifrada  = excluded.password_cifrada,
                updated_at        = excluded.updated_at
            """,
            (
                cert_id,
                cert.get("codigo_empresa"),
                cert.get("nombre", ""),
                cert.get("nif_titular", ""),
                cert.get("tipo", "PFX"),
                cert.get("ruta_archivo"),
                cert.get("fecha_emision"),
                cert.get("fecha_caducidad"),
                cert.get("notas"),
                int(cert.get("activo", 1)),
                cert.get("password_cifrada"),
                cert.get("created_at", now),
                now,
            ),
        )
        self.conn.commit()
        return cert_id

    def eliminar_notif_certificado(self, codigo_empresa: str, cert_id: str) -> None:
        self.conn.execute(
            "DELETE FROM notif_certificados WHERE id=? AND codigo_empresa=?",
            (cert_id, codigo_empresa),
        )
        self.conn.commit()

    # ── notif_organismos ─────────────────────────────────────────────────────

    def listar_notif_organismos(self, solo_activos: bool = False) -> list[dict]:
        sql = "SELECT * FROM notif_organismos"
        if solo_activos:
            sql += " WHERE activo=1"
        sql += " ORDER BY nombre"
        cur = self.conn.execute(sql)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def get_notif_organismo(self, org_id: int) -> dict | None:
        cur = self.conn.execute("SELECT * FROM notif_organismos WHERE id=?", (org_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))

    def upsert_notif_organismo(self, org: dict) -> int:
        now = self._utc_now()
        org_id = org.get("id")
        if org_id:
            self.conn.execute(
                """
                INSERT INTO notif_organismos
                    (id, codigo, nombre, tipo, url_portal, descripcion, activo, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    codigo      = excluded.codigo,
                    nombre      = excluded.nombre,
                    tipo        = excluded.tipo,
                    url_portal  = excluded.url_portal,
                    descripcion = excluded.descripcion,
                    activo      = excluded.activo,
                    updated_at  = excluded.updated_at
                """,
                (
                    int(org_id),
                    org.get("codigo", "").upper().strip(),
                    org.get("nombre", ""),
                    org.get("tipo", "AAPP"),
                    org.get("url_portal"),
                    org.get("descripcion"),
                    int(org.get("activo", 1)),
                    org.get("created_at", now),
                    now,
                ),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO notif_organismos
                    (codigo, nombre, tipo, url_portal, descripcion, activo, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(codigo) DO UPDATE SET
                    nombre      = excluded.nombre,
                    tipo        = excluded.tipo,
                    url_portal  = excluded.url_portal,
                    descripcion = excluded.descripcion,
                    activo      = excluded.activo,
                    updated_at  = excluded.updated_at
                """,
                (
                    org.get("codigo", "").upper().strip(),
                    org.get("nombre", ""),
                    org.get("tipo", "AAPP"),
                    org.get("url_portal"),
                    org.get("descripcion"),
                    int(org.get("activo", 1)),
                    now,
                    now,
                ),
            )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM notif_organismos WHERE codigo=?",
            (org.get("codigo", "").upper().strip(),),
        ).fetchone()
        return row[0] if row else 0

    def eliminar_notif_organismo(self, org_id: int) -> None:
        self.conn.execute("DELETE FROM notif_organismos WHERE id=?", (org_id,))
        self.conn.commit()

    # ── notif_buzones ────────────────────────────────────────────────────────

    def listar_notif_buzones(self, codigo_empresa: str, solo_activos: bool = False) -> list[dict]:
        sql = """
            SELECT b.*, o.nombre AS organismo_nombre, o.codigo AS organismo_codigo,
                   c.nombre AS certificado_nombre
            FROM notif_buzones b
            LEFT JOIN notif_organismos o ON b.organismo_id = o.id
            LEFT JOIN notif_certificados c ON b.certificado_id = c.id
            WHERE b.codigo_empresa=?
        """
        params: list = [codigo_empresa]
        if solo_activos:
            sql += " AND b.activo=1"
        sql += " ORDER BY b.nombre"
        cur = self.conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def get_notif_buzon(self, buzon_id: str) -> dict | None:
        cur = self.conn.execute(
            """
            SELECT b.*, o.nombre AS organismo_nombre, o.codigo AS organismo_codigo,
                   c.nombre AS certificado_nombre
            FROM notif_buzones b
            LEFT JOIN notif_organismos o ON b.organismo_id = o.id
            LEFT JOIN notif_certificados c ON b.certificado_id = c.id
            WHERE b.id=?
            """,
            (buzon_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))

    def upsert_notif_buzon(self, buzon: dict) -> str:
        import uuid as _uuid
        now      = self._utc_now()
        buzon_id = str(buzon.get("id") or _uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO notif_buzones
                (id, codigo_empresa, nombre, organismo_id, tipo_buzon,
                 nif_titular, certificado_id, activo, ultima_consulta,
                 periodicidad_sync, modo_descarga, envio_automatico_cliente,
                 email_aviso, responsable_interno, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                nombre                   = excluded.nombre,
                organismo_id             = excluded.organismo_id,
                tipo_buzon               = excluded.tipo_buzon,
                nif_titular              = excluded.nif_titular,
                certificado_id           = excluded.certificado_id,
                activo                   = excluded.activo,
                ultima_consulta          = excluded.ultima_consulta,
                periodicidad_sync        = excluded.periodicidad_sync,
                modo_descarga            = excluded.modo_descarga,
                envio_automatico_cliente = excluded.envio_automatico_cliente,
                email_aviso              = excluded.email_aviso,
                responsable_interno      = excluded.responsable_interno,
                updated_at               = excluded.updated_at
            """,
            (
                buzon_id,
                buzon.get("codigo_empresa"),
                buzon.get("nombre", ""),
                buzon.get("organismo_id"),
                buzon.get("tipo_buzon", "DEH"),
                buzon.get("nif_titular"),
                buzon.get("certificado_id"),
                int(buzon.get("activo", 1)),
                buzon.get("ultima_consulta"),
                buzon.get("periodicidad_sync", "MANUAL"),
                buzon.get("modo_descarga", "SOLO_DETECTAR"),
                int(buzon.get("envio_automatico_cliente", 0)),
                buzon.get("email_aviso"),
                buzon.get("responsable_interno"),
                buzon.get("created_at", now),
                now,
            ),
        )
        self.conn.commit()
        return buzon_id

    def eliminar_notif_buzon(self, codigo_empresa: str, buzon_id: str) -> None:
        self.conn.execute(
            "DELETE FROM notif_buzones WHERE id=? AND codigo_empresa=?",
            (buzon_id, codigo_empresa),
        )
        self.conn.commit()

    # ── notif_bandeja ────────────────────────────────────────────────────────

    def listar_notif_bandeja(
        self,
        codigo_empresa: str,
        ejercicio: int,
        estado: str | None = None,
        organismo_id: int | None = None,
    ) -> list[dict]:
        sql = """
            SELECT nb.*, o.nombre AS organismo_nombre, o.codigo AS organismo_codigo,
                   bz.nombre AS buzon_nombre
            FROM notif_bandeja nb
            LEFT JOIN notif_organismos o  ON nb.organismo_id = o.id
            LEFT JOIN notif_buzones    bz ON nb.buzon_id     = bz.id
            WHERE nb.codigo_empresa=? AND nb.ejercicio=?
        """
        params: list = [codigo_empresa, int(ejercicio)]
        if estado:
            sql += " AND nb.estado=?"
            params.append(estado)
        if organismo_id:
            sql += " AND nb.organismo_id=?"
            params.append(int(organismo_id))
        sql += " ORDER BY nb.fecha_puesta_disposicion DESC, nb.created_at DESC"
        cur = self.conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def get_notif_bandeja_item(self, item_id: str) -> dict | None:
        cur = self.conn.execute(
            """
            SELECT nb.*, o.nombre AS organismo_nombre, o.codigo AS organismo_codigo,
                   bz.nombre AS buzon_nombre
            FROM notif_bandeja nb
            LEFT JOIN notif_organismos o  ON nb.organismo_id = o.id
            LEFT JOIN notif_buzones    bz ON nb.buzon_id     = bz.id
            WHERE nb.id=?
            """,
            (item_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))

    def upsert_notif_bandeja_item(self, item: dict) -> str:
        import uuid as _uuid
        now     = self._utc_now()
        item_id = str(item.get("id") or _uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO notif_bandeja
                (id, codigo_empresa, ejercicio, buzon_id, organismo_id,
                 asunto, descripcion, tipo_acto, referencia,
                 nif_interesado, nombre_interesado,
                 fecha_puesta_disposicion, fecha_vencimiento,
                 fecha_aceptacion, fecha_rechazo, estado,
                 pdf_path, metadatos_json, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                buzon_id                 = excluded.buzon_id,
                organismo_id             = excluded.organismo_id,
                asunto                   = excluded.asunto,
                descripcion              = excluded.descripcion,
                tipo_acto                = excluded.tipo_acto,
                referencia               = excluded.referencia,
                nif_interesado           = excluded.nif_interesado,
                nombre_interesado        = excluded.nombre_interesado,
                fecha_puesta_disposicion = excluded.fecha_puesta_disposicion,
                fecha_vencimiento        = excluded.fecha_vencimiento,
                fecha_aceptacion         = excluded.fecha_aceptacion,
                fecha_rechazo            = excluded.fecha_rechazo,
                estado                   = excluded.estado,
                pdf_path                 = excluded.pdf_path,
                metadatos_json           = excluded.metadatos_json,
                updated_at               = excluded.updated_at
            """,
            (
                item_id,
                item.get("codigo_empresa"),
                int(item.get("ejercicio") or 0),
                item.get("buzon_id"),
                item.get("organismo_id"),
                item.get("asunto", ""),
                item.get("descripcion"),
                item.get("tipo_acto"),
                item.get("referencia"),
                item.get("nif_interesado"),
                item.get("nombre_interesado"),
                item.get("fecha_puesta_disposicion"),
                item.get("fecha_vencimiento"),
                item.get("fecha_aceptacion"),
                item.get("fecha_rechazo"),
                item.get("estado", "PENDIENTE"),
                item.get("pdf_path"),
                item.get("metadatos_json"),
                item.get("created_at", now),
                now,
            ),
        )
        self.conn.commit()
        return item_id

    def cambiar_estado_notif_bandeja(
        self, codigo_empresa: str, item_id: str, estado: str, fecha: str
    ) -> None:
        now = self._utc_now()
        fecha_col = "fecha_aceptacion" if estado == "ACEPTADA" else "fecha_rechazo"
        self.conn.execute(
            f"UPDATE notif_bandeja SET estado=?, {fecha_col}=?, updated_at=? "
            "WHERE id=? AND codigo_empresa=?",
            (estado, fecha, now, item_id, codigo_empresa),
        )
        self.conn.commit()

    def eliminar_notif_bandeja_item(self, codigo_empresa: str, item_id: str) -> None:
        self.conn.execute(
            "DELETE FROM notif_bandeja WHERE id=? AND codigo_empresa=?",
            (item_id, codigo_empresa),
        )
        self.conn.commit()

    def archivar_notif_bandeja_item(self, codigo_empresa: str, item_id: str, archivada: bool = True) -> None:
        now = self._utc_now()
        self.conn.execute(
            "UPDATE notif_bandeja SET archivada=?, updated_at=? WHERE id=? AND codigo_empresa=?",
            (1 if archivada else 0, now, item_id, codigo_empresa),
        )
        self.conn.commit()

    def marcar_notif_bandeja_enviada_cliente(self, codigo_empresa: str, item_id: str, fecha: str) -> None:
        now = self._utc_now()
        self.conn.execute(
            "UPDATE notif_bandeja SET enviada_cliente=1, fecha_envio_cliente=?, updated_at=? "
            "WHERE id=? AND codigo_empresa=?",
            (fecha, now, item_id, codigo_empresa),
        )
        self.conn.commit()

    def asignar_responsable_notif_bandeja(self, codigo_empresa: str, item_id: str, responsable: str | None) -> None:
        now = self._utc_now()
        self.conn.execute(
            "UPDATE notif_bandeja SET responsable=?, updated_at=? WHERE id=? AND codigo_empresa=?",
            (responsable, now, item_id, codigo_empresa),
        )
        self.conn.commit()

    # ── Notificaciones: listados globales (modulo global) ───────────────────
    # Estos metodos no filtran por empresa: el filtrado por permisos de
    # usuario se aplica en services/secured_gestor.py.

    def listar_empresas_resumen(self) -> list[dict]:
        cur = self.conn.execute(
            "SELECT codigo, nombre, cif, MAX(ejercicio) AS ejercicio "
            "FROM empresas GROUP BY codigo ORDER BY nombre"
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def listar_notif_bandeja_global(self, filtros: dict | None = None) -> list[dict]:
        sql = """
            SELECT nb.*, o.nombre AS organismo_nombre, o.codigo AS organismo_codigo,
                   bz.nombre AS buzon_nombre,
                   e.nombre AS empresa_nombre, e.cif AS empresa_cif
            FROM notif_bandeja nb
            LEFT JOIN notif_organismos o  ON nb.organismo_id = o.id
            LEFT JOIN notif_buzones    bz ON nb.buzon_id     = bz.id
            LEFT JOIN (SELECT codigo, nombre, cif, MAX(ejercicio) AS ejercicio
                       FROM empresas GROUP BY codigo) e ON e.codigo = nb.codigo_empresa
            WHERE 1=1
        """
        params: list = []
        filtros = filtros or {}
        if filtros.get("codigo_empresa"):
            sql += " AND nb.codigo_empresa=?"
            params.append(filtros["codigo_empresa"])
        sql += " ORDER BY nb.fecha_puesta_disposicion DESC, nb.created_at DESC"
        cur = self.conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def listar_notif_certificados_global(self, filtros: dict | None = None) -> list[dict]:
        sql = """
            SELECT c.*, e.nombre AS empresa_nombre, e.cif AS empresa_cif
            FROM notif_certificados c
            LEFT JOIN (SELECT codigo, nombre, cif, MAX(ejercicio) AS ejercicio
                       FROM empresas GROUP BY codigo) e ON e.codigo = c.codigo_empresa
            WHERE 1=1
        """
        params: list = []
        filtros = filtros or {}
        if filtros.get("codigo_empresa"):
            sql += " AND c.codigo_empresa=?"
            params.append(filtros["codigo_empresa"])
        sql += " ORDER BY e.nombre, c.nombre"
        cur = self.conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def listar_notif_buzones_global(self, filtros: dict | None = None) -> list[dict]:
        sql = """
            SELECT b.*, o.nombre AS organismo_nombre, o.codigo AS organismo_codigo,
                   c.nombre AS certificado_nombre,
                   e.nombre AS empresa_nombre, e.cif AS empresa_cif
            FROM notif_buzones b
            LEFT JOIN notif_organismos o   ON b.organismo_id = o.id
            LEFT JOIN notif_certificados c ON b.certificado_id = c.id
            LEFT JOIN (SELECT codigo, nombre, cif, MAX(ejercicio) AS ejercicio
                       FROM empresas GROUP BY codigo) e ON e.codigo = b.codigo_empresa
            WHERE 1=1
        """
        params: list = []
        filtros = filtros or {}
        if filtros.get("codigo_empresa"):
            sql += " AND b.codigo_empresa=?"
            params.append(filtros["codigo_empresa"])
        sql += " ORDER BY e.nombre, b.nombre"
        cur = self.conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    # ── notif_sync_logs ──────────────────────────────────────────────────────

    def listar_notif_sync_logs(self, filtros: dict | None = None) -> list[dict]:
        sql = """
            SELECT l.*, o.nombre AS organismo_nombre, o.codigo AS organismo_codigo,
                   bz.nombre AS buzon_nombre,
                   e.nombre AS empresa_nombre, e.cif AS empresa_cif
            FROM notif_sync_logs l
            LEFT JOIN notif_organismos o  ON l.organismo_id = o.id
            LEFT JOIN notif_buzones    bz ON l.buzon_id     = bz.id
            LEFT JOIN (SELECT codigo, nombre, cif, MAX(ejercicio) AS ejercicio
                       FROM empresas GROUP BY codigo) e ON e.codigo = l.codigo_empresa
            WHERE 1=1
        """
        params: list = []
        filtros = filtros or {}
        if filtros.get("codigo_empresa"):
            sql += " AND l.codigo_empresa=?"
            params.append(filtros["codigo_empresa"])
        sql += " ORDER BY l.fecha_hora DESC"
        cur = self.conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def upsert_notif_sync_log(self, log: dict) -> str:
        import uuid as _uuid
        now    = self._utc_now()
        log_id = str(log.get("id") or _uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO notif_sync_logs
                (id, codigo_empresa, organismo_id, buzon_id, fecha_hora,
                 resultado, error_detalle, notificaciones_detectadas, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                resultado                 = excluded.resultado,
                error_detalle             = excluded.error_detalle,
                notificaciones_detectadas = excluded.notificaciones_detectadas
            """,
            (
                log_id,
                log.get("codigo_empresa"),
                log.get("organismo_id"),
                log.get("buzon_id"),
                log.get("fecha_hora", now),
                log.get("resultado", "OK"),
                log.get("error_detalle"),
                int(log.get("notificaciones_detectadas") or 0),
                log.get("created_at", now),
            ),
        )
        self.conn.commit()
        return log_id

    # ── Seeder de datos simulados ────────────────────────────────────────────

    def sembrar_organismos_simulados(self) -> None:
        """Asegura el catalogo de organismos (buzones estilo Portal NEOS). Idempotente."""
        now = self._utc_now()
        organismos = [
            # (codigo, nombre, tipo, url_portal, descripcion)
            ("DEHU", "Direccion Electronica Habilitada Unica (DEHu)", "ESTATAL",
             "https://dehu.redsara.es/", "Punto unico: AEAT, Seguridad Social y otros"),
            ("TGSS", "Seguridad Social", "ESTATAL",
             "https://sede.seg-social.gob.es/wps/portal/sede/sede/Inicio/NotificacionesTelematicas",
             "SS - Sede electronica"),
            ("DGT", "Direccion General de Trafico", "ESTATAL",
             "https://sede.dgt.gob.es/es/", "DGT - Sede Electronica"),
            ("ENOTUM", "eNotum", "AUTONOMICO",
             "https://api.enotum.cat:8443/", "eNotum (Catalunya)"),
            ("DFGIPUZKOA", "Diputacion Foral de Gipuzkoa", "FORAL",
             "https://w390w.gipuzkoa.net/WAS/HACI/WATGipuzkoatariaWEB/inicio.do?idioma=C&app=BUZON",
             "Sede electronica de la Diputacion Foral de Gipuzkoa"),
            ("GVA", "Generalitat Valenciana", "AUTONOMICO",
             "https://www.comunicaciones.gva.es/comunicaciones/login.html", "Generalitat Valenciana"),
            ("XUNTA", "Xunta de Galicia", "AUTONOMICO",
             "https://notifica.xunta.gal/notificaciones/portal/portada", "Xunta de Galicia"),
            ("MADRID", "Comunidad de Madrid", "AUTONOMICO",
             "https://gestiona3.madrid.org/", "Comunidad de Madrid"),
            ("DPSEVILLA", "Diputacion Provincial de Sevilla", "PROVINCIAL",
             "https://sedeelectronicadipusevilla.es/opencms/opencms/sede", "Diputacion Provincial de Sevilla"),
            ("DFBIZKAIA", "Diputacion Foral de Bizkaia - eBizkaia", "FORAL",
             "https://www.ebizkaia.eus/es/mi-perfil", "Diputacion Foral de Bizkaia - eBizkaia"),
            ("EUSKADI", "Comunidad Autonoma de Pais Vasco", "AUTONOMICO",
             "https://www.euskadi.eus/notificaciones/", "Comunidad Autonoma de Pais Vasco"),
            ("JANDALUCIA", "Junta de Andalucia", "AUTONOMICO",
             "https://ws020.juntadeandalucia.es/", "Junta de Andalucia"),
            ("LPGC", "Ayuntamiento de Las Palmas de Gran Canaria", "LOCAL",
             "https://sedeelectronica.laspalmasgc.es/web/inicioWebc.do?opcion=noreg",
             "Ayuntamiento de Las Palmas de Gran Canaria"),
        ]
        for codigo, nombre, tipo, url, descr in organismos:
            self.conn.execute(
                """
                INSERT INTO notif_organismos
                    (codigo, nombre, tipo, url_portal, descripcion, activo, created_at, updated_at)
                VALUES (?,?,?,?,?,1,?,?)
                ON CONFLICT(codigo) DO UPDATE SET
                    nombre      = excluded.nombre,
                    tipo        = excluded.tipo,
                    url_portal  = excluded.url_portal,
                    descripcion = excluded.descripcion,
                    activo      = 1,
                    updated_at  = excluded.updated_at
                """,
                (codigo, nombre, tipo, url, descr, now, now),
            )
        # Eliminar los organismos de demo antiguos (y sus datos dependientes)
        # que no forman parte del catalogo de Portal NEOS.
        legacy = ("AEAT", "SEPE", "AEPD", "MHACIENDA", "MINTRA", "AYTO")
        ph = ",".join("?" for _ in legacy)
        ids = [r[0] for r in self.conn.execute(
            "SELECT id FROM notif_organismos WHERE codigo IN (%s)" % ph, legacy).fetchall()]
        if ids:
            iph = ",".join("?" for _ in ids)
            buz = [r[0] for r in self.conn.execute(
                "SELECT id FROM notif_buzones WHERE organismo_id IN (%s)" % iph, ids).fetchall()]
            if buz:
                bph = ",".join("?" for _ in buz)
                self.conn.execute("DELETE FROM notif_bandeja WHERE buzon_id IN (%s)" % bph, buz)
                self.conn.execute("DELETE FROM notif_sync_logs WHERE buzon_id IN (%s)" % bph, buz)
            self.conn.execute("DELETE FROM notif_bandeja WHERE organismo_id IN (%s)" % iph, ids)
            self.conn.execute("DELETE FROM notif_sync_logs WHERE organismo_id IN (%s)" % iph, ids)
            self.conn.execute("DELETE FROM notif_buzones WHERE organismo_id IN (%s)" % iph, ids)
            self.conn.execute("DELETE FROM notif_organismos WHERE id IN (%s)" % iph, ids)
        self.conn.commit()

    def sembrar_datos_empresa_simulados(self, codigo_empresa: str, ejercicio: int) -> None:
        """
        Inserta certificados, buzones y bandeja simulados para una empresa.
        Solo actua si no existen datos previos para esa empresa (idempotente).
        """
        import uuid as _uuid

        now = self._utc_now()

        # Obtener CIF de la empresa (para NIF titular)
        emp = self.get_empresa(codigo_empresa, ejercicio)
        nif = (emp or {}).get("cif") or "B00000000"

        # --- certificados ---
        existing_certs = self.listar_notif_certificados(codigo_empresa)
        if not existing_certs:
            for cert in [
                {
                    "id": str(_uuid.uuid4()), "codigo_empresa": codigo_empresa,
                    "nombre": "Certificado FNMT Empresa (vigente)",
                    "nif_titular": nif, "tipo": "PFX",
                    "fecha_emision": "2024-01-15", "fecha_caducidad": "2027-01-15",
                    "notas": "Certificado principal emitido por FNMT-RCM.",
                    "activo": 1, "created_at": now, "updated_at": now,
                },
                {
                    "id": str(_uuid.uuid4()), "codigo_empresa": codigo_empresa,
                    "nombre": "Certificado FNMT por vencer",
                    "nif_titular": nif, "tipo": "PFX",
                    "fecha_emision": "2023-07-01", "fecha_caducidad": "2026-07-01",
                    "notas": "Proximo a caducar. Renovar antes del 01/07/2026.",
                    "activo": 1, "created_at": now, "updated_at": now,
                },
                {
                    "id": str(_uuid.uuid4()), "codigo_empresa": codigo_empresa,
                    "nombre": "Certificado antiguo 2021 (caducado)",
                    "nif_titular": nif, "tipo": "PFX",
                    "fecha_emision": "2021-06-01", "fecha_caducidad": "2023-06-01",
                    "notas": "Caducado. Conservado como referencia historica.",
                    "activo": 0, "created_at": now, "updated_at": now,
                },
            ]:
                self.conn.execute(
                    "INSERT OR IGNORE INTO notif_certificados "
                    "(id,codigo_empresa,nombre,nif_titular,tipo,ruta_archivo,"
                    "fecha_emision,fecha_caducidad,notas,activo,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        cert["id"], cert["codigo_empresa"], cert["nombre"],
                        cert["nif_titular"], cert["tipo"], None,
                        cert["fecha_emision"], cert["fecha_caducidad"],
                        cert["notas"], cert["activo"],
                        cert["created_at"], cert["updated_at"],
                    ),
                )
            self.conn.commit()

        # --- buzones ---
        existing_buzones = self.listar_notif_buzones(codigo_empresa)
        if not existing_buzones:
            self.sembrar_organismos_simulados()
            cert_activo = next(
                (c for c in self.listar_notif_certificados(codigo_empresa) if c.get("activo")),
                None,
            )
            cert_id = cert_activo["id"] if cert_activo else None
            org_map = {o["codigo"]: o["id"] for o in self.listar_notif_organismos()}
            for buzon in [
                {
                    "id": str(_uuid.uuid4()), "codigo_empresa": codigo_empresa,
                    "nombre": "DEH AEAT Principal", "organismo_id": org_map.get("AEAT"),
                    "tipo_buzon": "DEH", "nif_titular": nif,
                    "certificado_id": cert_id, "activo": 1,
                    "ultima_consulta": "2026-06-09T10:30:00",
                },
                {
                    "id": str(_uuid.uuid4()), "codigo_empresa": codigo_empresa,
                    "nombre": "DEH Seguridad Social", "organismo_id": org_map.get("TGSS"),
                    "tipo_buzon": "DEH", "nif_titular": nif,
                    "certificado_id": cert_id, "activo": 1,
                    "ultima_consulta": "2026-06-09T10:31:00",
                },
                {
                    "id": str(_uuid.uuid4()), "codigo_empresa": codigo_empresa,
                    "nombre": "060 AGE General", "organismo_id": org_map.get("MHACIENDA"),
                    "tipo_buzon": "060", "nif_titular": nif,
                    "certificado_id": cert_id, "activo": 1,
                    "ultima_consulta": None,
                },
            ]:
                self.conn.execute(
                    "INSERT OR IGNORE INTO notif_buzones "
                    "(id,codigo_empresa,nombre,organismo_id,tipo_buzon,nif_titular,"
                    "certificado_id,activo,ultima_consulta,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        buzon["id"], buzon["codigo_empresa"], buzon["nombre"],
                        buzon["organismo_id"], buzon["tipo_buzon"], buzon["nif_titular"],
                        buzon["certificado_id"], buzon["activo"], buzon["ultima_consulta"],
                        now, now,
                    ),
                )
            self.conn.commit()

        # --- bandeja ---
        existing_bandeja = self.conn.execute(
            "SELECT COUNT(*) FROM notif_bandeja WHERE codigo_empresa=? AND ejercicio=?",
            (codigo_empresa, int(ejercicio)),
        ).fetchone()[0]
        if not existing_bandeja:
            self.sembrar_organismos_simulados()
            org_map   = {o["codigo"]: o["id"] for o in self.listar_notif_organismos()}
            buzon_map = {b["organismo_codigo"]: b["id"] for b in self.listar_notif_buzones(codigo_empresa) if b.get("organismo_codigo")}
            for item in [
                {
                    "organismo": "AEAT", "asunto": "Requerimiento - Modelo 347 ejercicio 2024",
                    "tipo_acto": "Requerimiento", "referencia": "REQ-2025-00123456",
                    "nif_interesado": nif, "nombre_interesado": (emp or {}).get("nombre", ""),
                    "fecha_puesta_disposicion": "2025-09-01", "fecha_vencimiento": "2025-10-01",
                    "estado": "VENCIDA",
                    "descripcion": "Se requiere informacion sobre operaciones con terceros."
                        " Importe declarado en IVA difiere con informacion de terceros.",
                },
                {
                    "organismo": "AEAT", "asunto": "Notificacion inicio actuaciones de comprobacion limitada",
                    "tipo_acto": "Notificacion", "referencia": "NOT-2026-00789012",
                    "nif_interesado": nif, "nombre_interesado": (emp or {}).get("nombre", ""),
                    "fecha_puesta_disposicion": "2026-05-28", "fecha_vencimiento": "2026-06-28",
                    "estado": "PENDIENTE",
                    "descripcion": "Inicio de actuaciones de comprobacion limitada en relacion"
                        " con el Impuesto sobre el Valor Anadido, periodo 01/2026.",
                },
                {
                    "organismo": "AEAT", "asunto": "Propuesta de liquidacion - IRPF 2024",
                    "tipo_acto": "Propuesta", "referencia": "PRL-2026-00445566",
                    "nif_interesado": nif, "nombre_interesado": (emp or {}).get("nombre", ""),
                    "fecha_puesta_disposicion": "2026-06-01", "fecha_vencimiento": "2026-07-15",
                    "estado": "PENDIENTE",
                    "descripcion": "Propuesta de liquidacion provisional del IRPF correspondiente"
                        " al ejercicio 2024. Diferencia a ingresar: 1.234,56 EUR.",
                },
                {
                    "organismo": "TGSS", "asunto": "Acta de liquidacion de cuotas - Trimestre 1/2026",
                    "tipo_acto": "Acta", "referencia": "ACT-2026-SS-00456789",
                    "nif_interesado": nif, "nombre_interesado": (emp or {}).get("nombre", ""),
                    "fecha_puesta_disposicion": "2026-04-15", "fecha_vencimiento": "2026-05-15",
                    "fecha_aceptacion": "2026-04-18",
                    "estado": "ACEPTADA",
                    "descripcion": "Acta de liquidacion por diferencias en la cotizacion de"
                        " trabajadores. Cuotas regularizadas: 3 trabajadores.",
                },
                {
                    "organismo": "TGSS", "asunto": "Resolucion sobre aplazamiento de deuda",
                    "tipo_acto": "Resolucion", "referencia": "RES-2026-SS-00112233",
                    "nif_interesado": nif, "nombre_interesado": (emp or {}).get("nombre", ""),
                    "fecha_puesta_disposicion": "2026-03-01", "fecha_vencimiento": "2026-04-01",
                    "fecha_aceptacion": "2026-03-05",
                    "estado": "ACEPTADA",
                    "descripcion": "Resolucion estimatoria de la solicitud de aplazamiento"
                        " de deuda por cuotas de Seguridad Social. Concedido fraccionamiento en 6 plazos.",
                },
                {
                    "organismo": "DGT", "asunto": "Notificacion expediente sancionador - Vehiculo de empresa",
                    "tipo_acto": "Expediente sancionador", "referencia": "EXP-DGT-2026-00778899",
                    "nif_interesado": nif, "nombre_interesado": (emp or {}).get("nombre", ""),
                    "fecha_puesta_disposicion": "2026-01-10", "fecha_vencimiento": "2026-02-10",
                    "fecha_rechazo": "2026-01-15",
                    "estado": "RECHAZADA",
                    "descripcion": "Notificacion de inicio de expediente sancionador por"
                        " exceso de velocidad. Vehiculo matricula 0000-ZZZ. Sancion propuesta: 300 EUR.",
                },
                {
                    "organismo": "SEPE", "asunto": "Comunicacion - Solicitud de informacion prestaciones",
                    "tipo_acto": "Comunicacion", "referencia": "COM-SEPE-2026-00334455",
                    "nif_interesado": nif, "nombre_interesado": (emp or {}).get("nombre", ""),
                    "fecha_puesta_disposicion": "2026-06-05", "fecha_vencimiento": "2026-07-05",
                    "estado": "PENDIENTE",
                    "descripcion": "Solicitud de informacion sobre prestaciones por desempleo"
                        " percibidas por trabajadores durante el ejercicio 2025.",
                },
                {
                    "organismo": "AEAT", "asunto": "Diligencia de embargo - Cuenta bancaria",
                    "tipo_acto": "Diligencia de embargo", "referencia": "EMB-2026-00991122",
                    "nif_interesado": nif, "nombre_interesado": (emp or {}).get("nombre", ""),
                    "fecha_puesta_disposicion": "2026-06-08", "fecha_vencimiento": "2026-06-18",
                    "estado": "PENDIENTE",
                    "descripcion": "Diligencia de embargo de cuentas bancarias por deuda tributaria"
                        " pendiente de pago. Importe: 5.678,90 EUR. Plazo de alegaciones: 10 dias.",
                },
            ]:
                org_id   = org_map.get(item["organismo"])
                buzon_id = buzon_map.get(item["organismo"])
                self.conn.execute(
                    "INSERT OR IGNORE INTO notif_bandeja "
                    "(id,codigo_empresa,ejercicio,buzon_id,organismo_id,asunto,descripcion,"
                    "tipo_acto,referencia,nif_interesado,nombre_interesado,"
                    "fecha_puesta_disposicion,fecha_vencimiento,fecha_aceptacion,fecha_rechazo,"
                    "estado,pdf_path,metadatos_json,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(_uuid.uuid4()), codigo_empresa, int(ejercicio),
                        buzon_id, org_id,
                        item["asunto"], item.get("descripcion", ""),
                        item["tipo_acto"], item["referencia"],
                        item["nif_interesado"], item["nombre_interesado"],
                        item["fecha_puesta_disposicion"], item["fecha_vencimiento"],
                        item.get("fecha_aceptacion"), item.get("fecha_rechazo"),
                        item["estado"], None, None,
                        now, now,
                    ),
                )
            self.conn.commit()

    # ── CUOTAS PERIODICAS ─────────────────────────────────────────────────────

    def upsert_cuota_periodica(self, datos: dict):
        import json as _json
        now = self._utc_now()
        cid = datos.get("id") or str(int(__import__("time").time() * 1000))
        lineas = datos.get("lineas") or datos.get("lineas_json") or []
        if isinstance(lineas, list):
            lineas_json = _json.dumps(lineas, ensure_ascii=False)
        else:
            lineas_json = str(lineas)
        self.conn.execute(
            """
            INSERT INTO cuotas_periodicas
              (id, codigo_empresa, ejercicio, tercero_id, nif, nombre, descripcion,
               serie, periodicidad, fecha_inicio, fecha_fin, activa,
               subcuenta_cliente, cuenta_bancaria, forma_pago,
               plantilla_word, plantilla_emitidas, tipo_operacion, modelo_fiscal,
               retencion_aplica, retencion_pct, descuento_total_tipo, descuento_total_valor,
               moneda_codigo, moneda_simbolo, observaciones, lineas_json,
               created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              tercero_id=excluded.tercero_id, nif=excluded.nif, nombre=excluded.nombre,
              descripcion=excluded.descripcion, serie=excluded.serie,
              periodicidad=excluded.periodicidad, fecha_inicio=excluded.fecha_inicio,
              fecha_fin=excluded.fecha_fin, activa=excluded.activa,
              subcuenta_cliente=excluded.subcuenta_cliente,
              cuenta_bancaria=excluded.cuenta_bancaria, forma_pago=excluded.forma_pago,
              plantilla_word=excluded.plantilla_word,
              plantilla_emitidas=excluded.plantilla_emitidas,
              tipo_operacion=excluded.tipo_operacion, modelo_fiscal=excluded.modelo_fiscal,
              retencion_aplica=excluded.retencion_aplica, retencion_pct=excluded.retencion_pct,
              descuento_total_tipo=excluded.descuento_total_tipo,
              descuento_total_valor=excluded.descuento_total_valor,
              moneda_codigo=excluded.moneda_codigo, moneda_simbolo=excluded.moneda_simbolo,
              observaciones=excluded.observaciones, lineas_json=excluded.lineas_json,
              updated_at=excluded.updated_at
            """,
            (
                cid, datos.get("codigo_empresa"), datos.get("ejercicio"),
                datos.get("tercero_id"), datos.get("nif"), datos.get("nombre"),
                datos.get("descripcion"), datos.get("serie"),
                datos.get("periodicidad", "mensual"),
                datos.get("fecha_inicio"), datos.get("fecha_fin"),
                int(datos.get("activa", 1)),
                datos.get("subcuenta_cliente"), datos.get("cuenta_bancaria"),
                datos.get("forma_pago"), datos.get("plantilla_word"),
                datos.get("plantilla_emitidas"),
                datos.get("tipo_operacion", "01"), datos.get("modelo_fiscal"),
                int(datos.get("retencion_aplica") or 0), datos.get("retencion_pct"),
                datos.get("descuento_total_tipo"), datos.get("descuento_total_valor"),
                datos.get("moneda_codigo"), datos.get("moneda_simbolo"),
                datos.get("observaciones"), lineas_json, now, now,
            ),
        )
        self.conn.commit()
        datos["id"] = cid

    def listar_cuotas_periodicas(self, codigo_empresa: str, ejercicio: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM cuotas_periodicas WHERE codigo_empresa=? AND ejercicio=? ORDER BY nombre",
            (codigo_empresa, int(ejercicio)),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_cuota_periodica(self, cuota_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM cuotas_periodicas WHERE id=?", (str(cuota_id),)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def eliminar_cuota_periodica(self, cuota_id: str):
        self.conn.execute("DELETE FROM cuotas_periodicas_generadas WHERE cuota_id=?", (str(cuota_id),))
        self.conn.execute("DELETE FROM cuotas_periodicas WHERE id=?", (str(cuota_id),))
        self.conn.commit()

    def listar_periodos_generados(self, cuota_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT periodo FROM cuotas_periodicas_generadas WHERE cuota_id=? ORDER BY periodo",
            (str(cuota_id),),
        ).fetchall()
        return [r[0] for r in rows]

    def registrar_periodo_generado(self, cuota_id: str, periodo: str, factura_id: str, fecha: str):
        self.conn.execute(
            "INSERT OR IGNORE INTO cuotas_periodicas_generadas (cuota_id, periodo, factura_id, fecha_registro) VALUES (?,?,?,?)",
            (str(cuota_id), periodo, str(factura_id), fecha),
        )
        self.conn.commit()
