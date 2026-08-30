# AGENTS.md

Guidance for coding agents working in this repository. Verified against the
repository on 2026-08-18. PWA de mensajeria retirada en esta version.

## Project Overview

Gest2A3Eco is a Windows desktop accounting and document-management application
built with Python, Tkinter and PostgreSQL. It generates A3ECO `suenlace.dat`
files and manages invoicing, OCR review, communications, signatures, public
administration certificates and DGT procedures.

The repository also contains a FastAPI backend and two Synology workers. The
backend owns provider secrets and serves DGT, OCR, SignRequest, Dataprius and
messaging API flows. The workers synchronize Microsoft Graph mail and messaging
attachments without requiring the desktop application to be open.

**La PWA heredada de mensajeria (`/mensajes`, `/equipo/mensajes`) ha sido retirada.**
FastAPI ya no sirve ninguna interfaz web de mensajeria. Flutter es el unico
cliente de interfaz previsto para mensajeria. Los adjuntos de mensajeria
proceden del cliente Flutter, no de ninguna PWA.

`gestinem_app/` es el proyecto Flutter para el cliente movil de mensajeria.
Los contratos backend existen antes de que la UI Flutter los consuma;
no describas el scaffold como una aplicacion terminada.

## Development Commands

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt

python main.py
$env:PYTHONPATH = "."
python -m pytest
python -m PyInstaller --clean --noconfirm Gest2A3Eco.spec

Set-Location gestinem_app
flutter pub get
flutter test
```

The release workflow builds with Python 3.14.2. The supported source baseline
is Python 3.10 or newer.

## Architecture

| Layer | Directory | Role |
|---|---|---|
| Views | `views/ui_*.py` | Tkinter screens; UI only |
| Controllers | `controllers/*.py` | Navigation, validation and orchestration |
| Services | `services/*.py` | OCR, mail, signatures, DGT and integrations |
| Processes | `procesos/*.py` | A3ECO records and Word/PDF generation |
| Models | `models/` | PostgreSQL access and A3ECO renderers |
| Backend | `backend/api/` | FastAPI integrations and web portals |
| Workers | `sync_worker/` | Synology mail and attachment synchronization |
| Mobile | `gestinem_app/` | Cliente Flutter de mensajeria (en desarrollo, no funcional aun) |
| Utilities | `utils/` | Configuration, credentials and validation |

Entry point: `main.py`. The company workspace is coordinated by
`controllers/app_controller.py`.

## Data and Configuration

PostgreSQL is the only application database. Do not add SQLite or other local
file-database fallbacks. Schema initialization and additive checks belong in
`models/gestor_postgres.py`. The DGT/messaging backend uses its own PostgreSQL
through `BACKEND_DATABASE_URL`.

Desktop configuration lives in
`%LOCALAPPDATA%\Gest2A3Eco\config.local.json`. It must contain only non-secret
values. PostgreSQL credentials and the workstation token belong in Windows
Credential Manager; `utils/credential_store.py` is the source of truth. Legacy
API keys must not be restored as desktop authentication mechanisms.

Documents shared by workstations belong under the configured network document
repository. Temporary cloud storage is not the definitive archive.

## Mensajeria: estado post-retirada PWA

- FastAPI solo proporciona API REST, WebSocket, FCM, almacenamiento y auth.
- No hay interfaz web de mensajeria. `/mensajes` y `/equipo/mensajes` devuelven 410.
- Los service workers de retirada en `/mensajes-sw.js` y `/equipo/mensajes-sw.js`
  son **transitorios**: eliminarlos 60 dias despues del despliegue de esta version.
- Web Push/VAPID (`pywebpush`, `MESSAGING_VAPID_*`) eliminados. Notificaciones
  via Firebase Cloud Messaging (FCM) unicamente.
- La aplicacion de escritorio ya no abre ninguna URL de mensajeria web.
- Invitaciones y recuperacion de contrasena usan deep links del cliente Flutter
  bajo `es.gestinem.app://auth/...`.
- La migracion `004_remove_web_push.sql` elimina `msg_push_subscriptions` y
  `msg_client_push_subscriptions`. Aplicar en produccion despues de este despliegue.

## Conventions

- Use Spanish identifiers, UI text and comments.
- Keep source ASCII unless the edited file already requires Unicode.
- UI belongs in `views/`; business logic in `controllers/`, `services/` or
  `procesos/`; data access in `models/`.
- Access application data through the PostgreSQL gestor exposed by
  `models/gestor_postgres.py`.
- Treat `plantillas.json` as seed/template material only.
- Generate PDFs through `procesos/facturas_word.py`; there is no supported
  basic-PDF fallback.
- Copy PDFs to the A3ECO linked folder only while generating `suenlace.dat`.
- Never persist provider secrets, workstation tokens or DSNs with passwords in
  JSON files.
- Preserve the Windows target and test both source and frozen path behavior
  when changing configuration or resources.
