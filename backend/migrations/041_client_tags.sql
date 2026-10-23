-- Etiquetas internas de clientes, administradas exclusivamente desde escritorio.
CREATE TABLE IF NOT EXISTS msg_client_tags (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    color VARCHAR(7) NOT NULL DEFAULT '#6750A4',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_msg_client_tags_name_lower
    ON msg_client_tags(LOWER(name));
CREATE INDEX IF NOT EXISTS ix_msg_client_tags_active
    ON msg_client_tags(active);

CREATE TABLE IF NOT EXISTS msg_organization_tags (
    organization_id VARCHAR(36) NOT NULL
        REFERENCES msg_organizations(id) ON DELETE CASCADE,
    tag_id VARCHAR(36) NOT NULL
        REFERENCES msg_client_tags(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (organization_id, tag_id)
);

CREATE INDEX IF NOT EXISTS ix_msg_organization_tags_tag
    ON msg_organization_tags(tag_id, organization_id);
