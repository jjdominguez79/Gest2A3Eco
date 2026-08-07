from __future__ import annotations

import shutil
import tempfile
import os
from pathlib import Path


def preparar_pdf_con_zonas(ruta: str, zonas: list[dict], destino: str | None = None) -> str:
    """Inserta etiquetas SignRequest invisibles en las coordenadas elegidas.

    Las coordenadas recibidas son proporciones de la pagina (0..1), con origen
    arriba a la izquierda, que es el sistema usado por el visor Tkinter.
    """
    origen = Path(ruta)
    if not origen.is_file():
        raise FileNotFoundError(f"No se encuentra el PDF: {origen}")
    if destino:
        salida = Path(destino)
    else:
        fd, temp_name = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        salida = Path(temp_name)
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF es necesario para preparar las zonas de firma.") from exc

    if not zonas:
        if salida != origen:
            shutil.copyfile(origen, salida)
        return str(salida)

    doc = fitz.open(str(origen))
    try:
        for zona in zonas:
            pagina_num = int(zona.get("pagina", 0))
            if pagina_num < 0 or pagina_num >= len(doc):
                raise ValueError("La pagina de una zona de firma no es valida.")
            page = doc[pagina_num]
            rect = page.rect
            x = max(0.0, min(1.0, float(zona.get("x", 0)))) * rect.width
            y = max(0.0, min(1.0, float(zona.get("y", 0)))) * rect.height
            w = max(0.02, min(1.0, float(zona.get("ancho", 0.2)))) * rect.width
            h = max(0.02, min(1.0, float(zona.get("alto", 0.08)))) * rect.height
            indice = int(zona.get("firmante", 1))
            if indice < 0:
                raise ValueError("El indice del firmante no puede ser negativo.")
            etiqueta = f"[[s|{indice}]]"
            # Blanco para no alterar visualmente el documento; SignRequest lee
            # el texto extraido del PDF y convierte la etiqueta en un campo.
            page.insert_textbox(
                fitz.Rect(x, y, min(rect.x1, x + w), min(rect.y1, y + h)),
                etiqueta,
                fontsize=max(6, min(18, h * 0.55)),
                fontname="helv",
                color=(1, 1, 1),
                overlay=True,
            )
        doc.save(str(salida), garbage=4, deflate=True)
    finally:
        doc.close()
    return str(salida)
