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

## Configuracion global y comunicaciones DEHu

La pestana **Configuracion global** del modulo de notificaciones guarda en
PostgreSQL una unica periodicidad para todos los buzones, el email de resumen
interno y la politica/plantilla de aviso al cliente. Solo el administrador
puede cambiarla. **Guardar y aplicar** replica la periodicidad en el backend;
la ficha del cliente conserva certificado, activacion y responsable, sin
permitir periodicidades particulares.

El resumen interno del despacho es distinto del email de comunicacion al
cliente. Este ultimo se dirige siempre al campo Email de la ficha y utiliza
su propia plantilla HTML y asunto, independientes de la plantilla de facturas.
En la bandeja se puede seleccionar con Ctrl/Mayus o **Seleccionar visibles**;
**Comunicar al cliente** publica los PDF seleccionados y, si esta habilitado,
envia un unico email por cliente con todos sus adjuntos, sin mezclar clientes.
Se registra por separado la publicacion y el estado del correo. Un fallo
seguro permite reintentar el email sin republicar los PDF; un resultado
incierto requiere comprobar el envio antes de reenviarlo.

La consulta es pasiva y excluye leidas/aceptadas/rechazadas/realizadas. No pide
la bandeja historica `realized_notifications` ni reutiliza capturas/filas DOM
cuando la API devuelve una bandeja vacia. Los resumenes enumeran solo
referencias nuevas, no todas las pendientes. La migracion backend
`023_dehu_new_notifications.sql` recuerda tambien las referencias de
resumenes anteriores y de titulares sin servicio, sin almacenar su contenido.
Un aviso descubierto por primera vez sigue siendo nuevo aunque su fecha de
puesta a disposicion sea anterior al dia de consulta.

Para activar el cambio en produccion es necesario actualizar escritorio,
backend y worker AAPP. El backend aplica la migracion al arrancar; el builder
Synology incluye el modulo compartido de estados DEHu.

## Limites deliberados

### Acceso desde el cliente Flutter

El cliente dispone de un menu lateral en la pantalla de conversaciones. La
entrada unica `Documentacion` (`/documentation`) agrupa `Mis documentos` y
`Solicitar certificados`, sin repetir esas opciones en el menu principal ni
mostrar accesos adicionales a la derecha de la cabecera. El menu incluye tambien
`Conversaciones`, `Facturacion` (si esta habilitada), `Mi area`, `Acerca de Gestinem`
y, como ultima opcion, `Cerrar sesion`.
La pantalla de certificados permite elegir el tramite y consultar `Mis solicitudes`.
Las opciones del menu conservan el inicio en el historial. `Documentacion`
dispone ademas de un boton para volver incluso si se abre por enlace directo.

El menu documental es visible aunque las funciones no esten habilitadas; en ese
caso muestra el motivo y no permite abrir el servicio deshabilitado. No activa
automaticamente los permisos globales ni los de la empresa. Para probar una
solicitud con un usuario cliente deben estar activos `CLIENT_CERTIFICATES_ENABLED`
y `client_certificates_enabled`, y el despacho debe haber preparado un certificado
digital vigente para su empresa. El catalogo mostrado procede del backend;
la presencia de un tramite no sustituye su calibracion ni una prueba real del worker.

### Restricciones de los tramites

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
