-- Esquema inicial PostgreSQL. SQLAlchemy mantiene el mismo modelo en desarrollo.
CREATE TABLE dgt_expedientes (
    id uuid PRIMARY KEY, referencia varchar(32) UNIQUE NOT NULL, tipo varchar(64) NOT NULL,
    titulo varchar(200) NOT NULL DEFAULT '', estado varchar(40) NOT NULL DEFAULT 'borrador',
    responsable varchar(120) NOT NULL DEFAULT '', observaciones text NOT NULL DEFAULT '',
    version integer NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE dgt_partes (
    id uuid PRIMARY KEY, expediente_id uuid NOT NULL REFERENCES dgt_expedientes(id) ON DELETE CASCADE,
    rol varchar(16) NOT NULL, estado varchar(32) NOT NULL DEFAULT 'pendiente',
    tipo_persona varchar(16) NOT NULL DEFAULT 'fisica', nombre varchar(200) NOT NULL DEFAULT '',
    nif varchar(20) NOT NULL DEFAULT '', email varchar(254) NOT NULL DEFAULT '',
    telefono varchar(32) NOT NULL DEFAULT '', datos jsonb NOT NULL DEFAULT '{}',
    submitted_at timestamptz, UNIQUE(expediente_id, rol)
);
CREATE TABLE dgt_vehiculos (id uuid PRIMARY KEY, expediente_id uuid UNIQUE NOT NULL REFERENCES dgt_expedientes(id) ON DELETE CASCADE, matricula varchar(20) NOT NULL DEFAULT '', bastidor varchar(40) NOT NULL DEFAULT '', datos jsonb NOT NULL DEFAULT '{}');
CREATE TABLE dgt_operaciones (id uuid PRIMARY KEY, expediente_id uuid UNIQUE NOT NULL REFERENCES dgt_expedientes(id) ON DELETE CASCADE, datos jsonb NOT NULL DEFAULT '{}');
CREATE TABLE dgt_enlaces (id uuid PRIMARY KEY, expediente_id uuid NOT NULL REFERENCES dgt_expedientes(id) ON DELETE CASCADE, rol varchar(16) NOT NULL, token_hash char(64) UNIQUE NOT NULL, expires_at timestamptz NOT NULL, revoked_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), last_access_at timestamptz);
CREATE TABLE dgt_documentos (id uuid PRIMARY KEY, expediente_id uuid NOT NULL REFERENCES dgt_expedientes(id) ON DELETE CASCADE, rol varchar(16) NOT NULL, tipo varchar(64) NOT NULL, nombre_archivo varchar(255) NOT NULL, storage_key varchar(500) UNIQUE NOT NULL, content_type varchar(100) NOT NULL, size integer NOT NULL, sha256 char(64) NOT NULL, dataprius_json jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE dgt_solicitudes_subsanacion (id uuid PRIMARY KEY, expediente_id uuid NOT NULL REFERENCES dgt_expedientes(id) ON DELETE CASCADE, rol varchar(16) NOT NULL, mensaje text NOT NULL, estado varchar(32) NOT NULL DEFAULT 'pendiente', created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE dgt_documentos_generados (id uuid PRIMARY KEY, expediente_id uuid NOT NULL REFERENCES dgt_expedientes(id) ON DELETE CASCADE, tipo varchar(64) NOT NULL, datos jsonb NOT NULL DEFAULT '{}');
CREATE TABLE dgt_firmas (id uuid PRIMARY KEY, expediente_id uuid NOT NULL REFERENCES dgt_expedientes(id) ON DELETE CASCADE, proveedor varchar(64) NOT NULL DEFAULT '', estado varchar(32) NOT NULL DEFAULT 'pendiente', evidencia jsonb NOT NULL DEFAULT '{}');
CREATE TABLE dgt_eventos (id bigserial PRIMARY KEY, expediente_id uuid REFERENCES dgt_expedientes(id) ON DELETE SET NULL, tipo varchar(64) NOT NULL, actor varchar(120) NOT NULL DEFAULT '', ip varchar(64) NOT NULL DEFAULT '', datos jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE dgt_comunicaciones (id uuid PRIMARY KEY, expediente_id uuid NOT NULL REFERENCES dgt_expedientes(id) ON DELETE CASCADE, canal varchar(32) NOT NULL, destinatario varchar(254) NOT NULL, estado varchar(32) NOT NULL DEFAULT 'preparada', datos jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX ix_dgt_expedientes_updated_at ON dgt_expedientes(updated_at);
CREATE INDEX ix_dgt_eventos_expediente ON dgt_eventos(expediente_id, created_at);
