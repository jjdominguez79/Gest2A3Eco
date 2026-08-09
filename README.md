# Gest2A3Eco

Aplicacion de escritorio en Python/Tkinter para Windows orientada a gestion
contable de Gestinem.

Funciones principales:

- Generacion de `suenlace.dat` para A3ECO.
- Gestion de facturas emitidas y recibidas.
- Generacion de PDF desde plantillas Word.
- OCR de facturas recibidas.
- Comunicaciones, notificaciones, firma documental y tramites DGT.

## Requisitos

- Python 3.10+
- Windows
- PostgreSQL accesible desde todos los puestos
- Dependencias de `requirements.txt`

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Ejecucion

```bash
python main.py
```

La conexion de datos se configura con `postgres_dsn` en `config.local.json` o
con la variable `GEST2A3ECO_POSTGRES_DSN`.

## Compilacion

```bash
pyinstaller Gest2A3Eco.spec
```

La build empaqueta recursos de aplicacion como `logo.png`, `icono.ico`,
`assets/`, `plantillas/email_factura.html` y `config.example.json`. No debe
incluir datos reales, configuracion local ni documentos generados.

## Arquitectura

```text
main.py                     Punto de entrada
controllers/                Coordinacion y validacion
views/                      Pantallas Tkinter
procesos/                   Generadores A3ECO y PDF
models/                     Gestor PostgreSQL y renderizadores A3ECO
services/                   Auth, email, OCR, notificaciones, integraciones
utils/                      Configuracion, validaciones y formato
plantillas/                 Plantillas versionables
assets/                     Recursos graficos
```

## Datos

PostgreSQL es la unica base operativa. No hay flujo soportado con bases locales
en fichero. El gestor PostgreSQL inicializa el esquema si la base esta vacia y
aplica comprobaciones aditivas necesarias al arrancar.

Los documentos generados se almacenan en rutas compartidas de red configuradas
para que todos los equipos trabajen sobre la misma informacion.

### Distribucion de datos y servicios

- **Base principal de la aplicacion:** PostgreSQL en la maquina virtual de red.
  Todos los puestos de escritorio se conectan a esta base mediante
  `postgres_dsn`.
- **Repositorio documental:** rutas compartidas de red, por defecto
  `\\GestinemMain\Doc_Compartidos\Gest2A3Eco`. Aqui se guardan documentos,
  adjuntos importados, PDFs y evidencias que deben compartir todos los equipos.
- **Backend de integraciones:** un unico proyecto Railway sirve Tramites DGT,
  firma documental, mensajeria y los conectores remotos. Se configura con
  `integrations_api_url` e `integrations_api_key`; las claves historicas
  `dgt_api_url` y `dgt_api_key` siguen aceptandose por compatibilidad.
- **Tramites DGT:** no usa la base principal para expedientes. Este backend
  usa su propia PostgreSQL mediante
  `DGT_DATABASE_URL`. En la base principal solo se conserva el vinculo contable
  `dgt_facturas` cuando un expediente remoto genera una factura local. Los
  documentos aportados o generados para el tramite se archivan en Dataprius bajo
  la carpeta del expediente, con metadatos registrados en Railway.
- **Comunicaciones / Microsoft Graph:** los mensajes se almacenan en la base
  principal, en tablas `comunicaciones_*`. La sincronizacion automatica no
  depende de que un usuario tenga abierta la aplicacion: la realiza el
  contenedor `mail-sync` del NAS/Synology.
- **Contenedor NAS `mail-sync`:** no tiene base de datos propia ni estado
  persistente relevante. Lee `oficina@gestinem.es` con Microsoft Graph usando
  credenciales de aplicacion/certificado y escribe los mensajes nuevos en la
  PostgreSQL principal. El cursor incremental de Graph se guarda en
  `comunicaciones_sync`.

### Comunicaciones: almacenamiento de mensajes

El flujo de entrada de correo es:

```text
Microsoft Graph / oficina@gestinem.es
  -> contenedor NAS mail-sync
  -> PostgreSQL principal
      -> comunicaciones_sin_asignar     correos nuevos pendientes de asignar
      -> comunicaciones                 conversaciones ya asignadas a cliente
      -> comunicaciones_mensajes        mensajes entrantes/salientes
      -> comunicaciones_adjuntos        adjuntos importados desde correo
      -> comunicaciones_sync            delta_link y ultimo estado de sync
      -> comunicaciones_adjuntos_decisiones
      -> documentos_archivo             documentos archivados en repositorio comun
```

La sincronizacion guarda metadatos y cuerpo HTML del mensaje. Los adjuntos no se
descargan de forma masiva durante la sincronizacion: se listan bajo demanda y se
guardan en el repositorio documental comun solo cuando el usuario decide
importarlos.

## Convenciones

- UI en `views/`.
- Logica de negocio en `controllers/`, `services/` o `procesos/`.
- Persistencia en `models/gestor_postgres.py`.
- Los PDFs se generan siempre con `procesos/facturas_word.py`.
- La carpeta A3ECO solo recibe PDFs durante la generacion de `suenlace.dat`.
