"""Servicio de catalogo de productos y servicios para facturacion online.

Ver docs/adr/0001-facturacion-autonoma-cliente.md, Etapa 4.
"""

from __future__ import annotations

from decimal import Decimal

from backend.api.client_models import ClientCatalogItem, ClientInvoiceLine


def copy_catalog_item_to_line(item: ClientCatalogItem, line: ClientInvoiceLine) -> None:
    """Copia los valores del articulo a la linea en el momento de anadirla.

    A partir de aqui la linea es independiente: modificar el articulo mas
    adelante (precio, IVA, descripcion...) nunca altera lineas ya copiadas,
    salvo una accion explicita del usuario que vuelva a aplicar el articulo.
    """
    line.catalog_item_id = item.id
    line.description = item.description
    line.unit_price = item.unit_price
    line.vat_rate = item.vat_rate


def catalog_item_to_dict(item: ClientCatalogItem) -> dict:
    return {
        "id": item.id,
        "item_type": item.item_type,
        "code": item.code,
        "description": item.description,
        "unit": item.unit,
        "unit_price": str(item.unit_price),
        "vat_rate": str(item.vat_rate),
        "withholding_rate": str(item.withholding_rate),
        "active": item.active,
        "revision": item.revision,
    }


def validate_catalog_item_payload(payload: dict) -> dict:
    """Valida y normaliza los campos del catalogo. Lanza ValueError si son invalidos."""
    description = str(payload.get("description", "")).strip()
    if not description:
        raise ValueError("La descripcion es obligatoria")

    item_type = str(payload.get("item_type", "service")).strip().lower()
    if item_type not in ("product", "service"):
        raise ValueError("item_type debe ser 'product' o 'service'")

    try:
        unit_price = Decimal(str(payload.get("unit_price", "0")))
        vat_rate = Decimal(str(payload.get("vat_rate", "21.00")))
        withholding_rate = Decimal(str(payload.get("withholding_rate", "0")))
    except Exception as exc:  # noqa: BLE001 - Decimal lanza varias excepciones
        raise ValueError("Importe o impuesto no valido") from exc

    if unit_price < 0:
        raise ValueError("El precio no puede ser negativo")
    if not (Decimal("0") <= vat_rate <= Decimal("100")):
        raise ValueError("El tipo de IVA debe estar entre 0 y 100")
    if not (Decimal("0") <= withholding_rate <= Decimal("100")):
        raise ValueError("La retencion debe estar entre 0 y 100")

    return {
        "item_type": item_type,
        "code": str(payload.get("code", "")).strip()[:40],
        "description": description[:2000],
        "unit": str(payload.get("unit", "")).strip()[:20],
        "unit_price": unit_price,
        "vat_rate": vat_rate,
        "withholding_rate": withholding_rate,
    }
