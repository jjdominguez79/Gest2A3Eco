CREATE TABLE IF NOT EXISTS msg_invitation_content (
    id VARCHAR(36) PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(16) NOT NULL DEFAULT 'draft',
    subject VARCHAR(300) NOT NULL,
    intro_text TEXT NOT NULL,
    closing_text TEXT NOT NULL,
    manual_storage_key VARCHAR(500) NOT NULL DEFAULT '',
    manual_name VARCHAR(255) NOT NULL DEFAULT '',
    manual_sha256 VARCHAR(64) NOT NULL DEFAULT '',
    manual_size INTEGER NOT NULL DEFAULT 0,
    created_by VARCHAR(64) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_by VARCHAR(64) NOT NULL DEFAULT '',
    published_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_msg_invitation_content_version
    ON msg_invitation_content(version);
CREATE INDEX IF NOT EXISTS ix_msg_invitation_content_status
    ON msg_invitation_content(status);
CREATE UNIQUE INDEX IF NOT EXISTS ux_msg_invitation_content_active
    ON msg_invitation_content(status) WHERE status = 'published';
CREATE UNIQUE INDEX IF NOT EXISTS ux_msg_invitation_content_draft
    ON msg_invitation_content(status) WHERE status = 'draft';
CREATE UNIQUE INDEX IF NOT EXISTS ux_msg_invitation_content_version_published
    ON msg_invitation_content(version) WHERE version > 0;
