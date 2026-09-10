# Implantacion de notificaciones electronicas y certificados AAPP

## Decision funcional

Cada empresa utiliza su propio certificado digital PFX/P12. No se emplea el
certificado del despacho como gran receptor. Un certificado de representante
se puede asociar a una empresa, pero la aplicacion advierte cuando el NIF del
titular no coincide con el NIF de la ficha.

## Primer incremento

- Recepcion de metadatos de notificaciones desde DEHu con el certificado del
  cliente, sin comparecer ni rechazar automaticamente.
- Solicitud de certificados AEAT y TGSS desde la pantalla global.
- Registro del resultado y del PDF obtenido en PostgreSQL.
- Publicacion manual del PDF en el area documental del cliente mediante el
  backend. Flutter lo muestra usando el contrato `client_documents` existente.
- Tipos documentales publicados:
  - `notificacion_dehu`
  - `certificado_aeat`
  - `certificado_tgss`
- Idempotencia por `source_system=desktop_aapp`, identificador local y hash del
  PDF.

## Cola central y futuro autoservicio

El backend es la fuente de verdad de las solicitudes que deben poder originar
tanto el escritorio como Flutter. La tabla `client_certificate_requests`
registra empresa, solicitante, tipo, parametros, estado, reintentos y documento
resultante. El certificado privado no forma parte de ninguna respuesta al
cliente.

La API ya contempla:

- catalogo de tipos disponibles;
- alta, listado, consulta y cancelacion por el cliente;
- alta interna desde el escritorio;
- claim exclusivo del siguiente trabajo por el worker;
- finalizacion con un documento del mismo cliente;
- error definitivo, intervencion requerida o reintento programado.

El autoservicio usa dos interruptores y nace desactivado: el global
`CLIENT_CERTIFICATES_ENABLED` y `client_certificates_enabled` por empresa.

## Custodia y worker

El escritorio dispone de la accion **Preparar para app / worker**. Esta envia
el PFX por HTTPS, el backend valida que contiene certificado y clave privada y
lo guarda en un contenedor independiente dentro de un sobre AES-256-GCM. La
contrasena forma parte del mismo sobre cifrado; PostgreSQL solo contiene la
referencia, vigencia, titular, huella y otros metadatos no secretos.

El worker `aapp_worker/` usa una credencial exclusiva, reclama una solicitud y
solo entonces obtiene el material. El PFX se escribe en un directorio temporal,
se ejecuta el conector, se publica el PDF en `client_documents` y se elimina el
temporal. Una caida del worker permite reclamar de nuevo el trabajo tras quince
minutos.

Flutter ya incluye la pantalla **Certificados oficiales** para consultar la
vigencia, crear y cancelar solicitudes, seguir su estado y abrir el documento
resultante. El PFX y la contrasena nunca forman parte de una respuesta cliente.

## Limites deliberados

- Los botones de comparecencia y rechazo no modifican el estado: falta el flujo
  remoto con confirmacion y justificante de DEHu.
- Una notificacion solo se puede publicar en Flutter cuando existe un PDF real.
- Los recorridos de las sedes AEAT/TGSS requieren calibracion y pruebas con
  certificados autorizados antes de considerarse productivos.
- El worker existe, pero no debe desplegarse para clientes reales hasta cerrar
  la calibracion de cada tramite del catalogo.

## Siguientes incrementos

1. Ejecutar el piloto completo con `AEAT_CORRIENTE` y `TGSS_CORRIENTE`, primero
   con navegador visible y despues en el contenedor headless.
2. Incorporar rotacion de la clave maestra y auditoria detallada de operaciones
   sobre el almacen central.
3. Descarga segura de documentos DEHu sin comparecencia cuando el portal lo
   permita.
4. Finalizacion y pruebas de cada tramite AEAT/TGSS por separado.
5. Comparecencia DEHu con confirmacion reforzada, justificante y verificacion
   posterior del estado remoto.
