"""Entrada del servicio cron de Railway para ayudas y subvenciones."""

from backend.api.database import SessionLocal
from backend.api.subvenciones_service import SubvencionesService


def main() -> int:
    with SessionLocal() as db:
        run = SubvencionesService(db).ejecutar()
        print(
            f"Subvenciones {run.id}: {run.estado}; leidas={run.leidas}; "
            f"nuevas={run.nuevas}; actualizadas={run.actualizadas}; "
            f"resumidas={run.resumidas}; avisos={run.avisos_enviados}"
        )
        return 0 if run.estado in {"ok", "omitida"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
