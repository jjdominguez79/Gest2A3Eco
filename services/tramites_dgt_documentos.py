from __future__ import annotations

from pathlib import Path


ROLES_DOCUMENTO_DGT = {
    "gestor": "Expediente / Gestor\u00eda",
    "comprador": "Comprador",
    "vendedor": "Vendedor",
}

TIPOS_DOCUMENTO_DGT = {
    "modelo_620": "Modelo 620 presentado",
    "justificante_presentacion": "Justificante de presentaci\u00f3n",
    "tasa_dgt": "Tasa / justificante de pago",
    "contrato_compraventa": "Contrato de compraventa",
    "documento_identidad": "DNI / NIE",
    "permiso_circulacion": "Permiso de circulaci\u00f3n",
    "ficha_tecnica": "Ficha t\u00e9cnica / ITV",
    "mandato_autorizacion": "Mandato / autorizaci\u00f3n",
    "escrito": "Escrito / alegaciones",
    "otro": "Otro documento",
}

MIME_POR_EXTENSION_DGT = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

FILTROS_ARCHIVO_DGT = (
    ("PDF o imagen", "*.pdf *.PDF *.jpg *.JPG *.jpeg *.JPEG *.png *.PNG"),
)


def rol_desde_etiqueta(etiqueta: str) -> str:
    for rol, visible in ROLES_DOCUMENTO_DGT.items():
        if etiqueta == visible:
            return rol
    raise ValueError("Selecciona el \u00e1mbito del documento.")


def etiqueta_rol_documento(rol: str) -> str:
    return ROLES_DOCUMENTO_DGT.get(str(rol or ""), str(rol or ""))


def tipo_desde_etiqueta(etiqueta: str) -> str:
    for tipo, visible in TIPOS_DOCUMENTO_DGT.items():
        if etiqueta == visible:
            return tipo
    raise ValueError("Selecciona el tipo de documento.")


def etiqueta_tipo_documento(tipo: str) -> str:
    return TIPOS_DOCUMENTO_DGT.get(str(tipo or ""), str(tipo or ""))


def mime_documento_dgt(file_path: str) -> str:
    extension = Path(file_path).suffix.lower()
    try:
        return MIME_POR_EXTENSION_DGT[extension]
    except KeyError as exc:
        raise ValueError("Solo se admiten archivos PDF, JPG, JPEG y PNG.") from exc
