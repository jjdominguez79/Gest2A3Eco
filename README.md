# Gest2A3Eco

Aplicacion de escritorio para Windows, desarrollada con Python y Tkinter, que
centraliza la gestion contable y documental de Gestinem e integra los datos con
A3ECO.

Funciones principales:

- Generacion de `suenlace.dat` para movimientos bancarios y facturas.
- Gestion de facturas emitidas, recibidas, cuotas y Facturae 3.2.2.
- Generacion de PDF desde plantillas Word y firma documental.
- Captura y revision OCR de facturas recibidas.
- Comunicaciones por Microsoft Graph, mensajeria web y notificaciones.
- Gestion documental, certificados de Administraciones Publicas y tramites DGT.
- Importacion de empresas, cuentas, terceros y asientos desde ficheros A3.

Documentacion especializada:

- [Backend e integraciones](backend/README.md)
- [OCR: estado actual](docs/ocr_estado_actual.md)
- [Facturae / FACe](docs/facturae_face.md)
- [Tramites DGT](docs/implantacion_dgt_online.md)
- [Arquitectura de secretos](docs/security/secrets-architecture.md)
- [Publicacion de versiones](docs/PUBLICACION_VERSIONES.md)
- [Servicios Synology](deploy/mail-sync/README.md)
- [Cliente Flutter en preparacion](gestinem_app/README.md)

Documentacion contrastada con el repositorio el 2026-08-15.

## Requisitos y desarrollo

- Windows.
- Python 3.10 o posterior. La publicacion automatizada usa Python 3.14.2.
- PostgreSQL accesible desde los puestos de escritorio.
- Microsoft Word para la conversion de plantillas DOCX a PDF.
- Dependencias de `requirements.txt` y, para pruebas, `requirements-dev.txt`.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt

python main.py
$env:PYTHONPATH = "."
python -m pytest
```

Para las notificaciones electronicas automatizadas tambien hay que instalar el
navegador de Playwright:

```powershell
playwright install chromium
```

## Configuracion del escritorio

En una instalacion normal, la configuracion se guarda en
`%LOCALAPPDATA%\Gest2A3Eco\config.local.json`. Los antiguos `config.json` y
`config.local.json` junto al ejecutable solo se leen para migrarlos en el primer
arranque.

El JSON contiene exclusivamente valores no sensibles, entre otros:

- conexion PostgreSQL separada en `postgres_host`, `postgres_port`,
  `postgres_database` y `postgres_user`;
- rutas de A3ECO, plantillas Word y repositorio documental;
- URLs del backend para integraciones y mensajeria;
- preferencias de OCR, firma y monedas.

La contrasena PostgreSQL y el `WorkstationToken` se guardan en Windows
Credential Manager. Para provisionar un puesto:

```powershell
python -m utils.provision_workstation --only-token
```

`GEST2A3ECO_POSTGRES_DSN` sigue disponible para automatizacion y migracion, pero
un DSN con contrasena nunca se persiste en el JSON. Las API keys historicas
`dgt_api_key`, `integrations_api_key` y `messaging_api_key` no autentican al
escritorio y se eliminan al guardar la configuracion.

## Arquitectura

```text
main.py                     Arranque, actualizaciones y autenticacion
controllers/                Navegacion, validacion y coordinacion
views/                      Pantallas Tkinter
procesos/                   Registros A3ECO y generacion Word/PDF
models/                     Persistencia PostgreSQL y renderizadores A3ECO
services/                   OCR, correo, firma, DGT y gestion documental
backend/api/                API FastAPI y portales web
sync_worker/                Workers de correo y adjuntos para Synology
gestinem_app/               Scaffold Flutter para el futuro cliente movil
utils/                      Configuracion, credenciales y validaciones
```

El escritorio aplica una arquitectura MVC con servicios y procesos. El backend
FastAPI concentra los secretos de proveedores externos y expone DGT, OCR,
SignRequest, Dataprius y los portales de mensajeria. Los procesos de Synology
mantienen la sincronizacion aunque ningun usuario tenga abierta la aplicacion.
El backend ya contiene contratos para dispositivos moviles, FCM, WebSocket,
grupos y campanas; `gestinem_app/` sigue siendo un scaffold Flutter y aun no es
un cliente funcional.

## Datos y documentos

PostgreSQL es la unica base operativa del escritorio. El gestor
`models/gestor_postgres.py` inicializa una base vacia y aplica comprobaciones
aditivas de esquema al arrancar. No existe un fallback soportado a SQLite.

La distribucion es:

- **PostgreSQL principal:** empresas, usuarios, facturacion, OCR, contabilidad,
  comunicaciones, firma y gestion documental.
- **PostgreSQL del backend:** expedientes DGT, portales de mensajeria, tokens,
  auditoria y estado temporal de integraciones.
- **Repositorio documental compartido:** por defecto
  `\\GestinemMain\Doc_Compartidos\Gest2A3Eco`; contiene documentos definitivos
  que deben compartir todos los puestos.
- **Dataprius:** archivo de documentos asociados a expedientes DGT.
- **Azure Blob privado:** almacenamiento temporal de adjuntos enviados desde la
  PWA hasta que el worker los verifica y copia al repositorio compartido.

Los correos de `oficina@gestinem.es` llegan mediante Microsoft Graph y el
contenedor `mail-sync`. Se guardan en PostgreSQL sin descargar masivamente sus
adjuntos; el usuario decide cuales incorpora al repositorio documental. El
worker `messaging-sync` atiende por separado los adjuntos enviados desde la PWA.

## Compilacion y publicacion

```powershell
python -m PyInstaller --clean --noconfirm Gest2A3Eco.spec
```

La build empaqueta codigo, recursos, plantillas versionables y
`config.example.json`; no debe incluir configuracion local, secretos ni
documentos generados. La publicacion completa de una version se realiza con:

```powershell
.\publicar_version.ps1
```

El procedimiento y la recuperacion ante errores se describen en
[`docs/PUBLICACION_VERSIONES.md`](docs/PUBLICACION_VERSIONES.md).

## Convenciones

- UI en `views/`; orquestacion en `controllers/`; negocio en `services/` o
  `procesos/`; persistencia en `models/`.
- Identificadores, textos de interfaz y comentarios en espanol.
- `plantillas.json` es material de semilla, no la fuente de verdad.
- Los PDFs se generan mediante `procesos/facturas_word.py`; no hay fallback a
  PDF basico.
- Los PDFs solo se copian a la carpeta enlazada de A3ECO al generar
  `suenlace.dat`.
