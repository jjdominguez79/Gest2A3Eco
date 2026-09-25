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

El catalogo incluye `TGSS_VIDA_LABORAL` como **Informe de vida laboral**. El
worker entra por la portada oficial de Importass, se identifica como el propio
interesado con su certificado digital y descarga el informe completo en PDF.
La solicitud puede realizarla el despacho o el cliente; si la crea el cliente,
el documento se publica automaticamente en su area documental. La opcion no
usa el acceso como apoderado y esta pensada para autonomos cuyo certificado
personal este preparado en el almacen central.

## Configuracion global, DEHu y DGT/DEV

La pestana **Configuracion global** del modulo de notificaciones guarda en
PostgreSQL una unica periodicidad para todos los buzones, la hora de Madrid
para las consultas diarias, el email de resumen interno y la politica/plantilla
de aviso al cliente. Solo el administrador puede cambiarla. La hora se escribe
en formato HH:MM cuando se elige **DIARIA**. **Guardar y aplicar** replica la
periodicidad y la hora en el backend;
la ficha del cliente conserva certificado, activacion y responsable, sin
permitir periodicidades particulares.

La consulta diaria se programa para la siguiente aparicion de esa hora en
Madrid, teniendo en cuenta el cambio de horario estacional. El worker la
encola cuando vence; la ejecucion puede comenzar unos segundos despues. La
sincronizacion manual se puede solicitar aparte y no cambia esa hora.

**Consultar metadatos** enumera las notificaciones y comunicaciones pendientes
y registra sus datos descriptivos (referencia, emisor, asunto y fechas). No
abre ni descarga el contenido, no comparece ni rechaza, y no publica un PDF
al cliente por si sola. Las etiquetas antiguas de descarga en algunos buzones
procedian de configuraciones previas; el worker actual solo consulta metadatos.

El resumen interno del despacho es distinto del email de comunicacion al
cliente. Este ultimo se dirige siempre al campo Email de la ficha y utiliza
su propia plantilla HTML y asunto, independientes de la plantilla de facturas.
En la bandeja se puede seleccionar con Ctrl/Mayus o **Seleccionar visibles**;
**Comunicar al cliente** publica los PDF seleccionados y, si esta habilitado,
envia un unico email por cliente con todos sus adjuntos, sin mezclar clientes.
Se registra por separado la publicacion y el estado del correo. Un fallo
seguro permite reintentar el email sin republicar los PDF; un resultado
incierto requiere comprobar el envio antes de reenviarlo.

La consulta es pasiva. DEHu lee pendientes y una ventana movil de realizadas
para actualizar como leida, aceptada, rechazada o caducada una referencia ya
controlada. Si una notificacion se lee directamente en el portal antes de la
primera sincronizacion, tambien se incorpora cuando su puesta a disposicion es
posterior al alta del buzon. Las realizadas anteriores a la activacion no se
incorporan de golpe: el historico es incremental y nunca se purga porque una
referencia deje de aparecer en el portal. Los resumenes enumeran solo
referencias nuevas, no todas las pendientes. La migracion backend
`023_dehu_new_notifications.sql` recuerda tambien las referencias de
resumenes anteriores y de titulares sin servicio, sin almacenar su contenido;
`029_dehu_activation_history.sql` fija el inicio del historico incremental.
Un aviso descubierto por primera vez sigue siendo nuevo aunque su fecha de
puesta a disposicion sea anterior al dia de consulta.

La pantalla **Buzones y sincronizacion** muestra DEHu y DGT/DEV para todos los
clientes, incluso cuando aun no existe una configuracion local. Admite seleccion
multiple para activar o desactivar buzones. Cada fila activa genera su propia
consulta con el certificado del cliente; nunca se reutiliza el certificado de
otro titular. DGT/DEV conserva igualmente un historico incremental desde la
fecha de activacion y muestra **No alta DEV** cuando el portal identifica el
certificado pero el titular no esta suscrito. La consulta se limita al listado:
no abre, acepta, rechaza ni descarga notificaciones.

El acceso DGT/DEV se valido en modo de solo lectura con E00006 el 22/09/2026:
el certificado autentico correctamente y la bandeja no contenia avisos en los
ultimos 180 dias. La migracion `028_dev_notifications.sql` crea la programacion
y el historico central de este segundo buzon.

Para activar el cambio en produccion es necesario actualizar escritorio,
backend y worker AAPP. El backend aplica las migraciones al arrancar; el builder
Synology incluye ambos conectores y el modulo compartido de estados.

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
2. Validar `TGSS_VIDA_LABORAL` con un certificado personal de autonomo, primero
   con navegador visible y despues en el contenedor headless.
3. Incorporar rotacion de la clave maestra y auditoria detallada de operaciones
   sobre el almacen central.
4. Descarga segura de documentos DEHu sin comparecencia cuando el portal lo
   permita.
5. Finalizacion y pruebas de cada tramite AEAT/TGSS por separado.
6. Comparecencia DEHu con confirmacion reforzada, justificante y verificacion
   posterior del estado remoto.
