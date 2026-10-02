"""Cola local de aprendizaje supervisado para facturas OCR."""
from __future__ import annotations

import json
import mimetypes
import re
import statistics
import uuid
from pathlib import Path
from datetime import datetime


class AprendizajeOcrService:
    """Convierte una factura validada en un ejemplo listo para entrenamiento.

    La validacion permanece local. La exportacion a Azure se hara de forma
    explicita y versionada, nunca al guardar una factura de produccion.
    """

    def __init__(self, gestor, empresa_id: str):
        self._gestor = gestor
        self._empresa_id = str(empresa_id)

    def registrar_factura_validada(
        self, documento: dict, factura: dict, marcas_campos: dict | None = None,
    ) -> int:
        tipo_documento = str(
            documento.get("tipo_documento") or "factura_recibida"
        )
        es_emitida = tipo_documento == "factura_emitida"
        if es_emitida:
            lineas = self._gestor.listar_lineas_iva_emitida_ocr(str(factura["id"]))
        else:
            lineas = self._gestor.listar_lineas_iva_ocr(str(factura["id"]))
        datos_ocr = self._datos_ocr_documento(documento)
        datos = {
            "TipoDocumento": tipo_documento,
            "NumeroFactura": str(factura.get("numero_factura") or ""),
            "FechaFactura": str(factura.get("fecha_factura") or ""),
            "FechaVencimiento": str(factura.get("fecha_vencimiento") or ""),
            "BaseTotal": float(factura.get("base_total") or 0.0),
            "IvaTotal": float(factura.get("iva_total") or 0.0),
            "TotalFactura": float(factura.get("total_factura") or 0.0),
            "LineasIva": [
                {
                    "TipoIva": float(linea.get("tipo_iva") or 0.0),
                    "Base": float(linea.get("base") or 0.0),
                    "CuotaIva": float(linea.get("cuota_iva") or 0.0),
                }
                for linea in lineas
            ],
        }
        if es_emitida:
            datos.update({
                "EmisorNif": str(datos_ocr.get("proveedor_nif") or ""),
                "EmisorNombre": str(datos_ocr.get("proveedor_nombre") or ""),
                "ClienteNif": str(
                    factura.get("nif_cliente") or factura.get("nif_proveedor") or ""
                ),
                "ClienteNombre": str(
                    factura.get("nombre_cliente")
                    or factura.get("nombre_proveedor")
                    or ""
                ),
            })
            tercero_nif = datos["ClienteNif"]
        else:
            datos.update({
                "ProveedorNif": str(factura.get("nif_proveedor") or ""),
                "ProveedorNombre": str(factura.get("nombre_proveedor") or ""),
            })
            tercero_nif = datos["ProveedorNif"]
        ejemplo_id = self._gestor.upsert_ejemplo_aprendizaje_ocr({
            "empresa_id": self._empresa_id,
            "documento_id": str(documento["id"]),
            "factura_id": str(factura["id"]),
            # La columna conserva su nombre historico; en emitidas identifica
            # al cliente para poder agrupar los ejemplos por tercero.
            "proveedor_nif": tercero_nif,
            "origen_path": str(documento.get("ruta_original") or ""),
            "datos_validados_json": json.dumps(datos, ensure_ascii=True, sort_keys=True),
            "estado": "pendiente",
            "fecha_validacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "notas": (
                f"{tipo_documento} validada en Gest2A3Eco; "
                "pendiente de exportacion a modelo."
            ),
            "marcas_json": json.dumps(marcas_campos or {}, ensure_ascii=True, sort_keys=True),
        })
        # El modelo local se recompone al validar: no envia datos fuera y hace
        # que las marcas humanas sean aprovechables desde la factura siguiente.
        if hasattr(self._gestor, "listar_ejemplos_aprendizaje_ocr_todos"):
            self.entrenar_modelos_locales()
        return ejemplo_id

    @staticmethod
    def _datos_ocr_documento(documento: dict) -> dict:
        raw = documento.get("json_ocr") or {}
        if isinstance(raw, dict):
            return raw
        try:
            parsed = json.loads(str(raw))
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    def resumen(self) -> dict:
        resumen = self._gestor.resumen_aprendizaje_ocr(self._empresa_id)
        if hasattr(self._gestor, "listar_modelos_ocr_locales"):
            modelos = self._gestor.listar_modelos_ocr_locales(
                self._empresa_id, "factura_recibida",
            )
            resumen["modelos_locales"] = len(modelos)
            resumen["ejemplos_modelo_local"] = sum(
                int(modelo.get("ejemplos") or 0) for modelo in modelos
            )
        return resumen

    def entrenar_modelos_locales(self) -> dict:
        """Entrena plantillas de posicion por proveedor con ejemplos marcados.

        Las coordenadas se normalizan respecto a la pagina, por lo que una
        misma plantilla sigue funcionando aunque cambie el zoom de revision.
        """
        ejemplos = self._gestor.listar_ejemplos_aprendizaje_ocr_todos(
            self._empresa_id,
        )
        grupos: dict[tuple[str, str], list[dict]] = {}
        for ejemplo in ejemplos:
            try:
                datos = json.loads(ejemplo.get("datos_validados_json") or "{}")
                marcas = json.loads(ejemplo.get("marcas_json") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(marcas, dict) or not marcas:
                continue
            tipo = str(datos.get("TipoDocumento") or "factura_recibida")
            tercero = str(ejemplo.get("proveedor_nif") or "").strip().upper()
            if not tercero:
                continue
            dimensiones = self._dimensiones_paginas(
                Path(str(ejemplo.get("origen_path") or ""))
            )
            campos = {}
            for campo, marca in marcas.items():
                normalizada = self._normalizar_marca(marca, dimensiones)
                if normalizada:
                    campos[str(campo)] = normalizada
            if campos:
                grupos.setdefault((tipo, tercero), []).append({
                    "campos": campos, "ejemplo_id": ejemplo.get("id"),
                })

        entrenados = 0
        for (tipo, tercero), muestras in grupos.items():
            por_campo: dict[str, list[dict]] = {}
            for muestra in muestras:
                for campo, marca in muestra["campos"].items():
                    por_campo.setdefault(campo, []).append(marca)
            campos_modelo = {}
            for campo, marcas in por_campo.items():
                paginas = [int(m["page"]) for m in marcas]
                campos_modelo[campo] = {
                    "page": int(round(statistics.median(paginas))),
                    "x": round(statistics.median(m["x"] for m in marcas), 6),
                    "y": round(statistics.median(m["y"] for m in marcas), 6),
                    "width": round(statistics.median(m["width"] for m in marcas), 6),
                    "height": round(statistics.median(m["height"] for m in marcas), 6),
                    "muestras": len(marcas),
                }
            if not campos_modelo:
                continue
            self._gestor.upsert_modelo_ocr_local({
                "id": str(uuid.uuid4()), "empresa_id": self._empresa_id,
                "tipo_documento": tipo, "tercero_nif": tercero,
                "ejemplos": len(muestras),
                "campos_json": json.dumps(campos_modelo, ensure_ascii=True),
                "metricas_json": json.dumps({
                    "campos": len(campos_modelo),
                    "muestras_por_campo": {
                        campo: len(marcas) for campo, marcas in por_campo.items()
                    },
                }, ensure_ascii=True),
                "estado": "activo",
                "entrenado_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            })
            entrenados += 1
        return {"modelos_entrenados": entrenados, "ejemplos_revisados": len(ejemplos)}

    def aplicar_modelo_local(
        self, path: str | Path, resultado, tipo_documento: str = "factura_recibida",
    ):
        """Completa el resultado OCR usando el modelo aprendido aplicable."""
        if not hasattr(self._gestor, "listar_modelos_ocr_locales"):
            return resultado
        modelos = self._gestor.listar_modelos_ocr_locales(
            self._empresa_id, tipo_documento,
        )
        modelo = self._seleccionar_modelo(modelos, resultado)
        if not modelo:
            return resultado
        try:
            campos = json.loads(modelo.get("campos_json") or "{}")
            extraidos = self._extraer_campos(Path(path), campos)
        except Exception:
            return resultado
        aplicados = {}
        mapa = {
            "ProveedorNif": "proveedor_nif",
            "ProveedorNombre": "proveedor_nombre",
            "ClienteNif": "cliente_nif", "ClienteNombre": "cliente_nombre",
            "NumeroFactura": "numero_factura", "FechaFactura": "fecha_factura",
            "FechaVencimiento": "fecha_vencimiento",
        }
        importes = {
            "BaseTotal": "base_total", "IvaTotal": "iva_total",
            "TotalFactura": "total",
        }
        for campo, atributo in mapa.items():
            valor = str(extraidos.get(campo) or "").strip()
            if valor:
                setattr(resultado, atributo, valor)
                aplicados[campo] = valor
        for campo, atributo in importes.items():
            valor = self._importe(extraidos.get(campo))
            if valor is not None:
                setattr(resultado, atributo, valor)
                aplicados[campo] = valor
        if aplicados:
            resultado.raw_json = dict(resultado.raw_json or {})
            resultado.raw_json["modelo_local"] = {
                "id": modelo.get("id"), "version": modelo.get("version"),
                "tercero_nif": modelo.get("tercero_nif"), "campos": aplicados,
            }
            resultado.motor = f"{resultado.motor}+modelo_local_v{modelo.get('version') or 1}"
            resultado.confianza = max(float(resultado.confianza or 0), 0.75)
        return resultado

    @staticmethod
    def _seleccionar_modelo(modelos: list[dict], resultado):
        def clave(value):
            return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
        nif = clave(getattr(resultado, "proveedor_nif", ""))
        texto = clave(getattr(resultado, "texto", ""))
        for modelo in modelos:
            tercero = clave(modelo.get("tercero_nif"))
            if tercero and (tercero == nif or tercero in texto):
                return modelo
        return None

    @staticmethod
    def _dimensiones_paginas(path: Path) -> dict[int, tuple[float, float]]:
        if not path.is_file():
            return {}
        if path.suffix.lower() == ".pdf":
            try:
                import fitz
                with fitz.open(path) as pdf:
                    return {
                        numero: (
                            float(pagina.rect.width) * 1.5,
                            float(pagina.rect.height) * 1.5,
                        )
                        for numero, pagina in enumerate(pdf)
                    }
            except Exception:
                return {}
        try:
            from PIL import Image
            with Image.open(path) as image:
                image.thumbnail((1250, 1200))
                return {0: (float(image.width), float(image.height))}
        except Exception:
            return {}

    @staticmethod
    def _normalizar_marca(marca: dict, dimensiones: dict) -> dict | None:
        try:
            page = int(marca.get("page") or 0)
            ancho, alto = dimensiones[page]
            x = float(marca["x"]) / ancho
            y = float(marca["y"]) / alto
            width = float(marca["width"]) / ancho
            height = float(marca["height"]) / alto
            if min(width, height) <= 0:
                return None
            return {"page": page, "x": x, "y": y, "width": width, "height": height}
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return None

    @staticmethod
    def _extraer_campos(path: Path, campos: dict) -> dict:
        if path.suffix.lower() != ".pdf" or not path.is_file():
            return {}
        import fitz
        extraidos = {}
        with fitz.open(path) as pdf:
            for campo, marca in campos.items():
                page_no = int(marca.get("page") or 0)
                if page_no < 0 or page_no >= len(pdf):
                    continue
                pagina = pdf.load_page(page_no)
                rect = pagina.rect
                zona = fitz.Rect(
                    float(marca["x"]) * rect.width,
                    float(marca["y"]) * rect.height,
                    (float(marca["x"]) + float(marca["width"])) * rect.width,
                    (float(marca["y"]) + float(marca["height"])) * rect.height,
                )
                texto = pagina.get_text("text", clip=zona).strip().replace("\n", " ")
                if texto:
                    extraidos[str(campo)] = " ".join(texto.split())
        return extraidos

    @staticmethod
    def _importe(value) -> float | None:
        raw = str(value or "").strip().replace("€", "").replace(" ", "")
        raw = re.sub(r"[^0-9,.-]", "", raw)
        if not raw:
            return None
        if "," in raw and "." in raw:
            raw = raw.replace(".", "").replace(",", ".")
        elif "," in raw:
            raw = raw.replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            return None

    def exportar_via_backend(
        self, *, base_url: str, api_key: str, timeout: int = 120,
    ) -> dict:
        """Envia ejemplos al backend, unico propietario de las claves Azure."""
        base_url = str(base_url or "").strip().rstrip("/")
        api_key = str(api_key or "").strip()
        if not base_url or not api_key:
            raise ValueError(
                "Faltan integrations_api_url o el WorkstationToken del puesto."
            )
        ejemplos = self._gestor.listar_ejemplos_aprendizaje_ocr(self._empresa_id, "pendiente")
        if not ejemplos:
            return {"subidos": 0, "omitidos": 0, "errores": []}

        import requests

        subidos = 0
        omitidos = 0
        errores = []
        for ejemplo in ejemplos:
            origen = Path(str(ejemplo.get("origen_path") or ""))
            if not origen.is_file():
                omitidos += 1
                errores.append(f"Ejemplo {ejemplo.get('id')}: no se encuentra el documento.")
                continue
            metadata = {
                "documento_id": ejemplo.get("documento_id"),
                "factura_id": ejemplo.get("factura_id"),
                "campos": json.loads(ejemplo.get("datos_validados_json") or "{}"),
                "marcas": json.loads(ejemplo.get("marcas_json") or "{}"),
                "fecha_validacion": ejemplo.get("fecha_validacion"),
            }
            content_type = mimetypes.guess_type(origen.name)[0] or "application/octet-stream"
            try:
                with origen.open("rb") as fh:
                    response = requests.post(
                        f"{base_url}/api/v1/ocr/training/examples",
                        headers={"X-API-Key": api_key},
                        data={
                            "empresa_id": self._empresa_id,
                            "ejemplo_id": str(ejemplo["id"]),
                            "metadata_json": json.dumps(metadata, ensure_ascii=True),
                        },
                        files={"file": (origen.name, fh, content_type)},
                        timeout=timeout,
                    )
                if response.status_code >= 400:
                    try:
                        detalle = response.json().get("detail", response.text)
                    except Exception:
                        detalle = response.text
                    raise RuntimeError(
                        f"Backend OCR error {response.status_code}: {detalle}"
                    )
                resultado = response.json()
                ejemplo["estado"] = "exportado"
                ejemplo["modelo_destino"] = str(resultado.get("container") or "")
                ejemplo["fecha_exportacion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ejemplo["notas"] = (
                    "Exportado por el backend a Azure Blob; pendiente de "
                    "etiquetado/entrenamiento en Studio."
                )
                self._gestor.upsert_ejemplo_aprendizaje_ocr(ejemplo)
                subidos += 1
            except Exception as exc:
                omitidos += 1
                errores.append(f"Ejemplo {ejemplo.get('id')}: {exc}")
        return {"subidos": subidos, "omitidos": omitidos, "errores": errores}
