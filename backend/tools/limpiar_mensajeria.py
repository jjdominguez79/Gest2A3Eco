from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json

from backend.api.database import SessionLocal
from backend.api.messaging_cleanup import (
    CLOSE_CONFIRMATION,
    RECOVER_CONFIRMATION,
    build_cleanup_plan,
    close_pre_release_cleanup,
    execute_cleanup_plan,
    recover_cleanup_maintenance,
)


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
            "Previsualiza limpiezas de mensajeria de prueba o la purga global "
            "previa a Play Store. Sin --confirmar nunca modifica datos."
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
    scope.add_argument(
        "--prepublicacion-antes-de", type=_cutoff, metavar="FECHA_ISO",
        help=(
            "Purga global de mensajes de clientes y chats internos anteriores "
            "a la fecha, conservando cuentas y conversaciones."
        ),
    )
    scope.add_argument(
        "--cerrar-prepublicacion", action="store_true",
        help="Bloquea definitivamente la purga global tras publicar Flutter.",
    )
    scope.add_argument(
        "--recuperar-mantenimiento", action="store_true",
        help="Retira un bloqueo de mantenimiento dejado por una interrupcion.",
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
            if args.cerrar_prepublicacion:
                if not args.confirmar:
                    print("PREVISUALIZACION: el cierre global sera permanente.")
                    print(f"Para cerrar, repite con --confirmar {CLOSE_CONFIRMATION}")
                    return 0
                audit_id = close_pre_release_cleanup(
                    db, confirmation=args.confirmar, actor=args.actor or "",
                    reason=args.motivo or "",
                )
                print(f"Purga global cerrada definitivamente. Auditoria: {audit_id}")
                return 0
            if args.recuperar_mantenimiento:
                if not args.confirmar:
                    print("PREVISUALIZACION: se retirara el bloqueo de mantenimiento.")
                    print(f"Para recuperar, repite con --confirmar {RECOVER_CONFIRMATION}")
                    return 0
                audit_id = recover_cleanup_maintenance(
                    db, confirmation=args.confirmar, actor=args.actor or "",
                    reason=args.motivo or "",
                )
                print(f"Mantenimiento recuperado. Auditoria: {audit_id}")
                return 0
            plan = build_cleanup_plan(
                db,
                organization_refs=args.organizacion,
                cutoff=args.prepublicacion_antes_de or args.antes_de,
                reset_test=args.reset_test,
                pre_release=args.prepublicacion_antes_de is not None,
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
