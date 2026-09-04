ALTER TABLE msg_organizations
    ADD COLUMN IF NOT EXISTS logo_storage_key VARCHAR(500) NOT NULL DEFAULT '';

ALTER TABLE msg_organizations
    ADD COLUMN IF NOT EXISTS logo_content_type VARCHAR(120) NOT NULL DEFAULT '';
