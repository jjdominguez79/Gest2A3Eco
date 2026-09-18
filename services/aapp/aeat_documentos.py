"""Clasificacion conservadora de documentos AEAT, sin modificar el PDF firmado."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentoAEAT:
    clase: str = "REVISION"
    resultado: str | None = None
    referencia: str | None = None
    codigo_electronico: str | None = None


def normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).lower().strip()


def referencia_solicitud(texto: str) -> str | None:
    # El CSV autentica un documento; NO identifica por si solo el expediente.
    texto = normalizar_texto(texto)
    patron = (
        r"(?:referencia(?: de la solicitud)?|numero de (?:la )?solicitud|"
        r"numero de expediente)\s*[:\-]\s*([a-z0-9][a-z0-9/\-]{5,59})"
    )
    coincidencias = set(re.findall(patron, texto))
    if len(coincidencias) == 1:
        return coincidencias.pop().upper()
    return None


def codigo_electronico_solicitud(texto: str) -> str | None:
    """Codigo de recogida (16 caracteres), distinto de la referencia TCT."""
    texto = normalizar_texto(texto)
    coincidencias = set(re.findall(
        r"(?:codigo electronico(?: de la solicitud)?|codigo seguro de verificacion|csv)"
        r"\s*(?:\(csv\))?\s*[:\-]?\s*([a-z0-9]{16})\b", texto,
    ))
    return coincidencias.pop().upper() if len(coincidencias) == 1 else None


def clasificar_texto(texto: str) -> DocumentoAEAT:
    texto = normalizar_texto(texto)
    referencia = referencia_solicitud(texto)
    codigo = codigo_electronico_solicitud(texto)
    # No basta que la pagina diga "Obtener resguardo": inspeccionamos el PDF.
    cabecera = texto[:1400]
    resguardo = re.search(
        r"\b(?:resguardo|justificante)\b|solicitud de expedicion de certificado", cabecera,
    )
    certificado = bool(re.search(r"\bcertifica\b|\bcertificado tributario\b", texto))
    if resguardo and not re.search(r"\bcertifica\b", texto):
        return DocumentoAEAT("RESGUARDO", referencia=referencia, codigo_electronico=codigo)
    if not certificado:
        return DocumentoAEAT(referencia=referencia)
    negativo = bool(re.search(
        r"(?:no se encuentra|no esta|no se halla) al corriente|"
        r"(?:caracter|resultado|sentido)\s*[:\-]?\s*negativo|certificado negativo", texto,
    ))
    positivo = bool(re.search(
        r"(?:se encuentra|esta|se halla) al corriente|"
        r"(?:caracter|resultado|sentido)\s*[:\-]?\s*positivo|certificado positivo", texto,
    ))
    # La negacion manda: "no se encuentra" tambien contiene "se encuentra".
    resultado = "NEGATIVO" if negativo else "POSITIVO" if positivo else None
    return DocumentoAEAT("CERTIFICADO", resultado, referencia)


def inspeccionar_pdf(ruta: str) -> DocumentoAEAT:
    try:
        from pypdf import PdfReader
        lector = PdfReader(ruta)
        if len(lector.pages) > 30:
            return DocumentoAEAT()
        texto = "\n".join(p.extract_text() or "" for p in lector.pages)
        return clasificar_texto(texto)
    except Exception:
        # PDF escaneado, corrupto o formato no reconocido: nunca simular exito.
        return DocumentoAEAT()
