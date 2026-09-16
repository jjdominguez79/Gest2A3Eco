"""Replica la politica global DEHu en la programacion central del worker."""
from __future__ import annotations

from services.backend_client_service import BackendClientService


def aplicar_programacion_global(gestor, config: dict, backend=None) -> tuple[int, list[str]]:
    backend = backend or BackendClientService()
    guardados = 0
    errores = []
    por_empresa = {}
    for buzon in gestor.listar_notif_buzones_global():
        codigo = str(buzon.get("codigo_empresa") or "")
        if codigo not in por_empresa or buzon.get("activo"):
            por_empresa[codigo] = buzon
    for codigo, buzon in por_empresa.items():
        try:
            if not buzon.get("activo"):
                backend.delete_dehu_mailbox_config(company_code=codigo)
                continue
            empresa = gestor.get_empresa(codigo) or {}
            actualizado = dict(buzon)
            actualizado.update({
                "periodicidad_sync": config.get("periodicidad_sync") or "MANUAL",
                "envio_automatico_cliente": 0,
                "email_aviso": str(empresa.get("email") or "").strip() or None,
            })
            gestor.upsert_notif_buzon(actualizado)
            backend.save_dehu_mailbox_config(
                company_code=codigo,
                mailbox_id=str(buzon.get("id") or ""),
                mailbox_name=str(buzon.get("nombre") or "DEHu"),
                active=True,
                periodicity=actualizado["periodicidad_sync"],
                notification_email=str(config.get("email_resumen_interno") or ""),
            )
            guardados += 1
        except Exception as exc:
            errores.append(f"{codigo}: {exc}")
    return guardados, errores
