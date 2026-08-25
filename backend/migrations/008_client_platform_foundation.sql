-- 008_client_platform_foundation.sql
-- Extiende msg_organizations con datos de perfil empresarial y prepara
-- la infraestructura comun para el area documental y la facturacion online.
--
-- Idempotente: cada sentencia usa IF NOT EXISTS o equivalent.

-- ---------- Perfil empresarial en msg_organizations ----------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'msg_organizations' AND column_name = 'tax_id'
    ) THEN
        ALTER TABLE msg_organizations ADD COLUMN tax_id VARCHAR(20) NOT NULL DEFAULT '';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'msg_organizations' AND column_name = 'legal_name'
    ) THEN
        ALTER TABLE msg_organizations ADD COLUMN legal_name VARCHAR(200) NOT NULL DEFAULT '';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'msg_organizations' AND column_name = 'address'
    ) THEN
        ALTER TABLE msg_organizations ADD COLUMN address VARCHAR(300) NOT NULL DEFAULT '';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'msg_organizations' AND column_name = 'postal_code'
    ) THEN
        ALTER TABLE msg_organizations ADD COLUMN postal_code VARCHAR(10) NOT NULL DEFAULT '';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'msg_organizations' AND column_name = 'city'
    ) THEN
        ALTER TABLE msg_organizations ADD COLUMN city VARCHAR(100) NOT NULL DEFAULT '';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'msg_organizations' AND column_name = 'province'
    ) THEN
        ALTER TABLE msg_organizations ADD COLUMN province VARCHAR(100) NOT NULL DEFAULT '';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'msg_organizations' AND column_name = 'country'
    ) THEN
        ALTER TABLE msg_organizations ADD COLUMN country VARCHAR(60) NOT NULL DEFAULT 'ES';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'msg_organizations' AND column_name = 'phone'
    ) THEN
        ALTER TABLE msg_organizations ADD COLUMN phone VARCHAR(30) NOT NULL DEFAULT '';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'msg_organizations' AND column_name = 'email'
    ) THEN
        ALTER TABLE msg_organizations ADD COLUMN email VARCHAR(254) NOT NULL DEFAULT '';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'msg_organizations' AND column_name = 'profile_synced_at'
    ) THEN
        ALTER TABLE msg_organizations ADD COLUMN profile_synced_at TIMESTAMPTZ;
    END IF;

    -- Feature flag: facturacion online desactivada por defecto
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'msg_organizations' AND column_name = 'client_invoicing_enabled'
    ) THEN
        ALTER TABLE msg_organizations ADD COLUMN client_invoicing_enabled BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;

    -- Feature flag: area documental
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'msg_organizations' AND column_name = 'client_documents_enabled'
    ) THEN
        ALTER TABLE msg_organizations ADD COLUMN client_documents_enabled BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
END $$;
