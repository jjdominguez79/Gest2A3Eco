"""Replica la politica global DEHu/DEV en la programacion central del worker."""
from __future__ import annotations

from services.backend_client_service import BackendClientService


def aplicar_programacion_global(gestor, config: dict, backend=None) -> tuple[int, list[str]]:
    backend = backend or BackendClientService()
    guardados = 0
    errores = []
    por_empresa = {}
    for buzon in gestor.listar_notif_buzones_global():
        codigo = str(buzon.get("codigo_empresa") or "")
        provider = str(buzon.get("organismo_codigo") or "DEHU").upper()
        if provider in {"DEHU", "DEV"}:
            por_empresa[(codigo, provider)] = buzon
    for (codigo, provider), buzon in por_empresa.items():
        try:
            if not buzon.get("activo"):
                if provider == "DEHU":
                    backend.delete_dehu_mailbox_config(company_code=codigo)
                else:
                    backend.delete_dev_mailbox_config(company_code=codigo)
                continue
            empresa = gestor.get_empresa(codigo) or {}
            actualizado = dict(buzon)
            actualizado.update({
                "periodicidad_sync": config.get("periodicidad_sync") or "MANUAL",
                "modo_descarga": "SOLO_DETECTAR",
                "envio_automatico_cliente": 0,
                "email_aviso": str(empresa.get("email") or "").strip() or None,
            })
            gestor.upsert_notif_buzon(actualizado)
            save = (
                backend.save_dehu_mailbox_config
                if provider == "DEHU" else backend.save_dev_mailbox_config
            )
            save(
                company_code=codigo,
                mailbox_id=str(buzon.get("id") or ""),
                mailbox_name=str(buzon.get("nombre") or provider),
                active=True,
                periodicity=actualizado["periodicidad_sync"],
                daily_sync_time=str(config.get("hora_sync_diaria") or ""),
                notification_email=str(config.get("email_resumen_interno") or ""),
            )
            guardados += 1
        except Exception as exc:
            errores.append(f"{codigo}: {exc}")
    return guardados, errores
