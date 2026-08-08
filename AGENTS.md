# AGENTS.md

Guidance for Codex when working in this repository.

## Project Overview

Gest2A3Eco is a Windows desktop accounting application built with Python,
Tkinter and PostgreSQL. Core responsibilities:

1. Generate `suenlace.dat` binary files for A3ECO from bank extracts and invoice data.
2. Manage issued and received invoices, including Word-template PDF generation,
   communication workflows and OCR review.

## Development Commands

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

python main.py
pytest
pyinstaller Gest2A3Eco.spec
```

## Architecture

MVC + Services + Process layer. Entry point: `main.py`.

| Layer | Directory | Role |
|---|---|---|
| Views | `views/ui_*.py` | Tkinter screens; UI only |
| Controllers | `controllers/*.py` | Navigation, validation, orchestration |
| Services | `services/*.py` | Auth, email, OCR, notifications, imports |
| Processes | `procesos/*.py` | A3ECO binary generation and PDF generation |
| Models | `models/` | PostgreSQL data access and A3ECO record renderers |
| Utilities | `utils/` | Config I/O, NIF/CIF validation, number formatting |

## Database

PostgreSQL is the only application database. Configure it through
`postgres_dsn` in `config.local.json` or `GEST2A3ECO_POSTGRES_DSN`.

Do not add local file-database fallbacks, local `.db` paths, or migration flows
that require a workstation database file. Schema initialization and additive
checks belong in the PostgreSQL data layer.

## Conventions

- Spanish identifiers, UI text and comments.
- Source files should remain ASCII unless the edited file already requires otherwise.
- UI in `views/`; business logic in `controllers/`, `services/` or `procesos/`; data in `models/`.
- Data access goes through the PostgreSQL gestor exposed by `models/gestor_postgres.py`.
- `plantillas.json` is seed/template material only, not the source of truth.
- PDFs are generated through `procesos/facturas_word.py`; no basic-PDF fallback.
- PDFs are copied to the A3ECO linked folder only during `suenlace.dat` generation.
- Target platform is Windows.
