-- La privacidad de lectura no altera recibos ni contadores personales.
ALTER TABLE msg_staff ADD COLUMN IF NOT EXISTS mostrar_lecturas_clientes BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE msg_staff ADD COLUMN IF NOT EXISTS mostrar_lecturas_empleados BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE msg_events ADD COLUMN IF NOT EXISTS actor_type VARCHAR(16) NOT NULL DEFAULT '';
ALTER TABLE msg_events ADD COLUMN IF NOT EXISTS actor_id VARCHAR(64) NOT NULL DEFAULT '';
-- El administrador siempre consulta los estados, aunque desactivara el ajuste antiguo.
UPDATE msg_staff SET mostrar_estados_mensajes=TRUE WHERE role='admin';
