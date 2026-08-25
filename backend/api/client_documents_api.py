"""API de documentos del area privada del cliente.

Endpoints para publicacion interna, listado, descarga, lectura y gestion.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/messaging/client/documents", tags=["client-documents"])

# Endpoints implementados por subagente A en feature/area-documental-clientes
