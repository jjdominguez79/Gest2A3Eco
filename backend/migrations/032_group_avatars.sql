-- Avatar configurable para los grupos internos y las listas de campana.
ALTER TABLE msg_groups
    ADD COLUMN IF NOT EXISTS avatar_storage_key VARCHAR(500) NOT NULL DEFAULT '';
ALTER TABLE msg_groups
    ADD COLUMN IF NOT EXISTS avatar_content_type VARCHAR(120) NOT NULL DEFAULT '';
