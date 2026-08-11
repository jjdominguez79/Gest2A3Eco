import json
import time
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from services.terceros_empresa_fiscal_service import validate_tercero_empresa_rel
from utils.validaciones import (
    inferir_pais_desde_identificacion,
    normalizar_codigo_empresa_a3,
    normalizar_codigo_pais,
    normalizar_nif_cif,
)


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
    def __init__(self, source: Path, action: str, original: Exception):
        self.source = Path(source)
        self.action = action
        self.original = original
        super().__init__(f"No se pudo {action} la base de datos en '{self.source}': {original}")


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
  numero_cuenta TEXT,
  subcuenta_banco TEXT,
  subcuenta_por_defecto TEXT,
  conceptos_json TEXT,
  excel_json TEXT,
  PRIMARY KEY (codigo_empresa, ejercicio, banco)
);
CREATE TABLE IF NOT EXISTS importaciones_bancos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  banco TEXT NOT NULL,
  numero_cuenta TEXT,
  subcuenta_banco TEXT,
  usuario_id INTEGER,
  usuario TEXT,
  fecha_importacion TEXT NOT NULL,
  archivo_origen TEXT,
  hoja TEXT,
  archivo_generado TEXT,
  estado TEXT NOT NULL,
  filas_leidas INTEGER DEFAULT 0,
  movimientos_generados INTEGER DEFAULT 0,
  movimientos_omitidos INTEGER DEFAULT 0,
  fecha_primer_asiento TEXT,
  fecha_ultimo_asiento TEXT,
  saldo_primer_asiento REAL,
  saldo_final REAL,
  importe_entradas REAL DEFAULT 0,
  importe_salidas REAL DEFAULT 0,
  variacion_neta REAL DEFAULT 0,
  movimientos_duplicados INTEGER DEFAULT 0,
  movimientos_modificados INTEGER DEFAULT 0,
  modo_duplicados TEXT,
  importaciones_solapadas_json TEXT,
  avisos_json TEXT,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_importaciones_bancos_empresa
  ON importaciones_bancos(codigo_empresa, ejercicio, fecha_importacion DESC);
CREATE TABLE IF NOT EXISTS importaciones_bancos_movimientos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  importacion_id INTEGER NOT NULL,
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  banco TEXT,
  numero_cuenta TEXT,
  subcuenta_banco TEXT,
  fecha TEXT NOT NULL,
  importe REAL NOT NULL,
  concepto TEXT,
  referencia TEXT,
  saldo REAL,
  huella TEXT NOT NULL,
  ocurrencia INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  FOREIGN KEY (importacion_id) REFERENCES importaciones_bancos(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_importaciones_bancos_movimientos_cuenta
  ON importaciones_bancos_movimientos(
    codigo_empresa, ejercicio, subcuenta_banco, fecha, huella, ocurrencia
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
  facturae_error TEXT,
  updated_at TEXT,
  pdf_generated_at TEXT
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
  lineas_json TEXT,
  updated_at TEXT,
  pdf_generated_at TEXT
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
CREATE TABLE IF NOT EXISTS comunicaciones (
  id TEXT PRIMARY KEY,
  codigo_empresa TEXT NOT NULL,
  asunto TEXT NOT NULL,
  etiqueta TEXT,
  estado TEXT NOT NULL DEFAULT 'abierta',
  responsable_usuario_id INTEGER,
  responsable_nombre TEXT,
  descartado INTEGER NOT NULL DEFAULT 0,
  descartado_por TEXT,
  descartado_at TEXT,
  motivo_descarte TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comunicaciones_empresa
  ON comunicaciones(codigo_empresa, updated_at DESC);
CREATE TABLE IF NOT EXISTS comunicaciones_mensajes (
  id TEXT PRIMARY KEY,
  comunicacion_id TEXT NOT NULL,
  direccion TEXT NOT NULL,
  remitente TEXT,
  destinatarios_json TEXT NOT NULL,
  cc_json TEXT,
  asunto TEXT NOT NULL,
  cuerpo_html TEXT,
  estado_envio TEXT NOT NULL,
  error_envio TEXT,
  graph_message_id TEXT,
  internet_message_id TEXT,
  tiene_adjuntos INTEGER NOT NULL DEFAULT 0,
  usuario_id INTEGER,
  usuario_nombre TEXT,
  fecha TEXT NOT NULL,
  FOREIGN KEY (comunicacion_id) REFERENCES comunicaciones(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_com_mensajes_comunicacion
  ON comunicaciones_mensajes(comunicacion_id, fecha DESC);
CREATE TABLE IF NOT EXISTS comunicaciones_adjuntos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mensaje_id TEXT NOT NULL,
  nombre TEXT NOT NULL,
  ruta TEXT NOT NULL,
  tamano INTEGER,
  FOREIGN KEY (mensaje_id) REFERENCES comunicaciones_mensajes(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS comunicaciones_sync (
  mailbox TEXT PRIMARY KEY,
  delta_link TEXT,
  ultima_sincronizacion TEXT,
  ultimo_error TEXT
);
CREATE TABLE IF NOT EXISTS comunicaciones_avisos_estado (
  usuario_id INTEGER PRIMARY KEY,
  ultimo_control_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS comunicaciones_avisos_vistos (
  usuario_id INTEGER NOT NULL,
  graph_message_id TEXT NOT NULL,
  avisado_at TEXT NOT NULL,
  PRIMARY KEY (usuario_id, graph_message_id)
);
CREATE TABLE IF NOT EXISTS comunicaciones_sin_asignar (
  graph_message_id TEXT PRIMARY KEY,
  mailbox TEXT NOT NULL,
  remitente TEXT,
  asunto TEXT,
  etiqueta TEXT,
  fecha TEXT,
  cuerpo_html TEXT,
  payload_json TEXT NOT NULL,
  sugerencia_codigo_empresa TEXT,
  sugerencia_nombre TEXT,
  responsable_usuario_id INTEGER,
  responsable_nombre TEXT,
  estado TEXT NOT NULL DEFAULT 'pendiente',
  sin_cliente_confirmado INTEGER NOT NULL DEFAULT 0,
  descartado INTEGER NOT NULL DEFAULT 0,
  descartado_por TEXT,
  descartado_at TEXT,
  motivo_descarte TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS categorias_documentales (
  id TEXT PRIMARY KEY,
  nombre TEXT NOT NULL,
  carpeta TEXT NOT NULL UNIQUE,
  permite_ocr INTEGER NOT NULL DEFAULT 0,
  activa INTEGER NOT NULL DEFAULT 1,
  orden INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS documentos_archivo (
  id TEXT PRIMARY KEY,
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  categoria_id TEXT NOT NULL,
  nombre_original TEXT NOT NULL,
  nombre_archivo TEXT NOT NULL,
  ruta TEXT NOT NULL,
  hash_archivo TEXT NOT NULL,
  tamano INTEGER,
  mime_type TEXT,
  origen TEXT NOT NULL DEFAULT 'correo',
  comunicacion_id TEXT,
  mensaje_id TEXT,
  graph_message_id TEXT,
  graph_attachment_id TEXT,
  correo_remitente TEXT,
  correo_asunto TEXT,
  estado TEXT NOT NULL DEFAULT 'archivado',
  ocr_documento_id TEXT,
  creado_por TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (categoria_id) REFERENCES categorias_documentales(id),
  UNIQUE(codigo_empresa, hash_archivo)
);
CREATE INDEX IF NOT EXISTS idx_documentos_archivo_empresa
  ON documentos_archivo(codigo_empresa, ejercicio, categoria_id, created_at DESC);
CREATE TABLE IF NOT EXISTS comunicaciones_adjuntos_decisiones (
  graph_message_id TEXT NOT NULL,
  graph_attachment_id TEXT NOT NULL,
  nombre TEXT,
  accion TEXT NOT NULL,
  categoria_id TEXT,
  documento_id TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (graph_message_id, graph_attachment_id)
);
CREATE TABLE IF NOT EXISTS firma_solicitudes (
  id TEXT PRIMARY KEY,
  codigo_empresa TEXT NOT NULL,
  ejercicio INTEGER NOT NULL,
  origen TEXT NOT NULL DEFAULT 'archivo',
  documento_archivo_id TEXT,
  nombre_documento TEXT NOT NULL,
  ruta_origen TEXT NOT NULL,
  ruta_envio TEXT,
  hash_origen TEXT NOT NULL,
  proveedor TEXT NOT NULL DEFAULT 'signrequest',
  request_id TEXT,
  external_id TEXT,
  asunto TEXT,
  mensaje TEXT,
  usar_sms INTEGER NOT NULL DEFAULT 0,
  estado TEXT NOT NULL DEFAULT 'borrador',
  ruta_firmado TEXT,
  ruta_registro_firma TEXT,
  sha256_firmado TEXT,
  sha256_registro_firma TEXT,
  security_hash TEXT,
  signing_log_security_hash TEXT,
  documento_firmado_archivo_id TEXT,
  creado_por TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  enviado_at TEXT,
  firmado_at TEXT,
  UNIQUE(proveedor, request_id)
);
CREATE INDEX IF NOT EXISTS idx_firma_solicitudes_empresa
  ON firma_solicitudes(codigo_empresa, ejercicio, estado, created_at DESC);
CREATE TABLE IF NOT EXISTS firma_firmantes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  solicitud_id TEXT NOT NULL,
  orden INTEGER NOT NULL DEFAULT 1,
  nombre TEXT,
  email TEXT NOT NULL,
  telefono TEXT,
  tercero_id TEXT,
  es_remitente INTEGER NOT NULL DEFAULT 0,
  estado TEXT NOT NULL DEFAULT 'pendiente',
  FOREIGN KEY (solicitud_id) REFERENCES firma_solicitudes(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS firma_zonas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  solicitud_id TEXT NOT NULL,
  pagina INTEGER NOT NULL,
  x REAL NOT NULL,
  y REAL NOT NULL,
  ancho REAL NOT NULL,
  alto REAL NOT NULL,
  firmante INTEGER NOT NULL,
  FOREIGN KEY (solicitud_id) REFERENCES firma_solicitudes(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS firma_eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  solicitud_id TEXT NOT NULL,
  tipo TEXT NOT NULL,
  detalle_json TEXT,
  usuario TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (solicitud_id) REFERENCES firma_solicitudes(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS mensajeria_adjuntos_entrada (
  id TEXT PRIMARY KEY,
  mensaje_remoto_id TEXT NOT NULL,
  conversacion_remota_id TEXT NOT NULL,
  codigo_empresa TEXT NOT NULL,
  empresa_nombre TEXT,
  nombre_original TEXT NOT NULL,
  ruta_entrada TEXT NOT NULL,
  hash_archivo TEXT NOT NULL,
  tamano INTEGER,
  mime_type TEXT,
  remitente TEXT,
  estado TEXT NOT NULL DEFAULT 'pendiente_clasificar',
  error_detalle TEXT,
  documento_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_adjuntos_entrada_estado
  ON mensajeria_adjuntos_entrada(estado, codigo_empresa, created_at);
CREATE TABLE IF NOT EXISTS plantillas_firma (
  id TEXT PRIMARY KEY,
  nombre TEXT NOT NULL UNIQUE,
  descripcion TEXT,
  archivo_relativo TEXT NOT NULL UNIQUE,
  alcance TEXT NOT NULL DEFAULT 'global',
  version INTEGER NOT NULL DEFAULT 1,
  hash_docx TEXT NOT NULL,
  asunto TEXT,
  mensaje TEXT,
  activa INTEGER NOT NULL DEFAULT 0,
  zonas_revisadas INTEGER NOT NULL DEFAULT 0,
  creado_por TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plantillas_firma_empresas (
  plantilla_id TEXT NOT NULL,
  codigo_empresa TEXT NOT NULL,
  PRIMARY KEY (plantilla_id, codigo_empresa),
  FOREIGN KEY (plantilla_id) REFERENCES plantillas_firma(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS plantillas_firma_campos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plantilla_id TEXT NOT NULL,
  clave TEXT NOT NULL,
  etiqueta TEXT NOT NULL,
  origen TEXT NOT NULL DEFAULT 'manual',
  campo_origen TEXT,
  tipo TEXT NOT NULL DEFAULT 'texto',
  obligatorio INTEGER NOT NULL DEFAULT 0,
  valor_defecto TEXT,
  orden INTEGER NOT NULL DEFAULT 0,
  UNIQUE (plantilla_id, clave),
  FOREIGN KEY (plantilla_id) REFERENCES plantillas_firma(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS plantillas_firma_firmantes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plantilla_id TEXT NOT NULL,
  rol TEXT NOT NULL,
  origen TEXT NOT NULL DEFAULT 'manual',
  nombre TEXT,
  email TEXT,
  telefono TEXT,
  orden INTEGER NOT NULL DEFAULT 1,
  usar_sms INTEGER NOT NULL DEFAULT 0,
  UNIQUE (plantilla_id, orden),
  FOREIGN KEY (plantilla_id) REFERENCES plantillas_firma(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS plantillas_firma_zonas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plantilla_id TEXT NOT NULL,
  rol TEXT NOT NULL,
  pagina INTEGER NOT NULL,
  x REAL NOT NULL,
  y REAL NOT NULL,
  ancho REAL NOT NULL,
  alto REAL NOT NULL,
  FOREIGN KEY (plantilla_id) REFERENCES plantillas_firma(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS documentos_firma_generados (
  id TEXT PRIMARY KEY,
  plantilla_id TEXT NOT NULL,
  plantilla_version INTEGER NOT NULL,
  plantilla_hash TEXT NOT NULL,
  codigo_empresa TEXT,
  tercero_id TEXT,
  titulo TEXT NOT NULL,
  datos_json TEXT NOT NULL,
  firmantes_json TEXT NOT NULL,
  ruta_docx TEXT NOT NULL,
  ruta_pdf TEXT NOT NULL,
  hash_docx TEXT,
  hash_pdf TEXT,
  estado TEXT NOT NULL DEFAULT 'borrador',
  solicitud_id TEXT UNIQUE,
  creado_por TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (plantilla_id) REFERENCES plantillas_firma(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_documentos_firma_generados
  ON documentos_firma_generados(codigo_empresa, created_at DESC);
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


class GestorBase:
    """
    Base historica de metodos de negocio del gestor.

    No debe instanciarse directamente. La aplicacion usa GestorPostgres como
    gestor concreto.
    """

    def __init__(self, source: str | Path, json_seed: str | Path | None = None):
        raise RuntimeError("GestorBase no se instancia directamente; usa GestorPostgres.")

    # ---------- utilidades internas ----------
    def _init_schema(self):
        self.conn.executescript(SCHEMA + AUTH_SCHEMA)
        self.conn.commit()
        self._seed_categorias_documentales()
        self._ensure_column(
            "firma_solicitudes", "documento_firmado_archivo_id", "TEXT"
        )
        self.conn.commit()
        self._ensure_column("empresas", "cuenta_bancaria", "TEXT")
        self._ensure_column("empresas", "cuentas_bancarias", "TEXT")
        self._ensure_column("empresas", "pdf_ref_seq", "INTEGER")
        self._ensure_column("empresas", "serie_emitidas_rect", "TEXT")
        self._ensure_column("empresas", "siguiente_num_emitidas_rect", "INTEGER")
        self._ensure_column("empresas", "logo_max_width_mm", "REAL")
        self._ensure_column("empresas", "logo_max_height_mm", "REAL")
        self._ensure_column("empresas", "pais", "TEXT")
        self._ensure_column("empresas", "responsable", "TEXT")
        self._ensure_column("comunicaciones", "graph_conversation_id", "TEXT")
        self._ensure_column("comunicaciones", "etiqueta", "TEXT")
        self._ensure_column("comunicaciones", "descartado", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("comunicaciones", "descartado_por", "TEXT")
        self._ensure_column("comunicaciones", "descartado_at", "TEXT")
        self._ensure_column("comunicaciones", "motivo_descarte", "TEXT")
        self._ensure_column("comunicaciones_mensajes", "mailbox", "TEXT")
        self._ensure_column(
            "comunicaciones_mensajes", "tiene_adjuntos",
            "INTEGER NOT NULL DEFAULT 0",
        )
        self._ensure_column("comunicaciones_sin_asignar", "sugerencia_codigo_empresa", "TEXT")
        self._ensure_column("comunicaciones_sin_asignar", "etiqueta", "TEXT")
        self._ensure_column("comunicaciones_sin_asignar", "sugerencia_nombre", "TEXT")
        self._ensure_column("comunicaciones_sin_asignar", "responsable_usuario_id", "INTEGER")
        self._ensure_column("comunicaciones_sin_asignar", "responsable_nombre", "TEXT")
        self._ensure_column("comunicaciones_sin_asignar", "estado", "TEXT NOT NULL DEFAULT 'pendiente'")
        self._ensure_column("comunicaciones_sin_asignar", "sin_cliente_confirmado", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("comunicaciones_sin_asignar", "descartado", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("comunicaciones_sin_asignar", "descartado_por", "TEXT")
        self._ensure_column("comunicaciones_sin_asignar", "descartado_at", "TEXT")
        self._ensure_column("comunicaciones_sin_asignar", "motivo_descarte", "TEXT")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS comunicaciones_avisos_estado (
              usuario_id INTEGER PRIMARY KEY,
              ultimo_control_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS comunicaciones_avisos_vistos (
              usuario_id INTEGER NOT NULL,
              graph_message_id TEXT NOT NULL,
              avisado_at TEXT NOT NULL,
              PRIMARY KEY (usuario_id, graph_message_id)
            )
            """
        )
        self.conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_com_msg_graph "
            "ON comunicaciones_mensajes(graph_message_id) "
            "WHERE graph_message_id IS NOT NULL AND graph_message_id<>''"
        )
        self.conn.execute(
            "UPDATE comunicaciones SET estado='respondido' WHERE estado='contestado'"
        )
        self.conn.commit()
        self._ensure_column("bancos", "numero_cuenta", "TEXT")
        self._ensure_column("importaciones_bancos", "numero_cuenta", "TEXT")
        self._ensure_column("importaciones_bancos", "movimientos_duplicados", "INTEGER DEFAULT 0")
        self._ensure_column("importaciones_bancos", "movimientos_modificados", "INTEGER DEFAULT 0")
        self._ensure_column("importaciones_bancos", "modo_duplicados", "TEXT")
        self._ensure_column("importaciones_bancos", "importaciones_solapadas_json", "TEXT")
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
        self._ensure_column("albaranes_emitidas_docs", "updated_at", "TEXT")
        self._ensure_column("albaranes_emitidas_docs", "pdf_generated_at", "TEXT")
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
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS usuarios_permisos_globales (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              usuario_id INTEGER NOT NULL,
              permiso TEXT NOT NULL,
              activo INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(usuario_id, permiso),
              FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_usuarios_permisos_globales_usuario
              ON usuarios_permisos_globales(usuario_id);
            CREATE TABLE IF NOT EXISTS dgt_facturas (
              expediente_id TEXT PRIMARY KEY,
              factura_id TEXT NOT NULL UNIQUE,
              codigo_empresa TEXT NOT NULL,
              ejercicio INTEGER NOT NULL,
              destinatario TEXT NOT NULL,
              honorarios REAL NOT NULL DEFAULT 0,
              tasa_dgt REAL NOT NULL DEFAULT 0,
              impuesto_620 REAL NOT NULL DEFAULT 0,
              otros_suplidos REAL NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_dgt_facturas_factura
              ON dgt_facturas(factura_id);
        """)
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
        self._ensure_column("facturas_emitidas_docs", "updated_at", "TEXT")
        self._ensure_column("facturas_emitidas_docs", "pdf_generated_at", "TEXT")
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
                tipo_operacion_iva TEXT DEFAULT 'INTERIOR_DEDUCIBLE',
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

            CREATE TABLE IF NOT EXISTS ocr_aprendizaje_ejemplos (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id         TEXT NOT NULL,
                documento_id       TEXT NOT NULL,
                factura_id         TEXT NOT NULL UNIQUE,
                proveedor_nif      TEXT,
                origen_path        TEXT,
                datos_validados_json TEXT NOT NULL,
                estado             TEXT NOT NULL DEFAULT 'pendiente',
                modelo_destino     TEXT,
                fecha_validacion   TEXT NOT NULL,
                fecha_exportacion  TEXT,
                notas              TEXT,
                marcas_json        TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_ocr_aprendizaje_empresa
                ON ocr_aprendizaje_ejemplos(empresa_id, estado, proveedor_nif);
        """)
        self._ensure_column("facturas_recibidas", "pct_fraccion", "INTEGER")
        self._ensure_column("facturas_emitidas", "pct_fraccion", "INTEGER")
        self._ensure_column("ocr_aprendizaje_ejemplos", "marcas_json", "TEXT NOT NULL DEFAULT '{}'")
        self.conn.commit()
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
        # Las bases creadas antes de incorporar el control de fecha no
        # reciben cambios al ejecutar CREATE TABLE IF NOT EXISTS. Asegurar
        # la columna permite actualizar esas bases sin perder los periodos
        # ya registrados.
        self._ensure_column(
            "cuotas_periodicas_generadas", "fecha_registro", "TEXT"
        )
        self.conn.commit()

    def _seed_categorias_documentales(self) -> None:
        categorias = (
            ("facturas_recibidas", "Facturas recibidas", "FACTURAS_RECIBIDAS", 1, 10),
            ("fiscal", "Fiscal", "FISCAL", 0, 20),
            ("contable", "Contable", "CONTABLE", 0, 30),
            ("laboral", "Laboral", "LABORAL", 0, 40),
            ("bancaria", "Bancaria", "BANCARIA", 0, 50),
            ("mercantil", "Mercantil", "MERCANTIL", 0, 60),
            ("contratos", "Contratos", "CONTRATOS", 0, 70),
            ("firmas", "Firmas", "FIRMAS", 0, 75),
            ("notificaciones", "Notificaciones", "NOTIFICACIONES", 0, 80),
            ("otros", "Otros", "OTROS", 0, 90),
        )
        for categoria_id, nombre, carpeta, permite_ocr, orden in categorias:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO categorias_documentales
                  (id,nombre,carpeta,permite_ocr,activa,orden)
                VALUES (?,?,?,?,1,?)
                """,
                (categoria_id, nombre, carpeta, permite_ocr, orden),
            )
    def _ensure_column(self, table: str, column: str, col_type: str):
        cur = self.conn.execute(f"PRAGMA table_info({table})")
        cols = {r[1] for r in cur.fetchall()}
        if column in cols:
            return
        self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()

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
        eje = _ej_val(ejercicio)
        existente = self.conn.execute(
            "SELECT id FROM series_emitidas WHERE codigo_empresa=? AND ejercicio=? AND nombre=?",
            (codigo, eje, nombre),
        ).fetchone()
        if existente:
            self.conn.execute(
                "UPDATE series_emitidas SET siguiente_num=?, es_rectificativa=?, activa=? WHERE id=?",
                (int(siguiente_num), int(es_rectificativa), int(activa), existente[0]),
            )
        else:
            # No depender de una restriccion UNIQUE para guardar. Algunas bases
            # creadas con versiones antiguas no la incorporaron al actualizar el esquema.
            self.conn.execute(
                "INSERT INTO series_emitidas (codigo_empresa, ejercicio, nombre, siguiente_num, es_rectificativa, activa) VALUES (?,?,?,?,?,?)",
                (codigo, eje, nombre, int(siguiente_num), int(es_rectificativa), int(activa)),
            )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM series_emitidas WHERE codigo_empresa=? AND ejercicio=? AND nombre=?",
            (codigo, eje, nombre)
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

    def buscar_empresa_por_nif(self, nif: str | None, excluir_codigo: str | None = None):
        """Localiza una empresa por CIF/NIF normalizado.

        Se itera sobre las filas para que tambien se detecten datos antiguos
        que se guardaron con guiones, espacios o minusculas.
        """
        nif_norm = normalizar_nif_cif(nif)
        if not nif_norm:
            return None
        excluido = str(excluir_codigo or "").strip().upper()
        for empresa in self.listar_empresas():
            codigo = str(empresa.get("codigo") or "").strip().upper()
            if codigo == excluido:
                continue
            if normalizar_nif_cif(empresa.get("cif")) == nif_norm:
                return empresa
        return None

    def upsert_empresa(self, emp: dict):
        emp = dict(emp or {})
        codigo = normalizar_codigo_empresa_a3(emp.get("codigo"))
        emp["codigo"] = codigo
        emp["cif"] = normalizar_nif_cif(emp.get("cif"))
        duplicada = self.buscar_empresa_por_nif(emp.get("cif"), excluir_codigo=codigo)
        if duplicada:
            raise ValueError(
                "Ya existe una empresa con el CIF/NIF "
                f"{emp['cif']}: {duplicada.get('codigo')}."
            )
        existe = self.get_empresa(codigo, emp.get("ejercicio"))
        self.conn.execute(
            """
            INSERT INTO empresas (codigo, ejercicio, nombre, digitos_plan, serie_emitidas,
                siguiente_num_emitidas, serie_emitidas_rect, siguiente_num_emitidas_rect,
                pdf_ref_seq, cuenta_bancaria, cuentas_bancarias, cif, direccion, cp, poblacion, provincia, pais, telefono, email,
                logo_path, logo_max_width_mm, logo_max_height_mm, activo, naf, responsable)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                naf=excluded.naf,
                responsable=excluded.responsable
            """,
            (
                codigo,
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
                emp.get("responsable"),
            ),
        )
        self.conn.commit()
        if not existe:
            self._clonar_plantillas_si_hace_falta(codigo, emp.get("ejercicio"))

    def cambiar_codigo_empresa(self, codigo_actual: str, codigo_nuevo: str) -> bool:
        """Renombra una empresa y todas sus referencias dentro de una transaccion."""
        actual = normalizar_codigo_empresa_a3(codigo_actual)
        nuevo = normalizar_codigo_empresa_a3(codigo_nuevo)
        if not actual or not nuevo:
            raise ValueError("El codigo A3 de la empresa es obligatorio.")
        if actual == nuevo:
            return False
        if not self.get_empresa(actual):
            raise ValueError(f"No existe la empresa con codigo {actual}.")
        if self.get_empresa(nuevo):
            raise ValueError(f"Ya existe una empresa con el codigo {nuevo}.")

        # codigo_empresa es el nombre comun en el esquema. Las dos variantes
        # historicas se limitan a tablas conocidas para no tocar otros IDs.
        columnas = [("codigo_empresa", None), ("empresa_codigo", {"usuarios_empresas"})]
        columnas.append(("empresa_id", {
            "documentos_ocr", "facturas_recibidas_ocr", "ocr_aprendizaje_ejemplos",
        }))
        try:
            for columna, tablas_permitidas in columnas:
                filas = self.conn.execute(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE table_schema=current_schema() AND column_name=?",
                    (columna,),
                ).fetchall()
                for fila in filas:
                    tabla = str(fila["table_name"] or "")
                    if tablas_permitidas is not None and tabla not in tablas_permitidas:
                        continue
                    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", tabla):
                        continue
                    self.conn.execute(
                        f"UPDATE {tabla} SET {columna}=? WHERE {columna}=?",
                        (nuevo, actual),
                    )
            self.conn.execute(
                "UPDATE empresas SET codigo=? WHERE codigo=?", (nuevo, actual),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return True

    # ---------- Cuenta ingreso predeterminada en maestro ----------
    def _migrate_prefijo_ingreso_empresa(self):
        """Para E00090: rellena cuenta_ingreso_predeterminada_id en maestro_subcuentas_empresa.

        Para cada subcuenta de cliente (430XXXXX) que no tenga ya ingreso configurado,
        deriva la cuenta de ingreso sustituyendo el prefijo 430 por 438.
        Ej: 43000001 → 43800001, 43000002 → 43800002.
        Solo actua si la subcuenta 438XXXXX correspondiente existe en el maestro.
        """
        rows = self.conn.execute(
            """
            SELECT id, subcuenta
              FROM maestro_subcuentas_empresa
             WHERE codigo_empresa = 'E00090'
               AND subcuenta LIKE '430%'
               AND (cuenta_ingreso_predeterminada_id IS NULL
                    OR cuenta_ingreso_predeterminada_id = '')
            """
        ).fetchall()
        for row in rows:
            subcuenta = str(row[1] or "")
            if len(subcuenta) >= 3:
                ingreso = "438" + subcuenta[3:]
                # Verificar que la subcuenta 438XXXXX existe en el maestro
                existe = self.conn.execute(
                    "SELECT 1 FROM maestro_subcuentas_empresa WHERE codigo_empresa='E00090' AND subcuenta=?",
                    (ingreso,),
                ).fetchone()
                if existe:
                    self.conn.execute(
                        "UPDATE maestro_subcuentas_empresa SET cuenta_ingreso_predeterminada_id=? WHERE id=?",
                        (ingreso, row[0]),
                    )
        self.conn.commit()

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
            LEFT JOIN empresas e
              ON e.codigo = s.codigo_empresa
             AND e.ejercicio = (
                 SELECT MAX(e2.ejercicio) FROM empresas e2
                 WHERE e2.codigo = s.codigo_empresa
             )
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

    def next_pdf_ref(
        self, codigo_empresa: str, ejercicio: int | None = None, prefix: str = "E",
    ) -> str:
        eje = _ej_val(ejercicio)
        row = self.get_empresa(codigo_empresa, eje)
        if not row and eje is not None:
            row = self.get_empresa(codigo_empresa, None)
        if not row:
            raise ValueError(f"Empresa no encontrada para generar referencia PDF: {codigo_empresa}")

        prefix = str(prefix or "E").strip().upper()[:1]
        if not prefix.isalnum():
            raise ValueError("El prefijo de referencia PDF no es valido.")
        seq = int(row.get("pdf_ref_seq") or 0)
        if seq <= 0:
            cur = self.conn.execute(
                """SELECT pdf_ref FROM facturas_emitidas_docs WHERE codigo_empresa=? AND pdf_ref IS NOT NULL AND TRIM(pdf_ref)<>''
                   UNION ALL
                   SELECT pdf_ref FROM facturas_recibidas_docs WHERE codigo_empresa=? AND pdf_ref IS NOT NULL AND TRIM(pdf_ref)<>''""",
                (codigo_empresa, codigo_empresa),
            )
            for item in cur.fetchall():
                ref = str(item["pdf_ref"] or "").strip()
                base = ref.split("@", 1)[0]
                # La secuencia se comparte entre emitidas (E) y recibidas (R)
                # para evitar reutilizaciones si se cambia el prefijo.
                match = re.match(r"^[A-Z](\d{1,8})$", base, re.IGNORECASE)
                if match:
                    seq = max(seq, int(match.group(1)))

        seq += 1
        self.conn.execute(
            "UPDATE empresas SET pdf_ref_seq=? WHERE codigo=? AND ejercicio=?",
            (seq, str(row.get("codigo") or codigo_empresa), _ej_val(row.get("ejercicio"))),
        )
        self.conn.commit()
        return f"{prefix}{seq:08d}"

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
            INSERT INTO bancos (codigo_empresa, ejercicio, banco, numero_cuenta, subcuenta_banco, subcuenta_por_defecto, conceptos_json, excel_json)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(codigo_empresa, ejercicio, banco) DO UPDATE SET
                numero_cuenta=excluded.numero_cuenta,
                subcuenta_banco=excluded.subcuenta_banco,
                subcuenta_por_defecto=excluded.subcuenta_por_defecto,
                conceptos_json=excluded.conceptos_json,
                excel_json=excluded.excel_json
            """,
            (
                plantilla.get("codigo_empresa"),
                eje,
                plantilla.get("banco"),
                plantilla.get("numero_cuenta"),
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

    def crear_importacion_banco(self, datos: dict) -> int:
        campos = (
            "codigo_empresa", "ejercicio", "banco", "numero_cuenta", "subcuenta_banco",
            "usuario_id", "usuario", "fecha_importacion", "archivo_origen",
            "hoja", "archivo_generado", "estado", "filas_leidas",
            "movimientos_generados", "movimientos_omitidos",
            "fecha_primer_asiento", "fecha_ultimo_asiento",
            "saldo_primer_asiento", "saldo_final", "importe_entradas",
            "importe_salidas", "variacion_neta", "movimientos_duplicados",
            "movimientos_modificados", "modo_duplicados",
            "importaciones_solapadas_json", "avisos_json", "error",
        )
        valores = dict(datos)
        valores.setdefault("fecha_importacion", datetime.now().isoformat(timespec="seconds"))
        valores["ejercicio"] = _ej_val(valores.get("ejercicio"))
        valores["avisos_json"] = json.dumps(
            valores.get("avisos") or [], ensure_ascii=False
        )
        valores["importaciones_solapadas_json"] = json.dumps(
            valores.get("importaciones_solapadas") or [], ensure_ascii=False
        )
        cur = self.conn.execute(
            "INSERT INTO importaciones_bancos ({}) VALUES ({})".format(
                ", ".join(campos), ", ".join("?" for _ in campos)
            ),
            tuple(valores.get(campo) for campo in campos),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def listar_importaciones_bancos(self, codigo_empresa: str, ejercicio: int, limite: int = 250):
        cur = self.conn.execute(
            """
            SELECT * FROM importaciones_bancos
            WHERE codigo_empresa=? AND ejercicio=?
            ORDER BY fecha_importacion DESC, id DESC
            LIMIT ?
            """,
            (codigo_empresa, _ej_val(ejercicio), max(1, int(limite))),
        )
        out = []
        for row in cur.fetchall():
            dato = self._row_to_dict(row)
            dato["avisos"] = json.loads(dato.get("avisos_json") or "[]")
            dato["importaciones_solapadas"] = json.loads(
                dato.get("importaciones_solapadas_json") or "[]"
            )
            dato.pop("avisos_json", None)
            dato.pop("importaciones_solapadas_json", None)
            out.append(dato)
        return out

    def guardar_movimientos_importacion_banco(
        self, importacion_id: int, datos_cuenta: dict, movimientos: list[dict]
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        filas = [
            (
                int(importacion_id),
                datos_cuenta.get("codigo_empresa"),
                _ej_val(datos_cuenta.get("ejercicio")),
                datos_cuenta.get("banco"),
                datos_cuenta.get("numero_cuenta"),
                datos_cuenta.get("subcuenta_banco"),
                mov.get("fecha"),
                mov.get("importe"),
                mov.get("concepto"),
                mov.get("referencia"),
                mov.get("saldo"),
                mov.get("huella"),
                int(mov.get("ocurrencia") or 1),
                now,
            )
            for mov in movimientos or []
        ]
        if filas:
            self.conn.executemany(
                """
                INSERT INTO importaciones_bancos_movimientos (
                  importacion_id, codigo_empresa, ejercicio, banco,
                  numero_cuenta, subcuenta_banco, fecha, importe, concepto,
                  referencia, saldo, huella, ocurrencia, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                filas,
            )
            self.conn.commit()
        return len(filas)

    def listar_movimientos_importados_banco(
        self, codigo_empresa: str, ejercicio: int, plantilla: dict
    ) -> list[dict]:
        numero = str(plantilla.get("numero_cuenta") or "").strip()
        subcuenta = str(plantilla.get("subcuenta_banco") or "").strip()
        banco = str(plantilla.get("banco") or "").strip()
        if numero:
            filtro = (
                "(COALESCE(numero_cuenta, '')=? OR "
                "(COALESCE(numero_cuenta, '')='' AND "
                "COALESCE(subcuenta_banco, '')=?))"
            )
            valores_cuenta = (numero, subcuenta)
        elif subcuenta:
            filtro = "COALESCE(subcuenta_banco, '')=?"
            valores_cuenta = (subcuenta,)
        else:
            filtro = "COALESCE(banco, '')=?"
            valores_cuenta = (banco,)
        cur = self.conn.execute(
            f"""
            SELECT fecha, importe, concepto, referencia, saldo, huella,
                   ocurrencia, MIN(id) AS primer_id
            FROM importaciones_bancos_movimientos
            WHERE codigo_empresa=? AND ejercicio=? AND {filtro}
            GROUP BY fecha, importe, concepto, referencia, saldo, huella, ocurrencia
            ORDER BY fecha, primer_id
            """,
            (codigo_empresa, _ej_val(ejercicio), *valores_cuenta),
        )
        return [self._row_to_dict(row) for row in cur.fetchall()]

    def listar_importaciones_banco_solapadas(
        self, codigo_empresa: str, ejercicio: int, plantilla: dict,
        fecha_desde: str, fecha_hasta: str
    ) -> list[dict]:
        numero = str(plantilla.get("numero_cuenta") or "").strip()
        subcuenta = str(plantilla.get("subcuenta_banco") or "").strip()
        banco = str(plantilla.get("banco") or "").strip()
        if numero:
            filtro = (
                "(COALESCE(numero_cuenta, '')=? OR "
                "(COALESCE(numero_cuenta, '')='' AND "
                "COALESCE(subcuenta_banco, '')=?))"
            )
            valores_cuenta = (numero, subcuenta)
        elif subcuenta:
            filtro = "COALESCE(subcuenta_banco, '')=?"
            valores_cuenta = (subcuenta,)
        else:
            filtro = "COALESCE(banco, '')=?"
            valores_cuenta = (banco,)
        cur = self.conn.execute(
            f"""
            SELECT id, fecha_importacion, fecha_primer_asiento,
                   fecha_ultimo_asiento, archivo_origen, estado
            FROM importaciones_bancos
            WHERE codigo_empresa=? AND ejercicio=? AND {filtro}
              AND estado IN ('CORRECTA', 'CON_AVISOS')
              AND fecha_primer_asiento<=? AND fecha_ultimo_asiento>=?
            ORDER BY fecha_importacion DESC, id DESC
            """,
            (
                codigo_empresa, _ej_val(ejercicio), *valores_cuenta,
                fecha_hasta, fecha_desde,
            ),
        )
        return [self._row_to_dict(row) for row in cur.fetchall()]

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
                cuenta_ingreso_por_defecto, cuenta_iva_repercutido_defecto, cuenta_retenciones_irpf,
                excel_json, pct_fraccion)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(codigo_empresa, ejercicio, nombre) DO UPDATE SET
                cuenta_cliente_prefijo=excluded.cuenta_cliente_prefijo,
                cuenta_ingreso_por_defecto=excluded.cuenta_ingreso_por_defecto,
                cuenta_iva_repercutido_defecto=excluded.cuenta_iva_repercutido_defecto,
                cuenta_retenciones_irpf=excluded.cuenta_retenciones_irpf,
                excel_json=excluded.excel_json,
                pct_fraccion=excluded.pct_fraccion
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
                1 if plantilla.get("pct_fraccion") else 0,
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
            f"UPDATE facturas_emitidas_docs SET estado_contable='pendiente' WHERE codigo_empresa=? AND (estado_contable IS NULL OR estado_contable='') AND id IN ({qmarks})",
            (codigo_empresa, *ids),
        )
        self.conn.commit()

    def listar_facturas_emitidas_en_contabilidad(self, codigo_empresa: str, ejercicio: int):
        """Devuelve las facturas emitidas con estado_contable pendiente o generado (todos los ejercicios)."""
        cur = self.conn.execute(
            "SELECT * FROM facturas_emitidas_docs WHERE codigo_empresa=? AND estado_contable IS NOT NULL AND estado_contable != '' ORDER BY fecha_asiento, numero",
            (codigo_empresa,),
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
            f"UPDATE facturas_emitidas_docs SET estado_contable=NULL WHERE codigo_empresa=? AND estado_contable='pendiente' AND id IN ({qmarks})",
            (codigo_empresa, *ids),
        )
        self.conn.commit()
        return cur.rowcount

    def marcar_generadas_con_asiento(self, codigo_empresa: str, ejercicio: int) -> int:
        """Marca como 'generado' todas las facturas en contabilidad con numero_asiento relleno."""
        cur = self.conn.execute(
            """UPDATE facturas_emitidas_docs
               SET estado_contable='generado'
               WHERE codigo_empresa=?
                 AND estado_contable='pendiente'
                 AND numero_asiento IS NOT NULL AND TRIM(numero_asiento) != ''""",
            (codigo_empresa,),
        )
        self.conn.commit()
        return cur.rowcount

    def resetear_facturas_emitidas_generadas(self, codigo_empresa: str, ejercicio: int, ids: list):
        """Revierte el estado 'generado' a 'pendiente' para permitir regenerar el suenlace.

        La factura permanece en el modulo de contabilidad (estado_contable no queda NULL)
        de modo que el usuario puede volver a generar el suenlace sin tener que
        volver a añadirla desde el modulo de facturacion.
        """
        ids = ids or []
        if not ids:
            return 0
        qmarks = ",".join("?" for _ in ids)
        cur = self.conn.execute(
            f"UPDATE facturas_emitidas_docs SET estado_contable='pendiente' WHERE codigo_empresa=? AND estado_contable='generado' AND id IN ({qmarks})",
            (codigo_empresa, *ids),
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

    def listar_control_facturas_global(self, codigos_empresas: list[str]) -> list[dict]:
        """Devuelve una proyeccion comun de facturas emitidas y recibidas.

        La consulta recibe explicitamente las empresas visibles para no exponer
        datos de clientes que no correspondan a la sesion actual. Los filtros de
        interfaz se aplican sobre esta proyeccion, que es pequena y evita
        duplicar la semantica de estados en las vistas.
        """
        codigos = [str(c).strip() for c in (codigos_empresas or []) if str(c).strip()]
        if not codigos:
            return []
        marks = ",".join("?" for _ in codigos)
        sql = f"""
            SELECT
                'emitida' AS tipo, id, codigo_empresa, ejercicio,
                TRIM(COALESCE(serie, '') || COALESCE(numero, '')) AS numero_factura,
                COALESCE(fecha_expedicion, fecha_asiento, '') AS fecha,
                COALESCE(nombre, '') AS tercero, COALESCE(nif, '') AS nif,
                COALESCE(descripcion, '') AS descripcion, estado_contable,
                COALESCE(generada, 0) AS generada, COALESCE(fecha_generacion, '') AS fecha_generacion,
                COALESCE(numero_asiento, '') AS numero_asiento,
                '' AS estado_validacion, '' AS estado_ocr, lineas_json,
                COALESCE(borrador, 0) AS borrador, NULL AS total
            FROM facturas_emitidas_docs
            WHERE codigo_empresa IN ({marks}) AND COALESCE(borrador, 0)=0
            UNION ALL
            SELECT
                'recibida' AS tipo, id, codigo_empresa, ejercicio,
                COALESCE(numero_factura, '') AS numero_factura,
                COALESCE(fecha_factura, fecha_asiento, '') AS fecha,
                COALESCE(proveedor_nombre, '') AS tercero, COALESCE(proveedor_nif, '') AS nif,
                COALESCE(descripcion, '') AS descripcion, estado_contable,
                COALESCE(generada, 0) AS generada, COALESCE(fecha_generacion, '') AS fecha_generacion,
                COALESCE(numero_asiento, '') AS numero_asiento,
                COALESCE(estado_validacion, '') AS estado_validacion,
                COALESCE(estado_ocr, '') AS estado_ocr, NULL AS lineas_json,
                0 AS borrador, total
            FROM facturas_recibidas_docs
            WHERE codigo_empresa IN ({marks})
            ORDER BY fecha DESC, codigo_empresa, numero_factura
        """
        cur = self.conn.execute(sql, tuple(codigos) * 2)
        return [self._row_to_dict(row) for row in cur.fetchall()]

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
             subcuenta_ingreso, subcuenta_iva, subcuenta_retencion, facturae_xml_path, facturae_generated_at, facturae_status, facturae_error,
             updated_at, pdf_generated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                facturae_error=excluded.facturae_error,
                updated_at=excluded.updated_at,
                pdf_generated_at=excluded.pdf_generated_at
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
                self._utc_now(),
                factura.get("pdf_generated_at"),
            ),
        )
        self.conn.commit()
        return fid

    def eliminar_empresa_completa(self, codigo: str) -> int:
        """Elimina una empresa y todos sus ejercicios, verificando el resultado.

        Esta operacion se usa desde el catalogo. A diferencia del borrado por
        ejercicio, limpia tambien los registros que no llevan ejercicio y que
        de otro modo dejaban restos de una empresa eliminada.
        """
        codigo = str(codigo or "").strip().upper()
        if not codigo:
            raise ValueError("Indica el codigo de empresa que se desea eliminar.")

        tablas = (
            ("albaranes_emitidas_docs", "codigo_empresa"),
            ("asientos_contables", "codigo_empresa"),
            ("bancos", "codigo_empresa"),
            ("cert_solicitudes", "codigo_empresa"),
            ("comunicaciones", "codigo_empresa"),
            ("cuentas_bancarias", "codigo_empresa"),
            ("cuotas_periodicas", "codigo_empresa"),
            ("document_scan_run_items", "codigo_empresa"),
            ("facturas_recibidas_ocr", "empresa_id"),
            ("documentos_ocr", "empresa_id"),
            ("documentos_generados", "codigo_empresa"),
            ("documentos", "codigo_empresa"),
            ("duplicate_groups", "codigo_empresa"),
            ("empresa_ccc", "codigo_empresa"),
            ("facturas_emitidas_docs", "codigo_empresa"),
            ("facturas_emitidas", "codigo_empresa"),
            ("facturas_recibidas_docs", "codigo_empresa"),
            ("facturas_recibidas", "codigo_empresa"),
            ("importaciones_bancos_movimientos", "codigo_empresa"),
            ("importaciones_bancos", "codigo_empresa"),
            ("intervinientes", "codigo_empresa"),
            ("lotes_suenlace", "codigo_empresa"),
            ("maestro_subcuentas_empresa", "codigo_empresa"),
            ("notif_bandeja", "codigo_empresa"),
            ("notif_buzones", "codigo_empresa"),
            ("notif_certificados", "codigo_empresa"),
            ("notif_sync_logs", "codigo_empresa"),
            ("notificaciones_config", "codigo_empresa"),
            ("notificaciones", "codigo_empresa"),
            ("operaciones", "codigo_empresa"),
            ("plan_cuentas", "codigo_empresa"),
            ("plantillas_documentos", "codigo_empresa"),
            ("series_emitidas", "codigo_empresa"),
            ("terceros_empresas", "codigo_empresa"),
            ("usuarios_empresas", "empresa_codigo"),
        )
        filas_tablas = self.conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema=current_schema()"
        ).fetchall()
        existentes = {
            str(fila["table_name"] or "").lower()
            for fila in filas_tablas
        }
        eliminadas = 0
        try:
            for tabla, columna in tablas:
                if tabla.lower() not in existentes:
                    continue
                cur = self.conn.execute(
                    f"DELETE FROM {tabla} WHERE {columna}=?", (codigo,)
                )
                eliminadas += max(0, int(cur.rowcount or 0))
            cur = self.conn.execute("DELETE FROM empresas WHERE codigo=?", (codigo,))
            eliminadas += max(0, int(cur.rowcount or 0))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

        if self.conn.execute(
            "SELECT 1 FROM empresas WHERE codigo=? LIMIT 1", (codigo,)
        ).fetchone():
            raise RuntimeError(f"No se ha podido confirmar el borrado de la empresa {codigo}.")
        return eliminadas

    def actualizar_numero_asiento_factura_emitida(
        self,
        codigo_empresa: str,
        factura_id: str,
        numero_asiento: str,
    ) -> bool:
        """Actualiza solo el asiento capturado desde A3ECO.

        Evita regrabar la factura completa al refrescar este dato tras la
        importacion, especialmente importante con el adaptador PostgreSQL.
        """
        cur = self.conn.execute(
            "UPDATE facturas_emitidas_docs SET numero_asiento=? "
            "WHERE id=? AND codigo_empresa=?",
            (str(numero_asiento or "").strip(), str(factura_id), str(codigo_empresa)),
        )
        self.conn.commit()
        return bool(cur.rowcount)

    def eliminar_factura_emitida(self, codigo_empresa: str, factura_id: str, ejercicio: int):
        ejercicio_key = _ej_val(ejercicio)
        try:
            # Una factura creada desde albaranes deja de bloquearlos al borrarse.
            # Ambas operaciones forman una sola transaccion para no dejar enlaces
            # huerfanos si falla la eliminacion de la factura.
            self.conn.execute(
                "UPDATE albaranes_emitidas_docs "
                "SET facturado=0, factura_id=NULL, fecha_facturacion=NULL "
                "WHERE codigo_empresa=? AND ejercicio=? AND factura_id=?",
                (codigo_empresa, ejercicio_key, factura_id),
            )
            self.conn.execute(
                "DELETE FROM facturas_emitidas_docs WHERE codigo_empresa=? AND ejercicio=? AND id=?",
                (codigo_empresa, ejercicio_key, factura_id),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def marcar_facturas_emitidas_generadas(self, codigo_empresa: str, ids: list, fecha: str, ejercicio: int):
        ids = ids or []
        if not ids:
            return
        qmarks = ",".join("?" for _ in ids)
        self.conn.execute(
            f"UPDATE facturas_emitidas_docs SET generada=1, fecha_generacion=? WHERE codigo_empresa=? AND id IN ({qmarks})",
            (fecha, codigo_empresa, *ids),
        )
        self.conn.execute(
            f"UPDATE facturas_emitidas_docs SET estado_contable='generado' WHERE codigo_empresa=? AND estado_contable='pendiente' AND id IN ({qmarks})",
            (codigo_empresa, *ids),
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
             tipo_operacion, plantilla_emitidas, plantilla_word, lineas_json, updated_at, pdf_generated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                lineas_json=excluded.lineas_json,
                updated_at=excluded.updated_at,
                pdf_generated_at=excluded.pdf_generated_at
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
                self._utc_now(),
                albaran.get("pdf_generated_at"),
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
                cuenta_gasto_por_defecto, cuenta_iva_soportado_defecto, excel_json, pct_fraccion)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(codigo_empresa, ejercicio, nombre) DO UPDATE SET
                cuenta_proveedor_prefijo=excluded.cuenta_proveedor_prefijo,
                cuenta_gasto_por_defecto=excluded.cuenta_gasto_por_defecto,
                cuenta_iva_soportado_defecto=excluded.cuenta_iva_soportado_defecto,
                excel_json=excluded.excel_json,
                pct_fraccion=excluded.pct_fraccion
            """,
            (
                plantilla.get("codigo_empresa"),
                eje,
                plantilla.get("nombre"),
                plantilla.get("cuenta_proveedor_prefijo"),
                plantilla.get("cuenta_gasto_por_defecto"),
                plantilla.get("cuenta_iva_soportado_defecto"),
                json.dumps(plantilla.get("excel", {}), ensure_ascii=False),
                1 if plantilla.get("pct_fraccion") else 0,
            ),
        )
        self.conn.commit()

    def eliminar_recibida(self, codigo_empresa: str, nombre: str, ejercicio: int):
        self.conn.execute(
            "DELETE FROM facturas_recibidas WHERE codigo_empresa=? AND ejercicio=? AND nombre=?",
            (codigo_empresa, _ej_val(ejercicio), nombre),
        )
        self.conn.commit()

    # ---------- GESTION DOCUMENTAL ----------
    def listar_categorias_documentales(self, solo_activas: bool = True) -> list[dict]:
        where = "WHERE activa=1" if solo_activas else ""
        rows = self.conn.execute(
            f"SELECT * FROM categorias_documentales {where} ORDER BY orden,nombre"
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def listar_documentos_archivo(
        self, codigo_empresa: str, ejercicio: int | None = None,
        categoria_id: str = "",
    ) -> list[dict]:
        self.reconciliar_documentos_archivo_ocr(codigo_empresa)
        clauses = ["d.codigo_empresa=?"]
        params: list = [codigo_empresa]
        if ejercicio is not None:
            clauses.append("d.ejercicio=?")
            params.append(int(ejercicio))
        if categoria_id:
            clauses.append("d.categoria_id=?")
            params.append(categoria_id)
        rows = self.conn.execute(
            "SELECT d.*,c.nombre AS categoria_nombre,c.permite_ocr "
            "FROM documentos_archivo d "
            "JOIN categorias_documentales c ON c.id=d.categoria_id WHERE "
            + " AND ".join(clauses)
            + " ORDER BY d.created_at DESC,d.nombre_original",
            tuple(params),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def reconciliar_documentos_archivo_ocr(self, codigo_empresa: str) -> int:
        """Libera vinculos OCR cuyo documento de trabajo ya fue eliminado."""
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        cursor = self.conn.execute(
            "UPDATE documentos_archivo SET ocr_documento_id=NULL,"
            "estado='archivado',updated_at=? "
            "WHERE codigo_empresa=? AND ocr_documento_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM documentos_ocr o "
            "WHERE o.id=documentos_archivo.ocr_documento_id)",
            (now, codigo_empresa),
        )
        self.conn.commit()
        return max(0, int(cursor.rowcount or 0))

    def get_documento_archivo(self, documento_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT d.*,c.nombre AS categoria_nombre,c.permite_ocr "
            "FROM documentos_archivo d JOIN categorias_documentales c "
            "ON c.id=d.categoria_id WHERE d.id=?", (documento_id,),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def registrar_documento_archivo(self, datos: dict) -> str:
        documento_id = str(datos.get("id") or uuid.uuid4())
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        self.conn.execute(
            """
            INSERT INTO documentos_archivo
              (id,codigo_empresa,ejercicio,categoria_id,nombre_original,
               nombre_archivo,ruta,hash_archivo,tamano,mime_type,origen,
               comunicacion_id,mensaje_id,graph_message_id,graph_attachment_id,
               correo_remitente,correo_asunto,estado,ocr_documento_id,
               creado_por,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                documento_id, datos["codigo_empresa"], int(datos["ejercicio"]),
                datos["categoria_id"], datos["nombre_original"],
                datos["nombre_archivo"], datos["ruta"], datos["hash_archivo"],
                datos.get("tamano"), datos.get("mime_type"),
                datos.get("origen") or "correo", datos.get("comunicacion_id"),
                datos.get("mensaje_id"), datos.get("graph_message_id"),
                datos.get("graph_attachment_id"), datos.get("correo_remitente"),
                datos.get("correo_asunto"), datos.get("estado") or "archivado",
                datos.get("ocr_documento_id"), datos.get("creado_por"), now, now,
            ),
        )
        self.conn.commit()
        return documento_id

    def registrar_decision_adjunto(self, datos: dict) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        self.conn.execute(
            """
            INSERT INTO comunicaciones_adjuntos_decisiones
              (graph_message_id,graph_attachment_id,nombre,accion,categoria_id,
               documento_id,created_at) VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(graph_message_id,graph_attachment_id) DO UPDATE SET
              nombre=excluded.nombre,accion=excluded.accion,
              categoria_id=excluded.categoria_id,documento_id=excluded.documento_id,
              created_at=excluded.created_at
            """,
            (
                datos["graph_message_id"], datos["graph_attachment_id"],
                datos.get("nombre"), datos["accion"], datos.get("categoria_id"),
                datos.get("documento_id"), now,
            ),
        )
        self.conn.commit()

    def vincular_documento_archivo_ocr(self, documento_id: str, ocr_documento_id: str) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE documentos_archivo SET ocr_documento_id=?,estado='en_ocr',"
            "updated_at=? WHERE id=?", (ocr_documento_id, now, documento_id),
        )
        self.conn.commit()

    def eliminar_documento_archivo(self, documento_id: str) -> dict | None:
        documento = self.get_documento_archivo(documento_id)
        if not documento:
            return None
        self.conn.execute(
            "UPDATE comunicaciones_adjuntos_decisiones SET documento_id=NULL "
            "WHERE documento_id=?", (documento_id,),
        )
        self.conn.execute("DELETE FROM documentos_archivo WHERE id=?", (documento_id,))
        self.conn.commit()
        return documento

    # ---------- FIRMA ELECTRONICA ----------
    def crear_firma_solicitud(self, datos: dict, firmantes: list[dict], zonas: list[dict]) -> str:
        solicitud_id = str(datos["id"])
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        self.conn.execute(
            """INSERT INTO firma_solicitudes
            (id,codigo_empresa,ejercicio,origen,documento_archivo_id,nombre_documento,
             ruta_origen,ruta_envio,hash_origen,proveedor,external_id,asunto,mensaje,usar_sms,
             estado,creado_por,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (solicitud_id, datos["codigo_empresa"], int(datos["ejercicio"]),
             datos.get("origen") or "archivo", datos.get("documento_archivo_id"),
             datos["nombre_documento"], datos["ruta_origen"], datos.get("ruta_envio"),
             datos["hash_origen"], datos.get("proveedor") or "signrequest",
             datos.get("external_id"), datos.get("asunto"), datos.get("mensaje"),
             1 if datos.get("usar_sms") else 0, datos.get("estado") or "borrador",
             datos.get("creado_por"), now, now),
        )
        for firmante in firmantes:
            self.conn.execute(
                """INSERT INTO firma_firmantes
                (solicitud_id,orden,nombre,email,telefono,tercero_id,es_remitente)
                VALUES (?,?,?,?,?,?,?)""",
                (solicitud_id, int(firmante["orden"]), firmante.get("nombre"),
                 firmante["email"], firmante.get("telefono"), firmante.get("tercero_id"),
                 1 if firmante.get("es_remitente") else 0),
            )
        for zona in zonas:
            self.conn.execute(
                """INSERT INTO firma_zonas
                (solicitud_id,pagina,x,y,ancho,alto,firmante) VALUES (?,?,?,?,?,?,?)""",
                (solicitud_id, int(zona["pagina"]), float(zona["x"]), float(zona["y"]),
                 float(zona["ancho"]), float(zona["alto"]), int(zona["firmante"])),
            )
        self.conn.commit()
        return solicitud_id

    def get_firma_solicitud(self, solicitud_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM firma_solicitudes WHERE id=?", (str(solicitud_id),)
        ).fetchone()
        if not row:
            return None
        result = self._row_to_dict(row)
        result["firmantes"] = [self._row_to_dict(item) for item in self.conn.execute(
            "SELECT * FROM firma_firmantes WHERE solicitud_id=? ORDER BY orden,id",
            (str(solicitud_id),),
        ).fetchall()]
        result["zonas"] = [self._row_to_dict(item) for item in self.conn.execute(
            "SELECT * FROM firma_zonas WHERE solicitud_id=? ORDER BY pagina,id",
            (str(solicitud_id),),
        ).fetchall()]
        return result

    def listar_firma_solicitudes(self, codigo_empresa: str, ejercicio: int,
                                 estado: str = "", texto: str = "") -> list[dict]:
        clauses = ["codigo_empresa=?", "ejercicio=?"]
        params: list = [str(codigo_empresa), int(ejercicio)]
        if estado:
            clauses.append("estado=?")
            params.append(str(estado))
        if texto:
            clauses.append("(nombre_documento LIKE ? OR asunto LIKE ?)")
            params.extend([f"%{texto}%", f"%{texto}%"])
        rows = self.conn.execute(
            "SELECT * FROM firma_solicitudes WHERE " + " AND ".join(clauses)
            + " ORDER BY created_at DESC", tuple(params),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def listar_todas_firma_solicitudes(self, estado: str = "", texto: str = "") -> list[dict]:
        clauses = ["1=1"]
        params: list = []
        if estado:
            clauses.append("estado=?")
            params.append(str(estado))
        if texto:
            clauses.append("(nombre_documento LIKE ? OR asunto LIKE ? OR codigo_empresa LIKE ?)")
            params.extend([f"%{texto}%", f"%{texto}%", f"%{texto}%"])
        rows = self.conn.execute(
            "SELECT * FROM firma_solicitudes WHERE " + " AND ".join(clauses)
            + " ORDER BY created_at DESC", tuple(params),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def actualizar_firma_solicitud(self, solicitud_id: str, cambios: dict) -> None:
        permitidos = {
            "ruta_envio", "request_id", "estado", "ruta_firmado", "ruta_registro_firma",
            "asunto", "mensaje",
            "sha256_firmado", "sha256_registro_firma", "security_hash",
            "signing_log_security_hash", "documento_firmado_archivo_id",
            "enviado_at", "firmado_at", "request_id", "ruta_firmado",
            "ruta_registro_firma", "sha256_firmado", "sha256_registro_firma",
        }
        cambios = {key: value for key, value in cambios.items() if key in permitidos}
        if not cambios:
            return
        cambios["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        setters = ",".join(f"{key}=?" for key in cambios)
        self.conn.execute(
            f"UPDATE firma_solicitudes SET {setters} WHERE id=?",
            (*cambios.values(), str(solicitud_id)),
        )
        self.conn.commit()

    def actualizar_firma_participantes(self, solicitud_id: str,
                                       firmantes: list[dict], zonas: list[dict]) -> None:
        solicitud_id = str(solicitud_id)
        self.conn.execute("DELETE FROM firma_firmantes WHERE solicitud_id=?", (solicitud_id,))
        self.conn.execute("DELETE FROM firma_zonas WHERE solicitud_id=?", (solicitud_id,))
        for firmante in firmantes:
            self.conn.execute(
                """INSERT INTO firma_firmantes
                (solicitud_id,orden,nombre,email,telefono,tercero_id,es_remitente)
                VALUES (?,?,?,?,?,?,?)""",
                (solicitud_id, int(firmante["orden"]), firmante.get("nombre"),
                 firmante["email"], firmante.get("telefono"),
                 firmante.get("tercero_id"), 1 if firmante.get("es_remitente") else 0),
            )
        for zona in zonas:
            self.conn.execute(
                """INSERT INTO firma_zonas
                (solicitud_id,pagina,x,y,ancho,alto,firmante) VALUES (?,?,?,?,?,?,?)""",
                (solicitud_id, int(zona["pagina"]), float(zona["x"]), float(zona["y"]),
                 float(zona["ancho"]), float(zona["alto"]), int(zona["firmante"])),
            )
        self.conn.commit()

    def eliminar_firma_solicitud(self, solicitud_id: str) -> None:
        solicitud_id = str(solicitud_id)
        self.conn.execute("DELETE FROM firma_eventos WHERE solicitud_id=?", (solicitud_id,))
        self.conn.execute("DELETE FROM firma_firmantes WHERE solicitud_id=?", (solicitud_id,))
        self.conn.execute("DELETE FROM firma_zonas WHERE solicitud_id=?", (solicitud_id,))
        self.conn.execute("DELETE FROM firma_solicitudes WHERE id=?", (solicitud_id,))
        self.conn.commit()

    def registrar_firma_evento(self, solicitud_id: str, tipo: str,
                               detalle_json: str = "", usuario: str = "") -> None:
        self.conn.execute(
            "INSERT INTO firma_eventos(solicitud_id,tipo,detalle_json,usuario,created_at) "
            "VALUES (?,?,?,?,?)",
            (str(solicitud_id), str(tipo), detalle_json, usuario,
             datetime.now().astimezone().isoformat(timespec="seconds")),
        )
        self.conn.commit()

    def listar_firma_eventos(self, solicitud_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM firma_eventos WHERE solicitud_id=? ORDER BY created_at,id",
            (str(solicitud_id),),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def upsert_adjunto_mensajeria_entrada(self, datos: dict) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        self.conn.execute(
            """
            INSERT INTO mensajeria_adjuntos_entrada
              (id,mensaje_remoto_id,conversacion_remota_id,codigo_empresa,
               empresa_nombre,nombre_original,ruta_entrada,hash_archivo,tamano,
               mime_type,remitente,estado,error_detalle,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              ruta_entrada=excluded.ruta_entrada,hash_archivo=excluded.hash_archivo,
              tamano=excluded.tamano,mime_type=excluded.mime_type,
              estado=excluded.estado,error_detalle=excluded.error_detalle,
              updated_at=excluded.updated_at
            """,
            (
                datos["id"], datos["mensaje_remoto_id"],
                datos["conversacion_remota_id"], datos["codigo_empresa"],
                datos.get("empresa_nombre"), datos["nombre_original"],
                datos["ruta_entrada"], datos["hash_archivo"],
                datos.get("tamano"), datos.get("mime_type"),
                datos.get("remitente"), datos.get("estado") or "pendiente_clasificar",
                datos.get("error_detalle"), now, now,
            ),
        )
        self.conn.commit()

    def get_adjunto_mensajeria_entrada(self, adjunto_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM mensajeria_adjuntos_entrada WHERE id=?", (adjunto_id,),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def listar_adjuntos_mensajeria_entrada(self, estado: str = "pendiente_clasificar") -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM mensajeria_adjuntos_entrada WHERE estado=? "
            "ORDER BY created_at", (estado,),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def actualizar_adjunto_mensajeria_entrada(
        self, adjunto_id: str, estado: str, *, documento_id: str | None = None,
        error_detalle: str = "",
    ) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE mensajeria_adjuntos_entrada SET estado=?,documento_id=?,"
            "error_detalle=?,updated_at=? WHERE id=?",
            (estado, documento_id, error_detalle or None, now, adjunto_id),
        )
        self.conn.commit()

    # ---------- PLANTILLAS DE FIRMA ----------
    def guardar_plantilla_firma(self, plantilla: dict) -> str:
        plantilla_id = str(plantilla.get("id") or uuid.uuid4())
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        existe = self.conn.execute(
            "SELECT id,version,hash_docx,created_at FROM plantillas_firma WHERE id=?",
            (plantilla_id,),
        ).fetchone()
        version = int(plantilla.get("version") or (existe["version"] if existe else 1))
        if existe and str(existe.get("hash_docx") or "") != str(plantilla.get("hash_docx") or ""):
            version = max(version, int(existe["version"]) + 1)
        valores = (
            plantilla.get("nombre"), plantilla.get("descripcion"),
            plantilla.get("archivo_relativo"), plantilla.get("alcance") or "global",
            version, plantilla.get("hash_docx") or "", plantilla.get("asunto"),
            plantilla.get("mensaje"), 1 if plantilla.get("activa") else 0,
            1 if plantilla.get("zonas_revisadas") else 0,
            plantilla.get("creado_por"), now,
        )
        if existe:
            self.conn.execute(
                """UPDATE plantillas_firma SET nombre=?,descripcion=?,archivo_relativo=?,
                alcance=?,version=?,hash_docx=?,asunto=?,mensaje=?,activa=?,zonas_revisadas=?,
                creado_por=COALESCE(creado_por,?),updated_at=? WHERE id=?""",
                (*valores, plantilla_id),
            )
        else:
            self.conn.execute(
                """INSERT INTO plantillas_firma
                (id,nombre,descripcion,archivo_relativo,alcance,version,hash_docx,asunto,mensaje,
                 activa,zonas_revisadas,creado_por,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (plantilla_id, *valores[:-1], now, now),
            )
        for tabla in (
            "plantillas_firma_empresas", "plantillas_firma_campos",
            "plantillas_firma_firmantes", "plantillas_firma_zonas",
        ):
            self.conn.execute(f"DELETE FROM {tabla} WHERE plantilla_id=?", (plantilla_id,))
        for codigo in plantilla.get("empresas") or []:
            self.conn.execute(
                "INSERT INTO plantillas_firma_empresas(plantilla_id,codigo_empresa) VALUES (?,?)",
                (plantilla_id, str(codigo)),
            )
        for pos, campo in enumerate(plantilla.get("campos") or []):
            self.conn.execute(
                """INSERT INTO plantillas_firma_campos
                (plantilla_id,clave,etiqueta,origen,campo_origen,tipo,obligatorio,valor_defecto,orden)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (plantilla_id, campo["clave"], campo.get("etiqueta") or campo["clave"],
                 campo.get("origen") or "manual", campo.get("campo_origen"),
                 campo.get("tipo") or "texto", 1 if campo.get("obligatorio") else 0,
                 campo.get("valor_defecto"), int(campo.get("orden", pos))),
            )
        for pos, firmante in enumerate(plantilla.get("firmantes") or []):
            self.conn.execute(
                """INSERT INTO plantillas_firma_firmantes
                (plantilla_id,rol,origen,nombre,email,telefono,orden,usar_sms)
                VALUES (?,?,?,?,?,?,?,?)""",
                (plantilla_id, firmante.get("rol") or f"Firmante {pos + 1}",
                 firmante.get("origen") or "manual", firmante.get("nombre"),
                 firmante.get("email"), firmante.get("telefono"),
                 int(firmante.get("orden") or pos + 1),
                 1 if firmante.get("usar_sms") else 0),
            )
        for zona in plantilla.get("zonas") or []:
            self.conn.execute(
                """INSERT INTO plantillas_firma_zonas
                (plantilla_id,rol,pagina,x,y,ancho,alto) VALUES (?,?,?,?,?,?,?)""",
                (plantilla_id, zona["rol"], int(zona["pagina"]), float(zona["x"]),
                 float(zona["y"]), float(zona["ancho"]), float(zona["alto"])),
            )
        self.conn.commit()
        return plantilla_id

    def get_plantilla_firma(self, plantilla_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM plantillas_firma WHERE id=?", (str(plantilla_id),)).fetchone()
        if not row:
            return None
        item = self._row_to_dict(row)
        item["empresas"] = [r["codigo_empresa"] for r in self.conn.execute(
            "SELECT codigo_empresa FROM plantillas_firma_empresas WHERE plantilla_id=? ORDER BY codigo_empresa",
            (str(plantilla_id),),
        ).fetchall()]
        for key, tabla, order in (
            ("campos", "plantillas_firma_campos", "orden,id"),
            ("firmantes", "plantillas_firma_firmantes", "orden,id"),
            ("zonas", "plantillas_firma_zonas", "pagina,id"),
        ):
            item[key] = [self._row_to_dict(r) for r in self.conn.execute(
                f"SELECT * FROM {tabla} WHERE plantilla_id=? ORDER BY {order}",
                (str(plantilla_id),),
            ).fetchall()]
        return item

    def listar_plantillas_firma(self, codigo_empresa: str = "", incluir_inactivas: bool = False) -> list[dict]:
        clauses = ["1=1"]
        params: list = []
        if not incluir_inactivas:
            clauses.append("p.activa=1")
        if codigo_empresa:
            clauses.append("(p.alcance='global' OR EXISTS (SELECT 1 FROM plantillas_firma_empresas pe WHERE pe.plantilla_id=p.id AND pe.codigo_empresa=?))")
            params.append(str(codigo_empresa))
        elif not incluir_inactivas:
            clauses.append("p.alcance='global'")
        rows = self.conn.execute(
            "SELECT p.* FROM plantillas_firma p WHERE " + " AND ".join(clauses) + " ORDER BY LOWER(p.nombre)",
            tuple(params),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def eliminar_plantilla_firma(self, plantilla_id: str) -> None:
        usados = self.conn.execute(
            "SELECT 1 FROM documentos_firma_generados WHERE plantilla_id=? LIMIT 1", (str(plantilla_id),)
        ).fetchone()
        if usados:
            self.conn.execute("UPDATE plantillas_firma SET activa=0 WHERE id=?", (str(plantilla_id),))
        else:
            self.conn.execute("DELETE FROM plantillas_firma WHERE id=?", (str(plantilla_id),))
        self.conn.commit()

    def guardar_documento_firma_generado(self, documento: dict) -> str:
        documento_id = str(documento.get("id") or uuid.uuid4())
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        self.conn.execute(
            """INSERT INTO documentos_firma_generados
            (id,plantilla_id,plantilla_version,plantilla_hash,codigo_empresa,tercero_id,titulo,
             datos_json,firmantes_json,ruta_docx,ruta_pdf,hash_docx,hash_pdf,estado,solicitud_id,
             creado_por,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (documento_id, documento["plantilla_id"], int(documento["plantilla_version"]),
             documento["plantilla_hash"], documento.get("codigo_empresa"), documento.get("tercero_id"),
             documento["titulo"], json.dumps(documento.get("datos") or {}, ensure_ascii=False),
             json.dumps(documento.get("firmantes") or [], ensure_ascii=False), documento["ruta_docx"],
             documento["ruta_pdf"], documento.get("hash_docx"), documento.get("hash_pdf"),
             documento.get("estado") or "borrador", documento.get("solicitud_id"),
             documento.get("creado_por"), now, now),
        )
        self.conn.commit()
        return documento_id

    def vincular_documento_firma_solicitud(self, documento_id: str, solicitud_id: str) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE documentos_firma_generados SET solicitud_id=?,estado='enviado',updated_at=? WHERE id=?",
            (str(solicitud_id), now, str(documento_id)),
        )
        self.conn.commit()

    def get_documento_firma_generado(self, documento_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM documentos_firma_generados WHERE id=?", (str(documento_id),)
        ).fetchone()
        if not row:
            return None
        item = self._row_to_dict(row)
        item["datos"] = json.loads(item.pop("datos_json") or "{}")
        item["firmantes"] = json.loads(item.pop("firmantes_json") or "[]")
        return item

    def actualizar_documento_firma_generado(self, documento_id: str, cambios: dict) -> None:
        permitidos = {"ruta_docx", "ruta_pdf", "hash_docx", "hash_pdf", "estado", "solicitud_id"}
        cambios = {key: value for key, value in cambios.items() if key in permitidos}
        if not cambios:
            return
        cambios["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE documentos_firma_generados SET "
            + ",".join(f"{key}=?" for key in cambios) + " WHERE id=?",
            (*cambios.values(), str(documento_id)),
        )
        self.conn.commit()

    def devolver_facturas_recibidas_a_documentacion(
        self, codigo_empresa: str, ejercicio: int | None = None,
        incluir_contabilizadas: bool = False,
    ) -> dict:
        """Archiva y retira del circuito OCR facturas aun no contabilizadas.

        Se recuperan cargas del flujo OCR anterior sin borrar ni mover el PDF
        original: se conserva su ruta y se crea la ficha en Gestion documental.
        Las facturas ya enlazadas o contabilizadas se excluyen expresamente,
        salvo que se solicite de forma expresa para depurar pruebas.
        """
        categoria = self.conn.execute(
            "SELECT id FROM categorias_documentales "
            "WHERE carpeta='FACTURAS_RECIBIDAS' AND activa=1 LIMIT 1"
        ).fetchone()
        if not categoria:
            raise ValueError("No existe la categoria documental Facturas recibidas.")
        clauses = ["codigo_empresa=?"]
        if not incluir_contabilizadas:
            clauses.extend([
                "COALESCE(generada, 0)=0",
                "COALESCE(estado_contable, '') IN ('', 'pendiente_contabilizar')",
            ])
        params: list = [str(codigo_empresa)]
        if ejercicio is not None:
            clauses.append("ejercicio=?")
            params.append(int(ejercicio))
        rows = self.conn.execute(
            "SELECT * FROM facturas_recibidas_docs WHERE " + " AND ".join(clauses),
            tuple(params),
        ).fetchall()
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        archivadas = omitidas = 0
        for raw in rows:
            doc = self._row_to_dict(raw)
            ruta = str(doc.get("pdf_path") or doc.get("origen_path") or "").strip()
            if not ruta:
                omitidas += 1
                continue
            existente = self.conn.execute(
                "SELECT id FROM documentos_archivo WHERE codigo_empresa=? AND ruta=? LIMIT 1",
                (str(codigo_empresa), ruta),
            ).fetchone()
            if not existente:
                nombre = Path(ruta).name or str(doc.get("numero_factura") or "Factura recibida")
                self.conn.execute(
                    """INSERT INTO documentos_archivo
                       (id,codigo_empresa,ejercicio,categoria_id,nombre_original,nombre_archivo,
                        ruta,hash_archivo,tamano,mime_type,origen,estado,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        str(uuid.uuid4()), str(codigo_empresa), int(doc.get("ejercicio") or 0),
                        categoria["id"], nombre, nombre, ruta,
                        f"recuperado-ocr:{doc.get('id')}", None, "application/pdf",
                        "recuperacion_ocr", "archivado", now, now,
                    ),
                )
            self.conn.execute("DELETE FROM facturas_recibidas_docs WHERE id=?", (str(doc["id"]),))
            archivadas += 1
        self.conn.commit()
        return {"archivadas": archivadas, "omitidas_sin_ruta": omitidas}

    def vincular_documentos_graph_comunicacion(self, graph_message_id: str) -> None:
        row = self.conn.execute(
            "SELECT id,comunicacion_id FROM comunicaciones_mensajes "
            "WHERE graph_message_id=? LIMIT 1", (graph_message_id,),
        ).fetchone()
        if not row:
            return
        self.conn.execute(
            "UPDATE documentos_archivo SET comunicacion_id=?,mensaje_id=? "
            "WHERE graph_message_id=?",
            (row["comunicacion_id"], row["id"], graph_message_id),
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

    def actualizar_numero_asiento_factura_recibida(
        self, codigo_empresa: str, documento_id: str, numero_asiento: str,
    ) -> bool:
        """Guarda el asiento recuperado de A3 en factura y asiento propuesto."""
        now = self._utc_now()
        numero = str(numero_asiento or "").strip()
        cursor = self.conn.execute(
            "UPDATE facturas_recibidas_docs SET numero_asiento=?,updated_at=? "
            "WHERE id=? AND codigo_empresa=?",
            (numero, now, str(documento_id), str(codigo_empresa)),
        )
        self.conn.execute(
            "UPDATE asientos_contables SET numero_asiento=?,updated_at=? "
            "WHERE documento_id=? AND codigo_empresa=?",
            (numero, now, str(documento_id), str(codigo_empresa)),
        )
        self.conn.commit()
        return bool(cursor.rowcount)

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
        except Exception:
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
        except Exception:
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

    def listar_permisos_globales_usuario(self, user_id: int) -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM usuarios_permisos_globales WHERE usuario_id=? ORDER BY permiso",
            (int(user_id),),
        )
        return [self._row_to_dict(row) for row in cur.fetchall()]

    def upsert_permiso_global_usuario(self, user_id: int, permiso: str, activo: bool = True) -> None:
        now = self._utc_now()
        self.conn.execute(
            """
            INSERT INTO usuarios_permisos_globales (usuario_id, permiso, activo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(usuario_id, permiso) DO UPDATE SET
              activo=excluded.activo,
              updated_at=excluded.updated_at
            """,
            (int(user_id), str(permiso or "").strip(), 1 if activo else 0, now, now),
        )
        self.conn.commit()

    # ---------- VINCULO CONTABLE TRAMITES DGT ----------
    def get_dgt_factura(self, expediente_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM dgt_facturas WHERE expediente_id=?",
            (str(expediente_id),),
        ).fetchone()
        return self._row_to_dict(row)

    def upsert_dgt_factura(self, datos: dict) -> None:
        now = self._utc_now()
        self.conn.execute(
            """
            INSERT INTO dgt_facturas
              (expediente_id, factura_id, codigo_empresa, ejercicio, destinatario,
               honorarios, tasa_dgt, impuesto_620, otros_suplidos, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(expediente_id) DO UPDATE SET
              factura_id=excluded.factura_id,
              codigo_empresa=excluded.codigo_empresa,
              ejercicio=excluded.ejercicio,
              destinatario=excluded.destinatario,
              honorarios=excluded.honorarios,
              tasa_dgt=excluded.tasa_dgt,
              impuesto_620=excluded.impuesto_620,
              otros_suplidos=excluded.otros_suplidos,
              updated_at=excluded.updated_at
            """,
            (
                str(datos.get("expediente_id") or ""),
                str(datos.get("factura_id") or ""),
                str(datos.get("codigo_empresa") or ""),
                int(datos.get("ejercicio") or 0),
                str(datos.get("destinatario") or ""),
                float(datos.get("honorarios") or 0),
                float(datos.get("tasa_dgt") or 0),
                float(datos.get("impuesto_620") or 0),
                float(datos.get("otros_suplidos") or 0),
                datos.get("created_at") or now,
                now,
            ),
        )
        self.conn.commit()

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

    def marcar_subcuenta_enlazada_a3_por_cuenta(
        self, codigo_empresa: str, subcuenta: str, observaciones: str = "", lote: str | None = None
    ) -> None:
        now = self._utc_now()
        self.conn.execute(
            """UPDATE maestro_subcuentas_empresa
               SET pendiente_alta_a3=0, fecha_alta_a3=?, lote_alta_a3=?,
                   observaciones=?, updated_at=?
               WHERE codigo_empresa=? AND subcuenta=?""",
            (now, lote, observaciones or None, now, str(codigo_empresa), str(subcuenta)),
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

    def eliminar_documento_ocr(self, doc_id: str) -> bool:
        """Elimina el trabajo OCR y devuelve su documento de archivo a archivado."""
        documento = self.get_documento_ocr(doc_id)
        if not documento:
            return False
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE documentos_archivo SET ocr_documento_id=NULL,"
            "estado='archivado',updated_at=? WHERE ocr_documento_id=?",
            (now, str(doc_id)),
        )
        self.conn.execute(
            "DELETE FROM facturas_recibidas_ocr WHERE documento_id=?", (str(doc_id),)
        )
        self.conn.execute("DELETE FROM documentos_ocr WHERE id=?", (str(doc_id),))
        self.conn.commit()
        return True

    # facturas_recibidas_ocr ──────────────────────────────────────────────────

    def upsert_factura_recibida_ocr(self, factura: dict) -> str:
        """Inserta o actualiza una factura recibida OCR. Devuelve el id."""
        self.conn.execute(
            """
            INSERT INTO facturas_recibidas_ocr
              (id, documento_id, empresa_id, proveedor_id, nif_proveedor,
               nombre_proveedor, numero_factura, fecha_factura, fecha_operacion,
               fecha_vencimiento, total_factura, base_total, iva_total,
               retencion_total, tipo_operacion_iva, estado_validacion, observaciones)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
              tipo_operacion_iva=excluded.tipo_operacion_iva,
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
                factura.get("tipo_operacion_iva") or "INTERIOR_DEDUCIBLE",
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

    # ocr_aprendizaje_ejemplos -------------------------------------------------

    def upsert_ejemplo_aprendizaje_ocr(self, ejemplo: dict) -> int:
        """Guarda la version validada de una factura para futuro entrenamiento.

        El PDF no se copia ni se envia a ningun proveedor desde aqui. La cola
        local separa la validacion humana de la exportacion/reentrenamiento.
        """
        cur = self.conn.execute(
            """
            INSERT INTO ocr_aprendizaje_ejemplos
              (empresa_id, documento_id, factura_id, proveedor_nif, origen_path,
               datos_validados_json, estado, modelo_destino, fecha_validacion,
               fecha_exportacion, notas, marcas_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(factura_id) DO UPDATE SET
              proveedor_nif=excluded.proveedor_nif,
              origen_path=excluded.origen_path,
              datos_validados_json=excluded.datos_validados_json,
              estado=excluded.estado,
              modelo_destino=excluded.modelo_destino,
              fecha_validacion=excluded.fecha_validacion,
              fecha_exportacion='',
              notas=excluded.notas,
              marcas_json=excluded.marcas_json
            """,
            (
                str(ejemplo["empresa_id"]), str(ejemplo["documento_id"]),
                str(ejemplo["factura_id"]), ejemplo.get("proveedor_nif", ""),
                ejemplo.get("origen_path", ""), ejemplo["datos_validados_json"],
                ejemplo.get("estado", "pendiente"), ejemplo.get("modelo_destino", ""),
                ejemplo["fecha_validacion"], ejemplo.get("fecha_exportacion", ""),
                ejemplo.get("notas", ""), ejemplo.get("marcas_json", "{}"),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_ejemplo_aprendizaje_ocr(self, factura_id: str) -> dict | None:
        cur = self.conn.execute(
            "SELECT * FROM ocr_aprendizaje_ejemplos WHERE factura_id=?",
            (str(factura_id),),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def listar_ejemplos_aprendizaje_ocr(self, empresa_id: str, estado: str = "pendiente") -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM ocr_aprendizaje_ejemplos WHERE empresa_id=? AND estado=? ORDER BY id",
            (str(empresa_id), str(estado)),
        )
        return [dict(row) for row in cur.fetchall()]

    def resumen_aprendizaje_ocr(self, empresa_id: str) -> dict:
        cur = self.conn.execute(
            """
            SELECT estado, proveedor_nif, COUNT(*) AS total
            FROM ocr_aprendizaje_ejemplos
            WHERE empresa_id=?
            GROUP BY estado, proveedor_nif
            """,
            (str(empresa_id),),
        )
        filas = [dict(r) for r in cur.fetchall()]
        pendientes = sum(int(r["total"] or 0) for r in filas if r["estado"] == "pendiente")
        por_proveedor = {}
        for fila in filas:
            if fila["estado"] == "pendiente":
                clave = str(fila["proveedor_nif"] or "Sin NIF")
                por_proveedor[clave] = por_proveedor.get(clave, 0) + int(fila["total"] or 0)
        return {"pendientes": pendientes, "por_proveedor": por_proveedor}
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
        codigo = org.get("codigo", "").upper().strip()
        if codigo != "DEHU":
            raise ValueError("DEHu es el unico organismo de notificaciones soportado.")
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
                    codigo,
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
                    codigo,
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
            (codigo,),
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
        organismo_id = buzon.get("organismo_id")
        org = self.get_notif_organismo(organismo_id) if organismo_id else None
        if not org or org.get("codigo") != "DEHU":
            raise ValueError("El buzon debe pertenecer al organismo DEHu.")
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
                organismo_id,
                "DEHU",
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
            "SELECT e.codigo, e.nombre, e.cif, e.ejercicio "
            "FROM empresas e "
            "WHERE e.ejercicio = ("
            "  SELECT MAX(e2.ejercicio) FROM empresas e2 WHERE e2.codigo=e.codigo"
            ") ORDER BY e.nombre"
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
            LEFT JOIN empresas e
              ON e.codigo = nb.codigo_empresa
             AND e.ejercicio = (
                 SELECT MAX(e2.ejercicio) FROM empresas e2
                 WHERE e2.codigo = nb.codigo_empresa
             )
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
            LEFT JOIN empresas e
              ON e.codigo = c.codigo_empresa
             AND e.ejercicio = (
                 SELECT MAX(e2.ejercicio) FROM empresas e2
                 WHERE e2.codigo = c.codigo_empresa
             )
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
            LEFT JOIN empresas e
              ON e.codigo = b.codigo_empresa
             AND e.ejercicio = (
                 SELECT MAX(e2.ejercicio) FROM empresas e2
                 WHERE e2.codigo = b.codigo_empresa
             )
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
            LEFT JOIN empresas e
              ON e.codigo = l.codigo_empresa
             AND e.ejercicio = (
                 SELECT MAX(e2.ejercicio) FROM empresas e2
                 WHERE e2.codigo = l.codigo_empresa
             )
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

    # ── Configuracion del buzon unico DEHu ───────────────────────────────────

    def sembrar_organismos_simulados(self) -> None:
        """Compatibilidad: configura DEHu como unico buzon de notificaciones."""
        self.asegurar_dehu_unico()

    def asegurar_dehu_unico(self) -> None:
        """Deja un unico buzon DEHu por cliente y conserva el historico.

        Las versiones antiguas permitian configurar portales independientes,
        aunque todos terminaban usando el conector DEHu. La migracion reasigna
        sus notificaciones y logs al buzon DEHu del cliente antes de eliminar
        los buzones y organismos obsoletos.
        """
        now = self._utc_now()
        self.conn.execute(
            """
            INSERT INTO notif_organismos
                (codigo, nombre, tipo, url_portal, descripcion, activo, created_at, updated_at)
            VALUES ('DEHU', ?, 'ESTATAL', 'https://dehu.redsara.es/',
                    'Punto unico de notificaciones de las Administraciones Publicas', 1, ?, ?)
            ON CONFLICT(codigo) DO UPDATE SET
                nombre = excluded.nombre,
                tipo = excluded.tipo,
                url_portal = excluded.url_portal,
                descripcion = excluded.descripcion,
                activo = 1,
                updated_at = excluded.updated_at
            """,
            ("Direccion Electronica Habilitada unica (DEHu)", now, now),
        )
        dehu_id = self.conn.execute(
            "SELECT id FROM notif_organismos WHERE codigo='DEHU'"
        ).fetchone()[0]

        empresas = [
            r[0] for r in self.conn.execute(
                "SELECT DISTINCT codigo_empresa FROM notif_buzones"
            ).fetchall()
        ]
        for codigo_empresa in empresas:
            buzones = self.conn.execute(
                """
                SELECT b.id, o.codigo
                FROM notif_buzones b
                LEFT JOIN notif_organismos o ON o.id=b.organismo_id
                WHERE b.codigo_empresa=?
                ORDER BY CASE WHEN o.codigo='DEHU' THEN 0 ELSE 1 END, b.created_at, b.id
                """,
                (codigo_empresa,),
            ).fetchall()
            if not buzones:
                continue
            principal = buzones[0][0]
            self.conn.execute(
                """
                UPDATE notif_buzones
                SET nombre='DEHu', organismo_id=?, tipo_buzon='DEHU',
                    updated_at=?
                WHERE id=?
                """,
                (dehu_id, now, principal),
            )
            sobrantes = [r[0] for r in buzones[1:]]
            if sobrantes:
                ph = ",".join("?" for _ in sobrantes)
                self.conn.execute(
                    "UPDATE notif_bandeja SET buzon_id=?, organismo_id=? "
                    "WHERE buzon_id IN (%s)" % ph,
                    (principal, dehu_id, *sobrantes),
                )
                self.conn.execute(
                    "UPDATE notif_sync_logs SET buzon_id=?, organismo_id=? "
                    "WHERE buzon_id IN (%s)" % ph,
                    (principal, dehu_id, *sobrantes),
                )
                self.conn.execute(
                    "DELETE FROM notif_buzones WHERE id IN (%s)" % ph,
                    sobrantes,
                )

        self.conn.execute(
            "UPDATE notif_bandeja SET organismo_id=? WHERE organismo_id IS NOT NULL",
            (dehu_id,),
        )
        self.conn.execute(
            "UPDATE notif_sync_logs SET organismo_id=? WHERE organismo_id IS NOT NULL",
            (dehu_id,),
        )
        self.conn.execute("DELETE FROM notif_organismos WHERE codigo<>'DEHU'")
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
            for buzon in [{
                "id": str(_uuid.uuid4()), "codigo_empresa": codigo_empresa,
                "nombre": "DEHu", "organismo_id": org_map.get("DEHU"),
                "tipo_buzon": "DEHU", "nif_titular": nif,
                "certificado_id": cert_id, "activo": 1,
                "ultima_consulta": None,
            }]:
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
            buzon_dehu = next(
                (b["id"] for b in self.listar_notif_buzones(codigo_empresa)
                 if b.get("organismo_codigo") == "DEHU"),
                None,
            )
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
                org_id = org_map.get("DEHU")
                buzon_id = buzon_dehu
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

    # ---------------------------------------------------------------- comunicaciones

    def listar_comunicaciones(self, codigo_empresa: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT c.*, COUNT(m.id) AS mensajes,
                   MAX(m.fecha) AS ultima_fecha,
                   (SELECT m2.remitente FROM comunicaciones_mensajes m2
                    WHERE m2.comunicacion_id=c.id ORDER BY m2.fecha DESC LIMIT 1) AS ultimo_remitente,
                   (SELECT m2.direccion FROM comunicaciones_mensajes m2
                    WHERE m2.comunicacion_id=c.id ORDER BY m2.fecha DESC LIMIT 1) AS ultima_direccion
            FROM comunicaciones c
            LEFT JOIN comunicaciones_mensajes m ON m.comunicacion_id=c.id
            WHERE c.codigo_empresa=? AND c.descartado=0
            GROUP BY c.id ORDER BY c.updated_at DESC
            """,
            (codigo_empresa,),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def listar_mensajes_comunicacion(self, comunicacion_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM comunicaciones_mensajes WHERE comunicacion_id=? ORDER BY fecha DESC",
            (comunicacion_id,),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_comunicacion(self, comunicacion_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM comunicaciones WHERE id=?", (str(comunicacion_id),),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def registrar_adjunto_comunicacion(self, mensaje_id: str, ruta: str | Path, tamano: int | None = None) -> None:
        path = Path(ruta)
        with self.conn:
            self.conn.execute(
                """INSERT OR IGNORE INTO comunicaciones_adjuntos (mensaje_id,nombre,ruta,tamano)
                   VALUES (?,?,?,?)""",
                (str(mensaje_id), path.name, str(path), tamano if tamano is not None else (path.stat().st_size if path.exists() else None)),
            )

    def registrar_envio_comunicacion(self, datos: dict) -> tuple[str, str]:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        comunicacion_id = str(datos.get("comunicacion_id") or uuid.uuid4())
        mensaje_id = str(uuid.uuid4())
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO comunicaciones
                  (id,codigo_empresa,asunto,estado,responsable_usuario_id,
                   responsable_nombre,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at
                """,
                (
                    comunicacion_id, datos["codigo_empresa"], datos["asunto"], "abierta",
                    datos.get("usuario_id"), datos.get("usuario_nombre"), now, now,
                ),
            )
            self.conn.execute(
                """
                INSERT INTO comunicaciones_mensajes
                  (id,comunicacion_id,direccion,remitente,destinatarios_json,cc_json,
                   asunto,cuerpo_html,estado_envio,error_envio,graph_message_id,
                   internet_message_id,tiene_adjuntos,usuario_id,usuario_nombre,fecha,mailbox)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    mensaje_id, comunicacion_id, "saliente", datos.get("remitente"),
                    json.dumps(datos.get("destinatarios") or []),
                    json.dumps(datos.get("cc") or []), datos["asunto"],
                    datos.get("cuerpo_html"), datos.get("estado_envio"),
                    datos.get("error_envio"), datos.get("graph_message_id"),
                    datos.get("internet_message_id"), int(bool(datos.get("adjuntos"))),
                    datos.get("usuario_id"),
                    datos.get("usuario_nombre"), now, datos.get("mailbox"),
                ),
            )
            for ruta in datos.get("adjuntos") or []:
                path = Path(ruta)
                self.conn.execute(
                    "INSERT INTO comunicaciones_adjuntos (mensaje_id,nombre,ruta,tamano) VALUES (?,?,?,?)",
                    (mensaje_id, path.name, str(path), path.stat().st_size if path.exists() else None),
                )
        return comunicacion_id, mensaje_id

    def get_comunicaciones_delta(self, mailbox: str) -> str:
        row = self.conn.execute(
            "SELECT delta_link FROM comunicaciones_sync WHERE mailbox=?",
            (mailbox.lower(),),
        ).fetchone()
        return str(row["delta_link"] or "") if row else ""

    def guardar_comunicaciones_delta(
        self, mailbox: str, delta_link: str, error: str = "",
    ) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO comunicaciones_sync
                  (mailbox,delta_link,ultima_sincronizacion,ultimo_error)
                VALUES (?,?,?,?)
                ON CONFLICT(mailbox) DO UPDATE SET
                  delta_link=excluded.delta_link,
                  ultima_sincronizacion=excluded.ultima_sincronizacion,
                  ultimo_error=excluded.ultimo_error
                """,
                (mailbox.lower(), delta_link, now, error or None),
            )

    def buscar_empresa_por_email(self, email: str) -> dict | None:
        value = str(email or "").strip().lower()
        if not value:
            return None
        rows = self.conn.execute(
            """
            SELECT e.codigo,e.ejercicio,e.nombre,e.responsable,e.email
            FROM empresas e
            JOIN (
              SELECT codigo,MAX(ejercicio) ejercicio FROM empresas GROUP BY codigo
            ) u ON u.codigo=e.codigo AND u.ejercicio=e.ejercicio
            UNION
            SELECT e.codigo,e.ejercicio,e.nombre,e.responsable,t.email
            FROM terceros t
            JOIN terceros_empresas te ON te.tercero_id=t.id
            JOIN empresas e ON e.codigo=te.codigo_empresa AND e.ejercicio=te.ejercicio
            """,
        ).fetchall()
        unique = {}
        for row in rows:
            emails = {
                part.strip().lower()
                for part in re.split(r"[,;]", str(row["email"] or ""))
                if part.strip()
            }
            if value in emails:
                unique[row["codigo"]] = self._row_to_dict(row)
        return next(iter(unique.values())) if len(unique) == 1 else None

    def registrar_entrada_comunicacion(self, datos: dict) -> tuple[str, str] | None:
        graph_id = str(datos.get("graph_message_id") or "")
        if graph_id and self.conn.execute(
            "SELECT 1 FROM comunicaciones_mensajes WHERE graph_message_id=?",
            (graph_id,),
        ).fetchone():
            return None
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        conversation_id = str(datos.get("graph_conversation_id") or "")
        row = self.conn.execute(
            "SELECT id FROM comunicaciones WHERE graph_conversation_id=?",
            (conversation_id,),
        ).fetchone() if conversation_id else None
        comunicacion_id = row["id"] if row else str(uuid.uuid4())
        mensaje_id = str(uuid.uuid4())
        with self.conn:
            if not row:
                self.conn.execute(
                    """
                    INSERT INTO comunicaciones
                      (id,codigo_empresa,asunto,estado,responsable_nombre,
                       created_at,updated_at,graph_conversation_id)
                    VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (
                        comunicacion_id, datos["codigo_empresa"],
                        datos.get("asunto") or "(Sin asunto)", "abierta",
                        datos.get("responsable_nombre"), now, now, conversation_id,
                    ),
                )
            else:
                self.conn.execute(
                    "UPDATE comunicaciones SET updated_at=? WHERE id=?",
                    (now, comunicacion_id),
                )
            self.conn.execute(
                """
                INSERT INTO comunicaciones_mensajes
                  (id,comunicacion_id,direccion,remitente,destinatarios_json,
                   cc_json,asunto,cuerpo_html,estado_envio,graph_message_id,
                   internet_message_id,tiene_adjuntos,fecha,mailbox)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    mensaje_id, comunicacion_id, "entrante",
                    datos.get("remitente"),
                    json.dumps(datos.get("destinatarios") or []),
                    json.dumps(datos.get("cc") or []),
                    datos.get("asunto") or "(Sin asunto)",
                    datos.get("cuerpo_html") or "", "recibido",
                    graph_id, datos.get("internet_message_id"),
                    int(bool(datos.get("tiene_adjuntos"))),
                    datos.get("fecha") or now, datos.get("mailbox"),
                ),
            )
        return comunicacion_id, mensaje_id

    def guardar_comunicacion_sin_asignar(
        self, datos: dict, sugerencia: dict | None = None,
        responsable: dict | None = None,
    ) -> bool:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT OR IGNORE INTO comunicaciones_sin_asignar
                  (graph_message_id,mailbox,remitente,asunto,fecha,cuerpo_html,
                  payload_json,sugerencia_codigo_empresa,sugerencia_nombre,
                  responsable_usuario_id,responsable_nombre,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    datos["graph_message_id"], datos.get("mailbox") or "",
                    datos.get("remitente"), datos.get("asunto"),
                    datos.get("fecha"), datos.get("cuerpo_html"),
                    json.dumps(datos),
                    (sugerencia or {}).get("codigo"),
                    (sugerencia or {}).get("nombre"),
                    (responsable or {}).get("id"),
                    (responsable or {}).get("nombre"),
                    now,
                ),
            )
        return cursor.rowcount > 0

    def listar_pendientes_responsable(self, usuario_id: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM comunicaciones_sin_asignar
            WHERE responsable_usuario_id=? AND descartado=0
              AND (sin_cliente_confirmado=1 OR estado<>'gestionado')
            ORDER BY fecha DESC
            """,
            (usuario_id,),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def listar_comunicaciones_sin_asignar(
        self, incluir_gestionados: bool = False,
    ) -> list[dict]:
        where = "descartado=0"
        if not incluir_gestionados:
            where += " AND estado<>'gestionado' AND sin_cliente_confirmado=0"
        rows = self.conn.execute(
            f"SELECT * FROM comunicaciones_sin_asignar WHERE {where} ORDER BY fecha DESC"
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def obtener_nuevos_avisos_correo(
        self, usuario_id: int, mailbox: str,
    ) -> list[dict]:
        """Devuelve una sola vez los correos incorporados desde el ultimo control.

        La primera llamada inicializa el cursor sin recuperar el historico. En
        llamadas posteriores tambien incluye lo recibido mientras el usuario
        tenia cerrada la aplicacion.
        """
        usuario_id = int(usuario_id)
        mailbox = str(mailbox or "").strip().lower()
        if not mailbox:
            return []
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.conn:
            estado = self.conn.execute(
                "SELECT ultimo_control_at FROM comunicaciones_avisos_estado "
                "WHERE usuario_id=?",
                (usuario_id,),
            ).fetchone()
            if not estado:
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO comunicaciones_avisos_vistos
                      (usuario_id,graph_message_id,avisado_at)
                    SELECT ?,graph_message_id,?
                    FROM comunicaciones_sin_asignar
                    WHERE LOWER(mailbox)=?
                    """,
                    (usuario_id, now, mailbox),
                )
                self.conn.execute(
                    "INSERT INTO comunicaciones_avisos_estado "
                    "(usuario_id,ultimo_control_at,updated_at) VALUES (?,?,?)",
                    (usuario_id, now, now),
                )
                return []
            rows = self.conn.execute(
                """
                SELECT p.graph_message_id,p.mailbox,p.remitente,p.asunto,
                       p.fecha,p.created_at
                FROM comunicaciones_sin_asignar p
                WHERE LOWER(p.mailbox)=? AND p.descartado=0
                  AND NOT EXISTS (
                    SELECT 1 FROM comunicaciones_avisos_vistos v
                    WHERE v.usuario_id=?
                      AND v.graph_message_id=p.graph_message_id
                  )
                ORDER BY p.created_at,p.graph_message_id
                """,
                (mailbox, usuario_id),
            ).fetchall()
            for row in rows:
                self.conn.execute(
                    "INSERT OR IGNORE INTO comunicaciones_avisos_vistos "
                    "(usuario_id,graph_message_id,avisado_at) VALUES (?,?,?)",
                    (usuario_id, row["graph_message_id"], now),
                )
            self.conn.execute(
                "UPDATE comunicaciones_avisos_estado "
                "SET ultimo_control_at=?,updated_at=? WHERE usuario_id=?",
                (now, now, usuario_id),
            )
        return [self._row_to_dict(row) for row in rows]

    def listar_comunicaciones_descartadas(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM comunicaciones_sin_asignar "
            "WHERE descartado=1 ORDER BY descartado_at DESC"
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def listar_conversaciones_descartadas(self) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT c.*,e.nombre AS cliente_nombre,
                   MAX(m.fecha) AS fecha,
                   (
                     SELECT mm.remitente FROM comunicaciones_mensajes mm
                     WHERE mm.comunicacion_id=c.id
                     ORDER BY mm.fecha DESC LIMIT 1
                   ) AS remitente,
                   (
                     SELECT mm.mailbox FROM comunicaciones_mensajes mm
                     WHERE mm.comunicacion_id=c.id
                       AND mm.mailbox IS NOT NULL AND mm.mailbox<>''
                     ORDER BY mm.fecha DESC LIMIT 1
                   ) AS mailbox
            FROM comunicaciones c
            LEFT JOIN (
              SELECT e1.codigo,e1.nombre FROM empresas e1
              JOIN (
                SELECT codigo,MAX(ejercicio) ejercicio
                FROM empresas GROUP BY codigo
              ) latest
                ON latest.codigo=e1.codigo AND latest.ejercicio=e1.ejercicio
            ) e ON e.codigo=c.codigo_empresa
            LEFT JOIN comunicaciones_mensajes m ON m.comunicacion_id=c.id
            WHERE c.descartado=1
            GROUP BY c.id, e.nombre
            ORDER BY c.descartado_at DESC
            """
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def listar_comunicaciones_sin_cliente_asignadas(self) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT *,fecha AS ultima_fecha,remitente AS ultimo_remitente,
                   'Sin cliente' AS cliente_nombre
            FROM comunicaciones_sin_asignar
            WHERE sin_cliente_confirmado=1 AND descartado=0
              AND responsable_usuario_id IS NOT NULL
            ORDER BY fecha DESC
            """
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def asignar_comunicaciones_sin_cliente(
        self, graph_message_ids: list[str], responsable_usuario_id: int,
        responsable_nombre: str,
    ) -> int:
        ids = list(dict.fromkeys(graph_message_ids))
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with self.conn:
            cursor = self.conn.execute(
                f"""
                UPDATE comunicaciones_sin_asignar
                SET responsable_usuario_id=?,responsable_nombre=?,
                    sin_cliente_confirmado=1,estado='pendiente'
                WHERE graph_message_id IN ({placeholders}) AND descartado=0
                """,
                (responsable_usuario_id, responsable_nombre, *ids),
            )
        return cursor.rowcount

    def cambiar_estado_pendiente_responsable(
        self, graph_message_id: str, estado: str, usuario_id: int,
    ) -> None:
        if estado not in {"pendiente", "respondido", "gestionado"}:
            raise ValueError("Estado de comunicacion no valido.")
        with self.conn:
            self.conn.execute(
                "UPDATE comunicaciones_sin_asignar SET estado=? "
                "WHERE graph_message_id=? AND responsable_usuario_id=? AND descartado=0",
                (estado, graph_message_id, usuario_id),
            )

    def descartar_comunicaciones(
        self, graph_message_ids: list[str], usuario_nombre: str, motivo: str = "",
    ) -> int:
        ids = list(dict.fromkeys(graph_message_ids))
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.conn:
            cursor = self.conn.execute(
                f"""
                UPDATE comunicaciones_sin_asignar
                SET descartado=1,descartado_por=?,descartado_at=?,motivo_descarte=?
                WHERE graph_message_id IN ({placeholders})
                """,
                (usuario_nombre, now, motivo or None, *ids),
            )
        return cursor.rowcount

    def restaurar_comunicaciones(self, graph_message_ids: list[str]) -> int:
        ids = list(dict.fromkeys(graph_message_ids))
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with self.conn:
            cursor = self.conn.execute(
                f"""
                UPDATE comunicaciones_sin_asignar
                SET descartado=0,descartado_por=NULL,descartado_at=NULL,
                    motivo_descarte=NULL
                WHERE graph_message_id IN ({placeholders})
                """,
                tuple(ids),
            )
        return cursor.rowcount

    def descartar_conversaciones(
        self, comunicacion_ids: list[str], usuario_nombre: str, motivo: str = "",
    ) -> int:
        ids = list(dict.fromkeys(comunicacion_ids))
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.conn:
            cursor = self.conn.execute(
                f"""
                UPDATE comunicaciones
                SET descartado=1,descartado_por=?,descartado_at=?,
                    motivo_descarte=?,updated_at=?
                WHERE id IN ({placeholders}) AND descartado=0
                """,
                (usuario_nombre, now, motivo or None, now, *ids),
            )
        return cursor.rowcount

    def restaurar_conversaciones(self, comunicacion_ids: list[str]) -> int:
        ids = list(dict.fromkeys(comunicacion_ids))
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.conn:
            cursor = self.conn.execute(
                f"""
                UPDATE comunicaciones
                SET descartado=0,descartado_por=NULL,descartado_at=NULL,
                    motivo_descarte=NULL,updated_at=?
                WHERE id IN ({placeholders}) AND descartado=1
                """,
                (now, *ids),
            )
        return cursor.rowcount

    def reasignar_comunicacion(
        self, comunicacion_id: str, codigo_empresa: str,
        responsable_usuario_id: int, responsable_nombre: str,
    ) -> bool:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE comunicaciones
                SET codigo_empresa=?,responsable_usuario_id=?,
                    responsable_nombre=?,updated_at=?
                WHERE id=? AND descartado=0
                """,
                (
                    codigo_empresa, responsable_usuario_id,
                    responsable_nombre, now, comunicacion_id,
                ),
            )
        return cursor.rowcount > 0

    def reasignar_pendiente_responsable(
        self, graph_message_id: str, responsable_usuario_id: int,
        responsable_nombre: str,
    ) -> bool:
        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE comunicaciones_sin_asignar
                SET responsable_usuario_id=?,responsable_nombre=?,
                    sin_cliente_confirmado=1
                WHERE graph_message_id=? AND descartado=0
                """,
                (responsable_usuario_id, responsable_nombre, graph_message_id),
            )
        return cursor.rowcount > 0

    def asignar_comunicacion_pendiente(
        self, graph_message_id: str, codigo_empresa: str,
        responsable_usuario_id: int, responsable_nombre: str,
    ) -> tuple[str, str] | None:
        row = self.conn.execute(
            "SELECT payload_json,etiqueta FROM comunicaciones_sin_asignar "
            "WHERE graph_message_id=?",
            (graph_message_id,),
        ).fetchone()
        if not row:
            return None
        datos = json.loads(row["payload_json"])
        etiqueta = str(row["etiqueta"] or "").strip()
        empresa = self.get_empresa(codigo_empresa) or {}
        datos["codigo_empresa"] = codigo_empresa
        datos["responsable_usuario_id"] = responsable_usuario_id
        datos["responsable_nombre"] = responsable_nombre
        result = self.registrar_entrada_comunicacion(datos)
        if result:
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE comunicaciones
                    SET responsable_usuario_id=?,responsable_nombre=?,estado='pendiente',
                        etiqueta=?
                    WHERE id=?
                    """,
                    (responsable_usuario_id, responsable_nombre, etiqueta or None, result[0]),
                )
        with self.conn:
            self.conn.execute(
                "DELETE FROM comunicaciones_sin_asignar WHERE graph_message_id=?",
                (graph_message_id,),
            )
        return result

    def asignar_comunicaciones_pendientes(
        self, graph_message_ids: list[str], codigo_empresa: str,
        responsable_usuario_id: int, responsable_nombre: str,
    ) -> dict:
        asignadas = []
        omitidas = []
        for graph_message_id in dict.fromkeys(graph_message_ids):
            result = self.asignar_comunicacion_pendiente(
                graph_message_id, codigo_empresa,
                responsable_usuario_id, responsable_nombre,
            )
            if result:
                asignadas.append(graph_message_id)
            else:
                omitidas.append(graph_message_id)
        return {"asignadas": asignadas, "omitidas": omitidas}

    def listar_buzon_responsable(self, usuario_id: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT c.*,e.nombre AS cliente_nombre,
                   COUNT(m.id) mensajes,MAX(m.fecha) ultima_fecha,
                   (
                     SELECT mm.remitente FROM comunicaciones_mensajes mm
                     WHERE mm.comunicacion_id=c.id
                     ORDER BY mm.fecha DESC LIMIT 1
                   ) AS ultimo_remitente,
                   (
                     SELECT mm.mailbox
                     FROM comunicaciones_mensajes mm
                     WHERE mm.comunicacion_id=c.id
                       AND mm.mailbox IS NOT NULL AND mm.mailbox<>''
                     ORDER BY mm.fecha DESC LIMIT 1
                   ) AS mailbox
            FROM comunicaciones c
            LEFT JOIN (
              SELECT e1.codigo,e1.nombre FROM empresas e1
              JOIN (
                SELECT codigo,MAX(ejercicio) ejercicio FROM empresas GROUP BY codigo
              ) latest ON latest.codigo=e1.codigo AND latest.ejercicio=e1.ejercicio
            ) e ON e.codigo=c.codigo_empresa
            LEFT JOIN comunicaciones_mensajes m ON m.comunicacion_id=c.id
            WHERE c.responsable_usuario_id=? AND c.descartado=0
            GROUP BY c.id,e.nombre ORDER BY c.updated_at DESC
            """,
            (usuario_id,),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def actualizar_etiqueta_pendiente(
        self, graph_message_id: str, etiqueta: str,
    ) -> bool:
        with self.conn:
            cursor = self.conn.execute(
                "UPDATE comunicaciones_sin_asignar SET etiqueta=? "
                "WHERE graph_message_id=? AND descartado=0",
                (str(etiqueta or "").strip() or None, graph_message_id),
            )
        return cursor.rowcount > 0

    def actualizar_etiqueta_comunicacion(
        self, comunicacion_id: str, etiqueta: str,
    ) -> bool:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.conn:
            cursor = self.conn.execute(
                "UPDATE comunicaciones SET etiqueta=?,updated_at=? "
                "WHERE id=? AND descartado=0",
                (str(etiqueta or "").strip() or None, now, comunicacion_id),
            )
        return cursor.rowcount > 0

    def resumen_buzon_responsable(
        self, usuario_id: int, mailbox: str | None = None,
    ) -> dict[str, int]:
        """Resume el buzon de un responsable.

        Cuando se indica ``mailbox``, el resumen usa el mismo criterio que el
        listado de la interfaz: solo cuenta conversaciones cuyo ultimo mensaje
        pertenece a ese buzon, y pendientes sin cliente de ese mismo buzon.
        """
        counts = {"pendiente": 0, "respondido": 0, "gestionado": 0}
        mailbox = str(mailbox or "").strip().lower()
        filtro_comunicaciones = ""
        filtro_pendientes = ""
        params: list[object] = [usuario_id]
        if mailbox:
            filtro_comunicaciones = """
                AND COALESCE((
                    SELECT LOWER(mm.mailbox)
                    FROM comunicaciones_mensajes mm
                    WHERE mm.comunicacion_id=comunicaciones.id
                      AND mm.mailbox IS NOT NULL AND mm.mailbox<>''
                    ORDER BY mm.fecha DESC LIMIT 1
                ), '')=?
            """
            params.append(mailbox)
        params.append(usuario_id)
        if mailbox:
            filtro_pendientes = " AND LOWER(COALESCE(mailbox,''))=?"
            params.append(mailbox)
        rows = self.conn.execute(
            f"""
            SELECT estado,COUNT(*) total FROM (
              SELECT CASE
                       WHEN LOWER(COALESCE(estado,'')) IN ('', 'abierta', 'abierto', 'sin_gestionar') THEN 'pendiente'
                       ELSE LOWER(estado)
                     END estado
              FROM comunicaciones
              WHERE responsable_usuario_id=? AND descartado=0
              {filtro_comunicaciones}
              UNION ALL
              SELECT CASE
                       WHEN LOWER(COALESCE(estado,'')) IN ('', 'abierta', 'abierto', 'sin_gestionar') THEN 'pendiente'
                       ELSE LOWER(estado)
                     END estado
              FROM comunicaciones_sin_asignar
              WHERE responsable_usuario_id=? AND descartado=0
                AND sin_cliente_confirmado=1
              {filtro_pendientes}
            ) pendientes GROUP BY estado
            """,
            tuple(params),
        ).fetchall()
        for row in rows:
            estado = str(row["estado"] or "pendiente")
            if estado in counts:
                counts[estado] = int(row["total"] or 0)
        counts["total"] = sum(counts.values())
        return counts

    def listar_comunicaciones_supervision(self) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT c.*,e.nombre AS cliente_nombre,
                   COUNT(m.id) AS mensajes,
                   MAX(m.fecha) AS ultima_fecha,
                   (
                     SELECT mm.remitente
                     FROM comunicaciones_mensajes mm
                     WHERE mm.comunicacion_id=c.id
                     ORDER BY mm.fecha DESC LIMIT 1
                   ) AS ultimo_remitente,
                   (
                     SELECT mm.mailbox
                     FROM comunicaciones_mensajes mm
                     WHERE mm.comunicacion_id=c.id
                       AND mm.mailbox IS NOT NULL AND mm.mailbox<>''
                     ORDER BY mm.fecha DESC LIMIT 1
                   ) AS mailbox
            FROM comunicaciones c
            LEFT JOIN (
              SELECT e1.codigo,e1.nombre
              FROM empresas e1
              JOIN (
                SELECT codigo,MAX(ejercicio) ejercicio
                FROM empresas GROUP BY codigo
              ) latest
                ON latest.codigo=e1.codigo AND latest.ejercicio=e1.ejercicio
            ) e ON e.codigo=c.codigo_empresa
            LEFT JOIN comunicaciones_mensajes m ON m.comunicacion_id=c.id
            WHERE c.responsable_usuario_id IS NOT NULL AND c.descartado=0
            GROUP BY c.id, e.nombre
            ORDER BY c.updated_at DESC
            """
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def cambiar_estado_comunicacion(
        self, comunicacion_id: str, estado: str, usuario_id: int,
        allow_any_responsible: bool = False,
    ) -> None:
        allowed = {"pendiente", "respondido", "gestionado"}
        if estado not in allowed:
            raise ValueError("Estado de comunicacion no valido.")
        with self.conn:
            params = (
                estado, datetime.now().astimezone().isoformat(timespec="seconds"),
                comunicacion_id,
            )
            sql = "UPDATE comunicaciones SET estado=?,updated_at=? WHERE id=?"
            if not allow_any_responsible:
                sql += " AND responsable_usuario_id=?"
                params += (usuario_id,)
            self.conn.execute(sql, params)
