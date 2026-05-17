"""
Abstraccion del motor OCR.

Para anadir un nuevo proveedor:
  1. Crear una subclase de OCRProvider.
  2. Implementar nombre, disponible() y extraer().
  3. Registrarla en build_provider_chain().

El contrato de extraer() garantiza que NUNCA lanza excepcion:
los errores se devuelven en OCRResult.errores.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


# ── Resultado normalizado ────────────────────────────────────────────────────

@dataclass
class OCRResult:
    texto: str = ""
    confianza: float = 0.0
    proveedor: str = ""
    errores: list[str] = field(default_factory=list)
    campos_raw: dict = field(default_factory=dict)

    @property
    def exito(self) -> bool:
        return bool(self.texto.strip())


# ── Interfaz abstracta ────────────────────────────────────────────────────────

class OCRProvider(ABC):
    @property
    @abstractmethod
    def nombre(self) -> str:
        """Identificador corto del proveedor (para logs y datos_extra)."""

    @abstractmethod
    def disponible(self) -> bool:
        """True si el proveedor puede ejecutarse en el entorno actual."""

    @abstractmethod
    def extraer(self, path: Path) -> OCRResult:
        """Extrae texto del fichero. Nunca lanza excepcion."""


# ── Proveedor 1: texto nativo de PDF (pypdf) ─────────────────────────────────

class OCRProviderLocal(OCRProvider):
    """Extrae la capa de texto de PDFs digitales. Gratis, sin red, sin dependencias extra."""

    @property
    def nombre(self) -> str:
        return "local_pdf"

    def disponible(self) -> bool:
        try:
            import pypdf  # noqa: F401
            return True
        except ImportError:
            return False

    def extraer(self, path: Path) -> OCRResult:
        if path.suffix.lower() != ".pdf":
            return OCRResult(
                proveedor=self.nombre,
                errores=["El proveedor local solo procesa PDF con capa de texto."],
            )
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            pages = []
            for page in reader.pages:
                try:
                    pages.append(page.extract_text() or "")
                except Exception:
                    pages.append("")
            texto = "\n".join(pages).strip()
            if texto:
                return OCRResult(texto=texto, confianza=0.92, proveedor=self.nombre)
            return OCRResult(
                proveedor=self.nombre,
                errores=["PDF sin capa de texto. Se requiere OCR externo para procesar."],
            )
        except Exception as exc:
            return OCRResult(proveedor=self.nombre, errores=[f"Error pypdf: {exc}"])


# ── Proveedor 2: backend HTTP configurable ────────────────────────────────────

class OCRProviderHTTP(OCRProvider):
    """Envia el fichero a un endpoint HTTP POST y recibe texto + confianza.

    El endpoint debe aceptar JSON: {"file_path": "<ruta_absoluta>"}
    y devolver JSON: {"text": "...", "confidence": 0.95}
    (tambien acepta las claves "texto" y "confianza" en castellano).
    """

    def __init__(self, endpoint: str, timeout: int = 30):
        self._endpoint = endpoint.strip()
        self._timeout = timeout

    @property
    def nombre(self) -> str:
        return "http"

    def disponible(self) -> bool:
        return bool(self._endpoint)

    def extraer(self, path: Path) -> OCRResult:
        payload = json.dumps({"file_path": str(path)}).encode("utf-8")
        req = urllib.request.Request(
            self._endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            return OCRResult(proveedor=self.nombre, errores=[f"Error de red al conectar con backend OCR: {exc}"])
        except Exception as exc:
            return OCRResult(proveedor=self.nombre, errores=[f"Error inesperado en backend OCR: {exc}"])
        texto = str(raw.get("text") or raw.get("texto") or "")
        confianza = float(raw.get("confidence") or raw.get("confianza") or 0.0)
        if not texto:
            return OCRResult(proveedor=self.nombre, errores=["El backend OCR no devolvio texto."])
        return OCRResult(texto=texto, confianza=confianza, proveedor=self.nombre)


# ── Proveedor 3: Tesseract (stub — activar cuando este instalado) ─────────────

class OCRProviderTesseract(OCRProvider):
    """OCR local mediante Tesseract/pytesseract. Requiere Tesseract instalado en el sistema."""

    def __init__(self, lang: str = "spa+eng"):
        self._lang = lang

    @property
    def nombre(self) -> str:
        return "tesseract"

    def disponible(self) -> bool:
        try:
            import pytesseract  # noqa: F401
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def extraer(self, path: Path) -> OCRResult:
        try:
            import pytesseract
            from PIL import Image as PilImage
            if path.suffix.lower() == ".pdf":
                return self._extraer_pdf(path, pytesseract)
            img = PilImage.open(str(path))
            texto = pytesseract.image_to_string(img, lang=self._lang)
            conf_data = pytesseract.image_to_data(img, lang=self._lang, output_type=pytesseract.Output.DICT)
            confs = [c for c in conf_data.get("conf", []) if c != -1]
            confianza = round(sum(confs) / len(confs) / 100, 3) if confs else 0.0
            if texto.strip():
                return OCRResult(texto=texto.strip(), confianza=confianza, proveedor=self.nombre)
            return OCRResult(proveedor=self.nombre, errores=["Tesseract no extrajo texto de la imagen."])
        except Exception as exc:
            return OCRResult(proveedor=self.nombre, errores=[f"Error Tesseract: {exc}"])

    def _extraer_pdf(self, path: Path, pytesseract) -> OCRResult:
        try:
            import fitz  # pymupdf
            from PIL import Image as PilImage
            import io
            doc = fitz.open(str(path))
            textos = []
            for page in doc:
                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat)
                img = PilImage.open(io.BytesIO(pix.tobytes("png")))
                textos.append(pytesseract.image_to_string(img, lang=self._lang))
            texto = "\n".join(textos).strip()
            if texto:
                return OCRResult(texto=texto, confianza=0.75, proveedor=self.nombre)
            return OCRResult(proveedor=self.nombre, errores=["Tesseract no extrajo texto del PDF."])
        except ImportError:
            return OCRResult(proveedor=self.nombre, errores=["pymupdf (fitz) no disponible para renderizar PDF."])
        except Exception as exc:
            return OCRResult(proveedor=self.nombre, errores=[f"Error al procesar PDF con Tesseract: {exc}"])


# ── Proveedor 4: Mindee (stub — requiere API key) ────────────────────────────

class OCRProviderMindee(OCRProvider):
    """Extraccion estructurada de facturas via API Mindee.

    Activa configurando en config.json:
      "ocr_provider": "mindee"
      "mindee_api_key": "<tu_api_key>"
    """

    def __init__(self, api_key: str):
        self._api_key = api_key.strip()

    @property
    def nombre(self) -> str:
        return "mindee"

    def disponible(self) -> bool:
        if not self._api_key:
            return False
        try:
            import mindee  # noqa: F401
            return True
        except ImportError:
            return False

    def extraer(self, path: Path) -> OCRResult:
        try:
            from mindee import Client, product
            client = Client(api_key=self._api_key)
            with open(str(path), "rb") as f:
                input_doc = client.source_from_file(f)
            result = client.parse(product.InvoiceV4, input_doc)
            pred = result.document.inference.prediction
            campos_raw = {
                "supplier_name": str(pred.supplier_name),
                "supplier_company_registrations": [str(r) for r in (pred.supplier_company_registrations or [])],
                "invoice_number": str(pred.invoice_number),
                "date": str(pred.date),
                "total_amount": float(pred.total_amount.value or 0),
                "total_net": float(pred.total_net.value or 0),
                "taxes": [
                    {"rate": float(t.rate or 0), "value": float(t.value or 0), "base": float(t.base or 0)}
                    for t in (pred.taxes or [])
                ],
            }
            texto = result.document.to_s() if hasattr(result.document, "to_s") else str(result.document)
            return OCRResult(
                texto=texto,
                confianza=0.95,
                proveedor=self.nombre,
                campos_raw=campos_raw,
            )
        except Exception as exc:
            return OCRResult(proveedor=self.nombre, errores=[f"Error Mindee: {exc}"])


# ── Fabrica de cadena de proveedores ─────────────────────────────────────────

def build_provider_chain(cfg: dict) -> list[OCRProvider]:
    """Construye la lista de proveedores en orden de prioridad segun config.json.

    Orden por defecto si ocr_provider no esta configurado:
      1. HTTP (si ocr_endpoint esta definido)
      2. Local PDF (siempre disponible como fallback)

    Con ocr_provider="tesseract":
      1. Tesseract
      2. Local PDF (fallback)

    Con ocr_provider="mindee":
      1. Mindee
      2. Local PDF (fallback)
    """
    provider_name = str(cfg.get("ocr_provider") or "").strip().lower()
    endpoint = str(cfg.get("ocr_endpoint") or "").strip()
    mindee_key = str(cfg.get("mindee_api_key") or "").strip()

    chain: list[OCRProvider] = []

    if provider_name == "mindee" and mindee_key:
        chain.append(OCRProviderMindee(mindee_key))
    elif provider_name == "tesseract":
        chain.append(OCRProviderTesseract())
    elif provider_name == "http" and endpoint:
        chain.append(OCRProviderHTTP(endpoint))
    elif endpoint and not provider_name:
        chain.append(OCRProviderHTTP(endpoint))

    chain.append(OCRProviderLocal())
    return chain
