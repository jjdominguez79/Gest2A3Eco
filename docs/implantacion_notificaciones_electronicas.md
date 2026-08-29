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

## Limites deliberados

- Los botones de comparecencia y rechazo no modifican el estado: falta el flujo
  remoto con confirmacion y justificante de DEHu.
- Una notificacion solo se puede publicar en Flutter cuando existe un PDF real.
- La periodicidad configurada todavia no dispone de un worker AAPP autonomo.
- Los recorridos de las sedes AEAT/TGSS requieren calibracion y pruebas con
  certificados autorizados antes de considerarse productivos.

## Siguientes incrementos

1. Almacen central cifrado de PFX y contrasenas, con rotacion y auditoria.
2. Worker autonomo con bloqueos por cliente, periodicidad, reintentos y alertas.
3. Descarga segura de documentos DEHu sin comparecencia cuando el portal lo
   permita.
4. Finalizacion y pruebas de cada tramite AEAT/TGSS por separado.
5. Comparecencia DEHu con confirmacion reforzada, justificante y verificacion
   posterior del estado remoto.
