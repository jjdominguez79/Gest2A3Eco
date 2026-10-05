ALTER TABLE sub_convocatorias
    ALTER COLUMN codigo_bdns TYPE VARCHAR(80);

ALTER TABLE sub_convocatorias
    ADD COLUMN IF NOT EXISTS fuente VARCHAR(24) NOT NULL DEFAULT 'BDNS',
    ADD COLUMN IF NOT EXISTS fuente_nombre VARCHAR(180) NOT NULL
        DEFAULT 'Base de Datos Nacional de Subvenciones',
    ADD COLUMN IF NOT EXISTS codigo_fuente VARCHAR(160) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS naturaleza VARCHAR(32) NOT NULL DEFAULT 'convocatoria';

UPDATE sub_convocatorias
SET codigo_fuente = codigo_bdns
WHERE codigo_fuente = '';

CREATE INDEX IF NOT EXISTS ix_sub_convocatorias_fuente
    ON sub_convocatorias(fuente);
CREATE INDEX IF NOT EXISTS ix_sub_convocatorias_codigo_fuente
    ON sub_convocatorias(codigo_fuente);
CREATE INDEX IF NOT EXISTS ix_sub_convocatorias_naturaleza
    ON sub_convocatorias(naturaleza);
