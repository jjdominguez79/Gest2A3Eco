"""Migracion segura de PDFs emitidos a su repositorio compartido canonico."""
from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from utils.utilidades import get_default_output_dir


@dataclass
class MigracionPdfEmitidasResumen:
    migradas: int = 0
    ya_canonicas: int = 0
    sin_origen: int = 0
    conflictos: int = 0
    errores: list[str] = field(default_factory=list)


def ruta_pdf_emitida_canonica(factura: dict, root: Path | None = None) -> Path:
    """Calcula la misma ruta estable que usa el controlador de emitidas."""
    root = root or get_default_output_dir()
    codigo = _safe_name(factura.get("codigo_empresa")) or "Sin_empresa"
    ejercicio = _safe_name(factura.get("ejercicio"))
    serie = _safe_name(factura.get("serie"))
    numero = _safe_name(factura.get("numero"))
    cliente = _safe_name(factura.get("nombre")) or "Sin_cliente"
    ref = _safe_name(str(factura.get("pdf_ref") or "").split("@", 1)[0])
    identity = ref or f"{serie}{numero}"
    filename = "_".join(part for part in (identity, codigo, cliente) if part)
    if not filename:
        filename = f"Factura_{factura.get('id') or 'sin_id'}"
    return root / codigo / ejercicio / "Facturas_emitidas" / f"{filename}.pdf"


def migrar_pdf_emitidas(gestor, *, root: Path | None = None) -> MigracionPdfEmitidasResumen:
    """Copia PDFs disponibles y actualiza ``pdf_path`` solo tras verificarlos.

    No borra ningun origen ni altera ``pdf_path_a3``: esa columna conserva la
    copia tecnica de A3 para trazabilidad y recuperacion de archivos.
    """
    root = root or get_default_output_dir()
    rows = gestor.conn.execute(
        "SELECT id,codigo_empresa,ejercicio,serie,numero,nombre,pdf_ref,pdf_path,pdf_path_a3 "
        "FROM facturas_emitidas_docs"
    ).fetchall()
    resumen = MigracionPdfEmitidasResumen()
    for row in rows:
        factura = dict(row)
        destino = ruta_pdf_emitida_canonica(factura, root)
        actual = Path(str(factura.get("pdf_path") or ""))
        if actual == destino and destino.is_file():
            resumen.ya_canonicas += 1
            continue

        origen = _primer_origen_existente(factura)
        if origen is None:
            resumen.sin_origen += 1
            continue
        try:
            if destino.is_file() and _sha256(destino) != _sha256(origen):
                resumen.conflictos += 1
                resumen.errores.append(f"{factura['id']}: destino con contenido distinto")
                continue
            if not destino.is_file():
                destino.parent.mkdir(parents=True, exist_ok=True)
                temporal = destino.with_name(f".{destino.name}.{uuid.uuid4().hex}.tmp")
                try:
                    shutil.copy2(origen, temporal)
                    if _sha256(origen) != _sha256(temporal):
                        raise IOError("La copia no coincide con el origen.")
                    temporal.replace(destino)
                finally:
                    temporal.unlink(missing_ok=True)
            gestor.conn.execute(
                "UPDATE facturas_emitidas_docs SET pdf_path=? WHERE id=?",
                (str(destino), str(factura["id"])),
            )
            resumen.migradas += 1
        except Exception as exc:
            resumen.errores.append(f"{factura['id']}: {exc}")
    gestor.conn.commit()
    return resumen


def _primer_origen_existente(factura: dict) -> Path | None:
    for field in ("pdf_path", "pdf_path_a3"):
        value = str(factura.get(field) or "").strip()
        path = Path(value)
        if value and path.is_file():
            return path
    return None


def _safe_name(value) -> str:
    value = str(value or "").strip()
    value = re.sub(r'[<>:"/\\|?*]', " ", value)
    return " ".join(value.split())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()
