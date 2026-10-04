# Ayudas y subvenciones para clientes

## Arquitectura

El backend FastAPI es la unica fuente de verdad. Importa convocatorias de la
API publica de la BDNS, clasifica su alcance territorial y conserva el detalle
oficial en PostgreSQL. Flutter consulta el catalogo y guarda las preferencias
del cliente. El escritorio Python solo administra el servicio mediante la API;
no mantiene una copia local.

Los avisos reutilizan los dispositivos y Firebase Cloud Messaging de la
mensajeria. Cada pareja cliente-convocatoria tiene una entrega idempotente, por
lo que una ejecucion repetida no duplica notificaciones ya enviadas.

## Activacion

1. Aplicar el despliegue normal del backend; la migracion
   `backend/migrations/034_subvenciones.sql` es aditiva.
2. Definir `CLIENT_SUBSIDIES_ENABLED=true` en el servicio web de Railway.
3. Crear un servicio cron con `railway.subvenciones.toml`. La programacion
   incluida se ejecuta diariamente a las 05:15 UTC.
4. En el escritorio, abrir **Gestiones > Ayudas y subvenciones** y habilitar el
   servicio. Los avisos y los resumenes IA permanecen desactivados hasta que un
   administrador los active expresamente.
5. En la pestaña **Empresas**, habilitar gradualmente los clientes que deban
   ver la funcionalidad.

Variables opcionales:

- `ANTHROPIC_API_KEY`: habilita la posibilidad de generar resumenes.
- `SUBSIDIES_AI_MODEL`: modelo usado para los resumenes.
- `SUBSIDIES_BDNS_TIMEOUT`, `SUBSIDIES_BDNS_PAUSE` y
  `SUBSIDIES_BDNS_PAGE_SIZE`: ajustes operativos de la ingesta.
- `SUBSIDIES_INITIAL_DAYS`: ventana inicial, 14 dias por defecto.

## Uso del cliente

El cliente dispone de dos vistas: **Para ti**, que aplica sus territorios, y
**Todas**, que permite consultar el catalogo vigente completo. En preferencias
puede incluir ayudas nacionales, usar el domicilio de la empresa y suscribirse
a comunidades autonomas, provincias o municipios adicionales.

La activacion de avisos es voluntaria. En Web, Android e iOS sigue siendo
necesario que el usuario conceda el permiso de notificaciones del sistema.

La ficha muestra siempre enlaces a las fuentes oficiales e indica que el
resumen es orientativo y no sustituye a la convocatoria.

## Operacion y recuperacion

El panel muestra la ultima ejecucion, catalogo, empresas, suscripciones y
entregas FCM. Una convocatoria puede ocultarse, marcarse como revisada o dejar
su resumen pendiente para regenerarlo. Los fallos transitorios y los clientes
sin dispositivo se reintentan; las entregas correctas no se vuelven a enviar.

Para detener el proceso sin retirar el despliegue, desactive la sincronizacion
desde el panel. Para impedir el acceso de todos los clientes, cambie
`CLIENT_SUBSIDIES_ENABLED=false`; los datos y preferencias se conservan.
