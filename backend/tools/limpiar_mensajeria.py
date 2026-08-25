from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json

from backend.api.database import SessionLocal
from backend.api.messaging_cleanup import build_cleanup_plan, execute_cleanup_plan


def _cutoff(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Usa YYYY-MM-DD o una fecha ISO 8601 con zona horaria."
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Previsualiza y elimina exclusivamente mensajeria de organizaciones "
            "marcadas como prueba. Sin --confirmar nunca modifica datos."
        ),
    )
    parser.add_argument(
        "--organizacion", action="append", default=[], metavar="CODIGO_O_ID",
        help="Limita el alcance; se puede repetir. Debe estar marcada como prueba.",
    )
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument(
        "--antes-de", type=_cutoff, metavar="FECHA_ISO",
        help=(
            "Elimina mensajes y datos asociados anteriores a la fecha (exclusiva); "
            "una fecha sin zona se interpreta como UTC."
        ),
    )
    scope.add_argument(
        "--reset-test", action="store_true",
        help="Elimina completamente las organizaciones de prueba seleccionadas.",
    )
    parser.add_argument(
        "--confirmar", metavar="CODIGO",
        help="Ejecuta el plan si coincide con el codigo de la previsualizacion.",
    )
    parser.add_argument("--actor", help="Persona responsable de la ejecucion.")
    parser.add_argument("--motivo", help="Motivo que quedara en auditoria.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with SessionLocal() as db:
        try:
            plan = build_cleanup_plan(
                db,
                organization_refs=args.organizacion,
                cutoff=args.antes_de,
                reset_test=args.reset_test,
            )
            print(json.dumps(plan.public_dict(), indent=2, ensure_ascii=False))
            if not args.confirmar:
                print("\nPREVISUALIZACION: no se ha modificado ningun dato.")
                print(f"Para ejecutar, repite el comando con --confirmar {plan.confirmation_code}")
                return 0
            result = execute_cleanup_plan(
                db,
                plan,
                confirmation_code=args.confirmar,
                actor=args.actor or "",
                reason=args.motivo or "",
            )
        except ValueError as exc:
            print(f"ERROR: {exc}")
            return 2
    print(f"Limpieza completada. Auditoria: {result.audit_id}")
    if result.failed_storage_keys:
        print(
            "ATENCION: no se pudieron eliminar "
            f"{len(result.failed_storage_keys)} objetos; constan en la auditoria."
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
