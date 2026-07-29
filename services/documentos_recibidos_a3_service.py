"""Preparacion de PDFs de facturas recibidas para su enlace con A3ECO."""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from utils.utilidades import get_default_received_documents_dir


def preparar_documentos_para_suenlace(gestor, codigo_empresa: str, ejercicio: int, docs: list[dict], *, a3_root: str | Path = r"Z:\A3\A3ECO") -> list[dict]:
    """Asigna pdf_ref y garantiza la copia local y la de A3 antes de exportar."""
    codigo_a3 = _codigo_empresa_a3(codigo_empresa)
    a3_dir = Path(a3_root) / codigo_a3 / "FACTURAS" / str(ejercicio)
    try:
        a3_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"No se pudo acceder a la carpeta de PDFs de A3ECO: {a3_dir}") from exc

    preparados = []
    for original in docs:
        doc = dict(original)
        ref = str(doc.get("pdf_ref") or "").split("@", 1)[0].strip()
        if not ref:
            ref = gestor.next_pdf_ref(codigo_empresa, ejercicio)
            doc["pdf_ref"] = ref
        source = Path(str(doc.get("pdf_path") or doc.get("origen_path") or "").strip())
        if not source.is_file():
            raise FileNotFoundError(f"No se encuentra el documento de la factura {doc.get('numero_factura') or doc.get('id')}: {source}")

        local_pdf = _local_pdf_path(codigo_empresa, ejercicio, ref, doc)
        local_pdf.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() == ".pdf":
            if source.resolve() != local_pdf.resolve():
                shutil.copy2(source, local_pdf)
        else:
            _convertir_imagen_a_pdf(source, local_pdf)
        a3_pdf = a3_dir / f"{ref}.pdf"
        shutil.copy2(local_pdf, a3_pdf)

        doc["pdf_path"] = str(local_pdf)
        datos_extra = dict(doc.get("datos_extra") or {})
        datos_extra["pdf_path_a3"] = str(a3_pdf)
        doc["datos_extra"] = datos_extra
        gestor.upsert_factura_recibida_doc(doc)
        preparados.append(doc)
    return preparados


def _local_pdf_path(codigo_empresa: str, ejercicio: int, ref: str, doc: dict) -> Path:
    proveedor = _safe_name(doc.get("proveedor_nombre") or "Proveedor")
    numero = _safe_name(doc.get("numero_factura") or "Sin_numero")
    return get_default_received_documents_dir() / str(codigo_empresa) / str(ejercicio) / f"{ref}_{proveedor}_{numero}.pdf"


def _convertir_imagen_a_pdf(source: Path, destination: Path) -> None:
    try:
        from PIL import Image
        with Image.open(source) as image:
            image.convert("RGB").save(destination, "PDF", resolution=150.0)
    except Exception as exc:
        raise RuntimeError(f"No se pudo convertir la imagen a PDF: {source.name}") from exc


def _codigo_empresa_a3(codigo: str) -> str:
    digits = "".join(ch for ch in str(codigo or "") if ch.isdigit())
    return f"E{(digits.zfill(5) if digits else '00000')[:5]}"


def _safe_name(value: object) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or "")).strip(". ")[:80] or "Documento"
