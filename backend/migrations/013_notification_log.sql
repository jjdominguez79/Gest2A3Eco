-- Registro de intentos de entrega de notificaciones por factura.
-- Garantiza idempotencia y evita duplicados ante reintentos o concurrencia.
CREATE TABLE IF NOT EXISTS client_invoice_notification_log (
    id          SERIAL PRIMARY KEY,
    invoice_id  VARCHAR(36) NOT NULL REFERENCES client_invoices(id) ON DELETE CASCADE,
    -- 'email' | 'fcm'
    notification_type VARCHAR(10) NOT NULL,
    -- email: direccion del destinatario; fcm: token del dispositivo
    recipient   VARCHAR(500) NOT NULL DEFAULT '',
    -- pending | sending | sent | skipped | failed
    status      VARCHAR(20)  NOT NULL DEFAULT 'pending',
    detail      TEXT         NOT NULL DEFAULT '',
    attempt_count INT        NOT NULL DEFAULT 1,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_notif_log UNIQUE (invoice_id, notification_type, recipient)
);
CREATE INDEX IF NOT EXISTS ix_notif_log_invoice ON client_invoice_notification_log(invoice_id);
