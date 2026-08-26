-- Destino activo del dispositivo para suprimir avisos del chat visible.
-- Migracion aditiva e idempotente; active_conversation_id se conserva durante
-- la transicion para clientes Flutter anteriores.

ALTER TABLE msg_app_devices
  ADD COLUMN IF NOT EXISTS active_target_type varchar(24) NOT NULL DEFAULT '';

ALTER TABLE msg_app_devices
  ADD COLUMN IF NOT EXISTS active_target_id varchar(36) NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS ix_msg_app_devices_active_target
  ON msg_app_devices(active_target_type, active_target_id);
