-- Fecha de alta efectiva para mantener un historico DEHu incremental.
ALTER TABLE client_dehu_mailbox_configs
    ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ NOT NULL DEFAULT now();
