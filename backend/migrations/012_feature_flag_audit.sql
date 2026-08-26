-- Auditoria de cambios en feature flags de organizaciones.
-- Migracion aditiva e idempotente.

CREATE TABLE IF NOT EXISTS client_feature_flag_audit (
    id SERIAL PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL,
    flag_name VARCHAR(60) NOT NULL,
    old_value BOOLEAN NOT NULL,
    new_value BOOLEAN NOT NULL,
    changed_by VARCHAR(254) NOT NULL DEFAULT '',
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_feature_flag_audit_org
    ON client_feature_flag_audit(organization_id);

CREATE INDEX IF NOT EXISTS ix_feature_flag_audit_changed
    ON client_feature_flag_audit(changed_at DESC);
