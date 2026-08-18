"""Cola local de aprendizaje supervisado para facturas OCR."""
from __future__ import annotations

import json
import os
import re
import shutil
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
        return self._gestor.upsert_ejemplo_aprendizaje_ocr({
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
        return self._gestor.resumen_aprendizaje_ocr(self._empresa_id)

    def exportar_a_blob(self, *, connection_string: str, container: str, prefijo: str = "gest2a3eco") -> dict:
        """Sube documentos validados y un manifiesto auditable al contenedor.

        Document Intelligence Studio permite revisar/etiquetar estos PDF desde
        el mismo contenedor. No marca campos silenciosamente en produccion.
        """
        if (not connection_string or connection_string.startswith("CADENA_DE_CONEXION")
                or not container):
            raise ValueError(
                "Falta azure_storage_connection_string en config.local.json. "
                "Debe ser la cadena real de la cuenta gest2a3ocrtrain260805, no el texto de ejemplo."
            )
        try:
            from azure.storage.blob import BlobServiceClient, ContentSettings
        except ImportError as exc:
            raise RuntimeError("Instala azure-storage-blob para exportar el aprendizaje a Azure.") from exc
        ejemplos = self._gestor.listar_ejemplos_aprendizaje_ocr(self._empresa_id, "pendiente")
        if not ejemplos:
            return {"subidos": 0, "omitidos": 0, "manifiesto": ""}
        cliente = BlobServiceClient.from_connection_string(connection_string)
        cont = cliente.get_container_client(container)
        try:
            cont.create_container()
        except Exception as exc:
            # El contenedor ya existe: las versiones antiguas del SDK no
            # admiten exist_ok en create_container().
            if ("ContainerAlreadyExists" not in str(exc)
                    and "ResourceExistsError" not in type(exc).__name__
                    and "already exists" not in str(exc).lower()):
                raise
        manifiesto = []
        subidos = 0
        for ejemplo in ejemplos:
            origen = Path(str(ejemplo.get("origen_path") or ""))
            if not origen.is_file():
                continue
            nombre = re.sub(r"[^A-Za-z0-9_.-]+", "_", origen.name)
            blob_name = f"{prefijo}/{self._empresa_id}/{ejemplo['id']}_{nombre}"
            with origen.open("rb") as fh:
                cont.upload_blob(blob_name, fh, overwrite=True, content_settings=ContentSettings(content_type="application/pdf"))
            manifiesto.append({
                "ejemplo_id": ejemplo["id"], "documento_id": ejemplo.get("documento_id"),
                "blob": blob_name, "campos": json.loads(ejemplo.get("datos_validados_json") or "{}"),
                "marcas": json.loads(ejemplo.get("marcas_json") or "{}"),
            })
            subidos += 1
        manifest_name = f"{prefijo}/{self._empresa_id}/manifest.jsonl"
        datos = "".join(json.dumps(fila, ensure_ascii=True) + "\n" for fila in manifiesto).encode("utf-8")
        cont.upload_blob(manifest_name, datos, overwrite=True, content_settings=ContentSettings(content_type="application/json"))
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for ejemplo in ejemplos:
            if any(int(f["ejemplo_id"]) == int(ejemplo["id"]) for f in manifiesto):
                ejemplo["estado"] = "exportado"
                ejemplo["modelo_destino"] = container
                ejemplo["fecha_exportacion"] = ahora
                ejemplo["notas"] = "Exportado a Azure Blob; pendiente de etiquetado/entrenamiento en Studio."
                self._gestor.upsert_ejemplo_aprendizaje_ocr(ejemplo)
        return {"subidos": subidos, "omitidos": len(ejemplos) - subidos, "manifiesto": manifest_name}
