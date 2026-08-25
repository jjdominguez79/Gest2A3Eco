-- Limpieza administrativa segura de datos de prueba de mensajeria.
ALTER TABLE msg_organizations
  ADD COLUMN IF NOT EXISTS is_test boolean NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS ix_msg_organizations_is_test
  ON msg_organizations(is_test);

-- Compatibilidad con las empresas de prueba historicas.
UPDATE msg_organizations
SET is_test = true
WHERE upper(trim(company_code)) IN ('E0000', 'E00000');

CREATE TABLE IF NOT EXISTS msg_cleanup_audit (
  id varchar(36) PRIMARY KEY,
  actor varchar(160) NOT NULL,
  reason varchar(500) NOT NULL,
  scope varchar(32) NOT NULL,
  filters_json text NOT NULL DEFAULT '{}',
  counts_json text NOT NULL DEFAULT '{}',
  confirmation_code varchar(32) NOT NULL,
  storage_keys_json text NOT NULL DEFAULT '[]',
  failed_storage_keys_json text NOT NULL DEFAULT '[]',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_msg_cleanup_audit_confirmation_code
  ON msg_cleanup_audit(confirmation_code);
CREATE INDEX IF NOT EXISTS ix_msg_cleanup_audit_created_at
  ON msg_cleanup_audit(created_at);
