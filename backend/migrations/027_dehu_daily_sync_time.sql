-- Hora local de Madrid para la consulta diaria de buzones DEHu.
ALTER TABLE client_dehu_mailbox_configs
    ADD COLUMN IF NOT EXISTS daily_sync_time VARCHAR(5) NOT NULL DEFAULT '';
