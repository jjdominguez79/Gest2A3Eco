"""Preparacion de PDFs de facturas recibidas para su enlace con A3ECO."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from utils.utilidades import load_app_config


A3_SHARED_ROOT = Path(r"\\GestinemMain\Aplicaciones\A3\A3ECO")
A3_MAPPED_ROOT = Path(r"Z:\A3\A3ECO")


def preparar_documentos_para_suenlace(gestor, codigo_empresa: str, ejercicio: int, docs: list[dict], *, a3_root: str | Path | None = None) -> list[dict]:
    """Asigna pdf_ref y crea solo la copia tecnica que consumira A3ECO."""
    codigo_a3 = _codigo_empresa_a3(codigo_empresa)
    a3_dir = _a3_eco_root(a3_root, codigo_a3) / codigo_a3 / "FACTURAS" / str(ejercicio)
    try:
        a3_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"No se pudo acceder a la carpeta de PDFs de A3ECO: {a3_dir}") from exc

    preparados = []
    for original in docs:
        doc = dict(original)
        ref = str(doc.get("pdf_ref") or "").split("@", 1)[0].strip()
        # Las recibidas se distinguen de las emitidas con R. Las referencias
        # antiguas E se regeneran al volver a exportar para que A3 abra el PDF
        # correcto sin confundir ambos circuitos.
        if not ref or ref.upper().startswith("E"):
            ref = gestor.next_pdf_ref(codigo_empresa, ejercicio, prefix="R")
            doc["pdf_ref"] = ref
        source = Path(str(doc.get("pdf_path") or doc.get("origen_path") or "").strip())
        if not source.is_file():
            raise FileNotFoundError(f"No se encuentra el documento de la factura {doc.get('numero_factura') or doc.get('id')}: {source}")

        a3_pdf = a3_dir / f"{ref}.pdf"
        if source.suffix.lower() == ".pdf":
            shutil.copy2(source, a3_pdf)
        else:
            _convertir_imagen_a_pdf(source, a3_pdf)

        # pdf_path sigue apuntando al original respaldado del repositorio.
        # La ruta de A3 es una copia secundaria y regenerable.
        datos_extra = dict(doc.get("datos_extra") or {})
        datos_extra["pdf_path_a3"] = str(a3_pdf)
        doc["datos_extra"] = datos_extra
        gestor.upsert_factura_recibida_doc(doc)
        preparados.append(doc)
    return preparados


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


def _a3_eco_root(a3_root: str | Path | None, codigo_a3: str = "") -> Path:
    if a3_root:
        return Path(a3_root)
    configured = str(load_app_config().get("a3_base_path") or "").strip()
    candidates = [A3_SHARED_ROOT]
    if configured:
        base = Path(configured)
        candidates.append(base if base.name.upper() == "A3ECO" else base / "A3ECO")
    candidates.append(A3_MAPPED_ROOT)
    if codigo_a3:
        for candidate in candidates:
            if (candidate / codigo_a3).is_dir():
                return candidate
    # La ruta UNC es estable para todos los puestos y no depende de que Z:
    # este montada. Si la empresa aun no existe, el error mostrara esta ruta.
    return A3_SHARED_ROOT
