-- Migracion 004: retirada de tablas exclusivas de Web Push / VAPID
-- La PWA heredada de mensajeria ha sido retirada. Flutter usa FCM (msg_app_devices),
-- no Web Push. Estas tablas no tienen claves foraneas entrantes desde otras tablas.
-- IMPORTANTE: ejecutar despues de desplegar la version que retire messaging_push.py.

-- Tabla de suscripciones Web Push del despacho
DROP TABLE IF EXISTS msg_push_subscriptions;

-- Tabla de suscripciones Web Push de clientes
DROP TABLE IF EXISTS msg_client_push_subscriptions;
