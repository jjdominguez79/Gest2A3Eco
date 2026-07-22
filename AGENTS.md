# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

Gest2A3Eco is a desktop accounting application (Python 3.10+ / Tkinter / Windows) for Spanish accounting firm Gestinem. Two core functions:
1. Generate `suenlace.dat` binary files in A3ECO format from Excel bank extracts and invoice data
2. Manage issued invoices: creation, auto-numbering, PDF generation from Word templates, email/WhatsApp distribution

## Development Commands

```bash
# Setup
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS (dev only — app targets Windows)
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run
python main.py

# Tests
pytest                                    # all tests
pytest tests/test_validaciones.py         # single file
pytest tests/test_validaciones.py -k test_nif  # single test

# Build (Windows only)
pyinstaller Gest2A3Eco.spec    # → dist/Gest2A3Eco/Gest2A3Eco.exe
```

## Architecture

MVC + Services + Process layer. Entry point: `main.py`.

**Startup flow:** `main.py` → `UILogin` → `AuthService` → `AppController` → `UIPanelGeneral` (company list) → `UIDashboardEmpresa` → module views

| Layer | Directory | Role |
|---|---|---|
| Views | `views/ui_*.py` | Tkinter screens — UI only, no business logic |
| Controllers | `controllers/*.py` | Navigation, validation, orchestration |
| Services | `services/*.py` | Auth, email, OCR, notifications, imports |
| Processes | `procesos/*.py` | A3ECO binary generation, PDF from Word templates |
| Models | `models/` | SQLite data access (`gestor_sqlite.py`), A3ECO record renderers (`facturas_common.py`) |
| Utilities | `utils/` | Config I/O, NIF/CIF validation, number formatting |

## Key Domain Concepts

- **suenlace.dat**: Binary file with fixed-width records (types 0/1/2/9/C/6) for A3ECO accounting software import
- **digitos_plan**: Configurable account code length per company (default 8) — must be respected in all account/subaccount operations
- **Series**: Each company has independent invoice numbering series (normal `A` + rectificativa `R`)
- **PDF generation**: Always via `procesos/facturas_word.py` → `generar_pdf_desde_plantilla_word()`. No fallback to basic PDF.
- PDFs are copied to the A3ECO linked folder only during suenlace.dat generation, not during normal export

## Database

SQLite at `plantillas/gest2a3eco.db` (created on first run). Schema is embedded in `GestorSQLite.__init__()`. Key tables: `empresas`, `series_emitidas`, `facturas_emitidas`, `facturas_recibidas`, `terceros`, `terceros_empresas`, `bancos`, `plan_cuentas`, `usuarios`, `usuarios_empresas`.

Back up `plantillas/` before schema migrations.

## Conventions

- **Language**: Spanish identifiers, UI, and comments. Source files use ASCII (no accents).
- **Layer discipline**: UI in `views/`, logic in `controllers/` + `procesos/`, data in `models/`. Do not mix.
- **Data access**: Use `GestorSQLite` directly. `plantillas.json` is seed-only.
- **Auth**: scrypt hashing, roles ADMIN/EMPLEADO/CLIENTE, per-company permissions (NINGUNO/LECTURA/ESCRITURA). `SecuredGestorSQLite` wraps permission checks.
- **`main.py`**: Do not modify unless changing company identity data (nombre, CIF, contacto).
- **Platform**: Windows-targeted (uses `os.startfile`, Win32 paths, `pywin32`). Dev/testing possible on macOS but some features are Windows-only.
