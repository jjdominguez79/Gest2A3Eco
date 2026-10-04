ALTER TABLE msg_organizations
    ADD COLUMN IF NOT EXISTS client_subsidies_enabled BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS sub_convocatorias (
    id VARCHAR(36) PRIMARY KEY,
    codigo_bdns VARCHAR(24) NOT NULL UNIQUE,
    titulo TEXT NOT NULL,
    organo_nivel1 VARCHAR(80) NOT NULL DEFAULT '',
    organo_nivel2 VARCHAR(250) NOT NULL DEFAULT '',
    organo_nivel3 VARCHAR(350) NOT NULL DEFAULT '',
    ambito VARCHAR(16) NOT NULL,
    alcance_nacional BOOLEAN NOT NULL DEFAULT FALSE,
    ccaa_json JSONB NOT NULL DEFAULT '[]',
    provincias_json JSONB NOT NULL DEFAULT '[]',
    municipio_nombre VARCHAR(160) NOT NULL DEFAULT '',
    municipio_slug VARCHAR(160) NOT NULL DEFAULT '',
    es_provincial BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_recepcion DATE,
    fecha_inicio DATE,
    fecha_fin DATE,
    texto_inicio TEXT NOT NULL DEFAULT '',
    texto_fin TEXT NOT NULL DEFAULT '',
    abierto BOOLEAN,
    presupuesto DOUBLE PRECISION,
    tipo_convocatoria VARCHAR(250) NOT NULL DEFAULT '',
    finalidad VARCHAR(350) NOT NULL DEFAULT '',
    beneficiarios_json JSONB NOT NULL DEFAULT '[]',
    sectores_json JSONB NOT NULL DEFAULT '[]',
    instrumentos_json JSONB NOT NULL DEFAULT '[]',
    mrr BOOLEAN NOT NULL DEFAULT FALSE,
    enlaces_json JSONB NOT NULL DEFAULT '[]',
    resumen_json JSONB,
    resumen_estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
    resumen_modelo VARCHAR(100) NOT NULL DEFAULT '',
    hash_fuente VARCHAR(64) NOT NULL DEFAULT '',
    hash_resumen VARCHAR(64) NOT NULL DEFAULT '',
    raw_json JSONB NOT NULL DEFAULT '{}',
    visible BOOLEAN NOT NULL DEFAULT TRUE,
    revisada BOOLEAN NOT NULL DEFAULT FALSE,
    creada_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizada_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_sub_convocatorias_ambito ON sub_convocatorias(ambito);
CREATE INDEX IF NOT EXISTS ix_sub_convocatorias_fecha ON sub_convocatorias(fecha_recepcion DESC);
CREATE INDEX IF NOT EXISTS ix_sub_convocatorias_fecha_fin ON sub_convocatorias(fecha_fin);
CREATE INDEX IF NOT EXISTS ix_sub_convocatorias_municipio ON sub_convocatorias(municipio_slug);
CREATE INDEX IF NOT EXISTS ix_sub_convocatorias_visible ON sub_convocatorias(visible);
CREATE INDEX IF NOT EXISTS ix_sub_convocatorias_revisada ON sub_convocatorias(revisada);
CREATE INDEX IF NOT EXISTS ix_sub_convocatorias_resumen ON sub_convocatorias(resumen_estado);

CREATE TABLE IF NOT EXISTS sub_preferencias (
    client_id VARCHAR(36) PRIMARY KEY REFERENCES msg_clients(id) ON DELETE CASCADE,
    notificaciones_activas BOOLEAN NOT NULL DEFAULT FALSE,
    incluir_nacionales BOOLEAN NOT NULL DEFAULT TRUE,
    usar_territorio_empresa BOOLEAN NOT NULL DEFAULT TRUE,
    creada_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizada_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sub_suscripciones (
    id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL REFERENCES msg_clients(id) ON DELETE CASCADE,
    nivel VARCHAR(16) NOT NULL,
    codigo VARCHAR(160) NOT NULL,
    nombre VARCHAR(200) NOT NULL,
    creada_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_sub_suscripcion UNIQUE(client_id, nivel, codigo)
);
CREATE INDEX IF NOT EXISTS ix_sub_suscripciones_cliente ON sub_suscripciones(client_id);

CREATE TABLE IF NOT EXISTS sub_ejecuciones (
    id SERIAL PRIMARY KEY,
    inicio TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fin TIMESTAMPTZ,
    estado VARCHAR(20) NOT NULL DEFAULT 'en_curso',
    leidas INTEGER NOT NULL DEFAULT 0,
    nuevas INTEGER NOT NULL DEFAULT 0,
    actualizadas INTEGER NOT NULL DEFAULT 0,
    resumidas INTEGER NOT NULL DEFAULT 0,
    avisos_enviados INTEGER NOT NULL DEFAULT 0,
    detalle TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sub_configuracion (
    id VARCHAR(20) PRIMARY KEY DEFAULT 'global',
    servicio_activo BOOLEAN NOT NULL DEFAULT TRUE,
    avisos_activos BOOLEAN NOT NULL DEFAULT FALSE,
    resumenes_ia_activos BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by VARCHAR(160) NOT NULL DEFAULT '',
    actualizada_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO sub_configuracion (id) VALUES ('global') ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS sub_entregas (
    id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(36) NOT NULL REFERENCES msg_clients(id) ON DELETE CASCADE,
    convocatoria_id VARCHAR(36) NOT NULL REFERENCES sub_convocatorias(id) ON DELETE CASCADE,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
    intentos INTEGER NOT NULL DEFAULT 0,
    dispositivos_enviados INTEGER NOT NULL DEFAULT 0,
    ultimo_error TEXT NOT NULL DEFAULT '',
    enviada_at TIMESTAMPTZ,
    creada_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizada_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_sub_entrega UNIQUE(client_id, convocatoria_id)
);
CREATE INDEX IF NOT EXISTS ix_sub_entregas_estado ON sub_entregas(estado);
CREATE INDEX IF NOT EXISTS ix_sub_entregas_cliente ON sub_entregas(client_id);
CREATE INDEX IF NOT EXISTS ix_sub_entregas_convocatoria ON sub_entregas(convocatoria_id);
