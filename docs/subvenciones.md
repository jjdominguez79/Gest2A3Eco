# Ayudas y subvenciones para clientes

## Arquitectura

El backend FastAPI es la unica fuente de verdad. Importa ayudas desde la API
abierta del BOE, canales oficiales RSS/XML de diarios autonomicos y la API
publica de la BDNS. La BDNS enriquece y deduplica las convocatorias que tambien
aparecen en un boletin; las ayudas directas que solo existen como disposicion
legal conservan su referencia BOE. Todo el detalle se almacena en PostgreSQL.
Flutter consulta el catalogo y guarda las preferencias del cliente. El
escritorio Python solo administra el servicio mediante la API y no mantiene
una copia local.

Cada registro indica fuente, referencia oficial y naturaleza (convocatoria o
ayuda directa). Una norma con varias lineas de ayuda se divide en fichas
independientes para que los destinatarios y plazos no se mezclen.

El registro incorporado de canales oficiales incluye BOE y los diarios de
Andalucia, Canarias, Cantabria, Castilla y Leon, Extremadura, Galicia, Madrid y
Pais Vasco. Las convocatorias del resto de territorios siguen entrando por la
BDNS; sus canales oficiales se pueden incorporar con
`SUBSIDIES_BULLETIN_FEEDS_JSON` cuando ofrezcan RSS o Atom reutilizable.

Los avisos reutilizan los dispositivos y Firebase Cloud Messaging de la
mensajeria. Cada pareja cliente-convocatoria tiene una entrega idempotente, por
lo que una ejecucion repetida no duplica notificaciones ya enviadas.

## Activacion

1. Aplicar el despliegue normal del backend; la migracion
   `backend/migrations/034_subvenciones.sql` y
   `backend/migrations/035_subvenciones_boletines.sql` son aditivas.
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
- `SUBSIDIES_BOE_ENABLED`: permite detener solo la ingesta BOE.
- `SUBSIDIES_REGIONAL_BULLETINS_ENABLED`: permite detener los canales
  autonomicos sin afectar a BOE o BDNS.
- `SUBSIDIES_BULLETIN_TIMEOUT`, `SUBSIDIES_BULLETIN_PAUSE` y
  `SUBSIDIES_BULLETIN_MAX_CHARS`: ajustes de descarga y extraccion.
- `SUBSIDIES_BULLETIN_FEEDS_JSON`: canales RSS/XML oficiales adicionales. Cada
  entrada contiene `codigo`, `nombre`, `ccaa` y una lista `urls`.

## Uso del cliente

El cliente dispone de dos vistas: **Para ti**, que aplica sus territorios, y
**Todas**, que permite consultar el catalogo vigente completo. En preferencias
puede incluir ayudas nacionales, usar el domicilio de la empresa y suscribirse
a comunidades autonomas, provincias o municipios adicionales.

La activacion de avisos es voluntaria. En Web, Android e iOS sigue siendo
necesario que el usuario conceda el permiso de notificaciones del sistema.

La ficha muestra la procedencia, la referencia y enlaces a las fuentes
oficiales, e indica que el resumen es orientativo y no sustituye a la
publicacion oficial.

## Operacion y recuperacion

El panel muestra la ultima ejecucion, catalogo, empresas, suscripciones y
entregas FCM. Una convocatoria puede ocultarse, marcarse como revisada o dejar
su resumen pendiente para regenerarlo. Los fallos transitorios y los clientes
sin dispositivo se reintentan; las entregas correctas no se vuelven a enviar.

Para detener el proceso sin retirar el despliegue, desactive la sincronizacion
desde el panel. Para impedir el acceso de todos los clientes, cambie
`CLIENT_SUBSIDIES_ENABLED=false`; los datos y preferencias se conservan.
