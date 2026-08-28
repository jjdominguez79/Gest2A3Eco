-- Agrega token de propiedad atomica al log de notificaciones.
-- claim_token: hex aleatorio de 16 bytes escrito en la adquisicion (INSERT/UPDATE ... RETURNING).
-- claimed_at: timestamp de la adquisicion, util para detectar leases expirados.
ALTER TABLE client_invoice_notification_log
    ADD COLUMN IF NOT EXISTS claim_token VARCHAR(64) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;
