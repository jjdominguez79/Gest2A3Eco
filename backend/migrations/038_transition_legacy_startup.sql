-- 038_transition_legacy_startup.sql
-- Consolida el DDL adicional que el startup historico aplicaba en cada arranque.
-- Despues de esta migracion, run_migrations() ya no invoca _run_startup_ddl(),
-- _create_initial_channels() ni Base.metadata.create_all() en condiciones normales.
-- Usa ADD COLUMN IF NOT EXISTS para ser segura tanto en bases existentes (baseline)
-- como en instalaciones nuevas que llegaron aqui via 001-037.

-- ── msg_staff ──────────────────────────────────────────────────────────────────
ALTER TABLE msg_staff ADD COLUMN IF NOT EXISTS email               VARCHAR(254)  NOT NULL DEFAULT '';
ALTER TABLE msg_staff ADD COLUMN IF NOT EXISTS entra_oid           VARCHAR(64)   NOT NULL DEFAULT '';
ALTER TABLE msg_staff ADD COLUMN IF NOT EXISTS desktop_user_id     VARCHAR(64)   NOT NULL DEFAULT '';
ALTER TABLE msg_staff ADD COLUMN IF NOT EXISTS chat_alias          VARCHAR(160)  NOT NULL DEFAULT '';
ALTER TABLE msg_staff ADD COLUMN IF NOT EXISTS mostrar_estados_mensajes BOOLEAN  NOT NULL DEFAULT TRUE;
ALTER TABLE msg_staff ADD COLUMN IF NOT EXISTS avatar_storage_key  VARCHAR(500)  NOT NULL DEFAULT '';
ALTER TABLE msg_staff ADD COLUMN IF NOT EXISTS avatar_content_type VARCHAR(120)  NOT NULL DEFAULT '';
ALTER TABLE msg_staff ADD COLUMN IF NOT EXISTS password_hash       VARCHAR(300)  NOT NULL DEFAULT '';
ALTER TABLE msg_staff ADD COLUMN IF NOT EXISTS review_only         BOOLEAN       NOT NULL DEFAULT FALSE;

-- ── msg_messages ───────────────────────────────────────────────────────────────
ALTER TABLE msg_messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMPTZ;

-- ── msg_staff_thread_messages ──────────────────────────────────────────────────
ALTER TABLE msg_staff_thread_messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMPTZ;

-- ── dgt_documentos ─────────────────────────────────────────────────────────────
ALTER TABLE dgt_documentos ADD COLUMN IF NOT EXISTS dataprius_json JSONB NOT NULL DEFAULT '{}';

-- ── msg_organizations ──────────────────────────────────────────────────────────
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS tax_id                   VARCHAR(20)  NOT NULL DEFAULT '';
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS legal_name               VARCHAR(200) NOT NULL DEFAULT '';
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS address                  VARCHAR(300) NOT NULL DEFAULT '';
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS postal_code              VARCHAR(10)  NOT NULL DEFAULT '';
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS city                     VARCHAR(100) NOT NULL DEFAULT '';
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS province                 VARCHAR(100) NOT NULL DEFAULT '';
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS country                  VARCHAR(60)  NOT NULL DEFAULT 'ES';
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS phone                    VARCHAR(30)  NOT NULL DEFAULT '';
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS email                    VARCHAR(254) NOT NULL DEFAULT '';
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS logo_storage_key         VARCHAR(500) NOT NULL DEFAULT '';
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS logo_content_type        VARCHAR(120) NOT NULL DEFAULT '';
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS logo_sha256              VARCHAR(64)  NOT NULL DEFAULT '';
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS profile_synced_at        TIMESTAMPTZ;
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS client_invoicing_enabled    BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS client_documents_enabled    BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS client_certificates_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS client_subsidies_enabled    BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE msg_organizations ADD COLUMN IF NOT EXISTS is_test BOOLEAN NOT NULL DEFAULT FALSE;

-- ── msg_app_devices ────────────────────────────────────────────────────────────
ALTER TABLE msg_app_devices ADD COLUMN IF NOT EXISTS active_target_type VARCHAR(24) NOT NULL DEFAULT '';
ALTER TABLE msg_app_devices ADD COLUMN IF NOT EXISTS active_target_id   VARCHAR(36) NOT NULL DEFAULT '';

-- ── msg_websocket_tickets ──────────────────────────────────────────────────────
ALTER TABLE msg_websocket_tickets ADD COLUMN IF NOT EXISTS staff_session_id VARCHAR(36)
    REFERENCES msg_staff_sessions(id) ON DELETE CASCADE;

-- ── msg_attachments ────────────────────────────────────────────────────────────
ALTER TABLE msg_attachments ADD COLUMN IF NOT EXISTS withdrawn_at       TIMESTAMPTZ;
ALTER TABLE msg_attachments ADD COLUMN IF NOT EXISTS withdrawn_by       VARCHAR(64)  NOT NULL DEFAULT '';
ALTER TABLE msg_attachments ADD COLUMN IF NOT EXISTS withdrawal_reason  VARCHAR(500) NOT NULL DEFAULT '';
ALTER TABLE msg_attachments ADD COLUMN IF NOT EXISTS internal_message_id VARCHAR(36)
    REFERENCES msg_staff_thread_messages(id) ON DELETE CASCADE;
ALTER TABLE msg_attachments ALTER COLUMN message_id DROP NOT NULL;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_msg_attachments_single_parent') THEN
    ALTER TABLE msg_attachments ADD CONSTRAINT ck_msg_attachments_single_parent
      CHECK ((message_id IS NOT NULL AND internal_message_id IS NULL) OR
             (message_id IS NULL AND internal_message_id IS NOT NULL));
  END IF;
END $$;

-- ── msg_downloads ──────────────────────────────────────────────────────────────
ALTER TABLE msg_downloads ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

-- ── msg_conversations ──────────────────────────────────────────────────────────
ALTER TABLE msg_conversations ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;

-- ── msg_staff_app_codes ────────────────────────────────────────────────────────
ALTER TABLE msg_staff_app_codes ADD COLUMN IF NOT EXISTS purpose VARCHAR(32) NOT NULL DEFAULT 'mobile';

-- ── msg_cleanup_audit ──────────────────────────────────────────────────────────
ALTER TABLE msg_cleanup_audit ADD COLUMN IF NOT EXISTS storage_keys_json TEXT NOT NULL DEFAULT '[]';

-- ── Indices ────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_msg_staff_email             ON msg_staff(email);
CREATE INDEX IF NOT EXISTS ix_msg_staff_entra_oid         ON msg_staff(entra_oid);
CREATE INDEX IF NOT EXISTS ix_msg_staff_desktop_user_id   ON msg_staff(desktop_user_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_msg_staff_desktop_user_id_asignado ON msg_staff(desktop_user_id) WHERE desktop_user_id <> '';
CREATE UNIQUE INDEX IF NOT EXISTS ux_msg_staff_entra_oid_asignado       ON msg_staff(entra_oid)       WHERE entra_oid       <> '';
CREATE INDEX IF NOT EXISTS idx_msg_downloads_completed                   ON msg_downloads(attachment_id, completed_at);
CREATE INDEX IF NOT EXISTS ix_msg_conversations_started_at               ON msg_conversations(started_at DESC);
CREATE INDEX IF NOT EXISTS ix_msg_attachments_internal_message_id        ON msg_attachments(internal_message_id);
CREATE INDEX IF NOT EXISTS ix_msg_websocket_tickets_staff_session_id     ON msg_websocket_tickets(staff_session_id);
CREATE INDEX IF NOT EXISTS ix_msg_app_devices_active_target              ON msg_app_devices(active_target_type, active_target_id);
CREATE INDEX IF NOT EXISTS ix_msg_organizations_is_test                  ON msg_organizations(is_test);
-- Indices ausentes en produccion: estaban en ficheros 009, 010 y 037 que se
-- registraron via baseline sin ejecutarse. Se crean aqui idempotentemente.
CREATE INDEX IF NOT EXISTS ix_client_documents_org  ON client_documents(organization_id);
CREATE INDEX IF NOT EXISTS ix_client_invoices_org   ON client_invoices(organization_id);
CREATE INDEX IF NOT EXISTS ix_msg_staff_thread_mentions_message ON msg_staff_thread_mentions(internal_message_id);
CREATE INDEX IF NOT EXISTS ix_msg_staff_thread_mentions_staff   ON msg_staff_thread_mentions(mentioned_staff_external_id);

-- ── Backfills idempotentes ─────────────────────────────────────────────────────
UPDATE msg_staff AS s SET entra_oid = s.external_id
WHERE s.entra_oid = '' AND s.email <> '' AND EXISTS (
    SELECT 1 FROM msg_staff_sessions ss WHERE ss.staff_external_id = s.external_id);

UPDATE msg_organizations SET is_test = TRUE
WHERE UPPER(TRIM(company_code)) IN ('E0000', 'E00000');

UPDATE msg_conversations AS c
SET started_at = COALESCE((
    SELECT MIN(m.created_at) FROM msg_messages m WHERE m.conversation_id = c.id
), c.updated_at)
WHERE c.started_at IS NULL AND EXISTS (
    SELECT 1 FROM msg_messages m WHERE m.conversation_id = c.id);

-- ── Canales iniciales (TODAS las organizaciones, activas e inactivas) ──────────
-- Se ejecuta una sola vez gracias al sistema de migraciones.
-- No filtra por active=TRUE: se crea el canal para todas las organizaciones
-- independientemente de su estado.
INSERT INTO msg_conversations
    (id, organization_id, kind, state, assigned_staff_external_id, created_at, updated_at)
SELECT gen_random_uuid()::text, id, 'general', 'pendiente', '', NOW(), NOW()
FROM msg_organizations
WHERE NOT EXISTS (
    SELECT 1 FROM msg_conversations c
    WHERE c.organization_id = msg_organizations.id AND c.kind = 'general'
);

INSERT INTO msg_conversations
    (id, organization_id, kind, state, assigned_staff_external_id, created_at, updated_at)
SELECT gen_random_uuid()::text, id, 'private', 'pendiente', '', NOW(), NOW()
FROM msg_organizations
WHERE NOT EXISTS (
    SELECT 1 FROM msg_conversations c
    WHERE c.organization_id = msg_organizations.id AND c.kind = 'private'
);
