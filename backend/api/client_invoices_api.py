"""API de facturacion online del cliente.

Endpoints para borradores, emision, listado y configuracion.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/messaging/client/invoicing", tags=["client-invoicing"])

# Endpoints implementados por subagente B en feature/facturacion-clientes-flutter
