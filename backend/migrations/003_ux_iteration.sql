-- Migracion 003: UX iteration 2 - perfiles, password reset rate limiting
-- Aditiva, idempotente, sin destruir historico.

-- Rate limiting para forgot-password (intentos por IP)
CREATE TABLE IF NOT EXISTS msg_rate_limits (
    id BIGSERIAL PRIMARY KEY,
    key VARCHAR(200) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    count INTEGER NOT NULL DEFAULT 1,
    UNIQUE(key, window_start)
);
CREATE INDEX IF NOT EXISTS ix_msg_rate_limits_key_window ON msg_rate_limits(key, window_start);

-- Campo display_name para personalizacion sin tocar name
ALTER TABLE msg_staff ADD COLUMN IF NOT EXISTS display_name VARCHAR(160) NOT NULL DEFAULT '';

-- Marcar conversaciones como silenciadas (para futura funcionalidad)
ALTER TABLE msg_reads ADD COLUMN IF NOT EXISTS muted_until TIMESTAMPTZ;

-- Indice para busqueda de conversaciones por organizacion + estado
CREATE INDEX IF NOT EXISTS ix_msg_conversations_org_updated
    ON msg_conversations(organization_id, updated_at DESC);

-- Tabla de tokens de password reset ya existe en el modelo base,
-- pero aseguramos el indice de expiracion:
CREATE INDEX IF NOT EXISTS ix_msg_password_resets_expires_at
    ON msg_password_resets(expires_at);
CREATE INDEX IF NOT EXISTS ix_msg_password_resets_client_id
    ON msg_password_resets(client_id);
