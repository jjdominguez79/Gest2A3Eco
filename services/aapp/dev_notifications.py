"""Consulta pasiva del buzon DGT/Direccion Electronica Vial (DEV)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .base import (
    ConectorOrganismo,
    NotificacionDTO,
    OpcionesSync,
    ResultadoSync,
    registrar_conector,
)
from .cert_store import preparar_pfx_para_navegador
from .dev_playwright import DEV_LIST_URL, DEV_ORIGIN, _clasificar_estado
from utils.estados_dehu import normalizar_estado_dehu


class ConectorDEV(ConectorOrganismo):
    codigo_organismo = "DEV"

    def sincronizar(self, buzon, cert_material, opciones):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            return ResultadoSync(
                False, self.codigo_organismo,
                mensaje=f"Playwright no esta disponible: {exc}",
            )

        temp_dir = Path(os.path.dirname(cert_material.ruta_archivo))
        pfx_path = ""
        browser = None
        context = None
        try:
            pfx_path, pfx_password = preparar_pfx_para_navegador(
                cert_material, str(temp_dir / "navegador-dev.pfx"),
            )
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=opciones.headless)
                context = browser.new_context(client_certificates=[{
                    "origin": DEV_ORIGIN,
                    "pfxPath": pfx_path,
                    "passphrase": pfx_password,
                }], locale="es-ES", timezone_id="Europe/Madrid")
                context.set_default_timeout(opciones.timeout_ms)
                page = context.new_page()
                response = page.goto(
                    DEV_LIST_URL, wait_until="domcontentloaded",
                    timeout=opciones.timeout_ms,
                )
                try:
                    page.wait_for_load_state("networkidle", timeout=min(opciones.timeout_ms, 30000))
                except Exception:
                    pass
                page.wait_for_timeout(1200)
                texto = "\n".join(
                    value for value in page.locator("body").all_inner_texts()
                    if value.strip()
                )
                estado_acceso = _clasificar_estado(
                    texto, page.url, response.status if response else 0,
                )
                if estado_acceso == "NO_ALTA":
                    return ResultadoSync(
                        True, self.codigo_organismo,
                        mensaje=(
                            "NO_ALTA: El titular del certificado no esta dado "
                            "de alta en la Direccion Electronica Vial."
                        ),
                    )
                if estado_acceso != "AUTENTICADO":
                    return ResultadoSync(
                        False, self.codigo_organismo,
                        mensaje="DEV no reconocio una sesion autenticada con el certificado.",
                    )
                filas = self._extraer_filas(page)
                notificaciones = self._map_filas(
                    filas,
                    nif=cert_material.nif_titular or opciones.nif_filtro or "",
                    nombre=cert_material.nombre,
                )
                self._diagnostico(page, opciones, filas)
                return ResultadoSync(
                    True, self.codigo_organismo,
                    notificaciones=notificaciones,
                    mensaje=f"ACTIVO: {len(notificaciones)} elemento(s) DEV detectado(s).",
                )
        except Exception as exc:
            import traceback
            return ResultadoSync(
                False, self.codigo_organismo,
                mensaje=f"Error accediendo a DGT/DEV: {exc}",
                error_detalle=traceback.format_exc(),
            )
        finally:
            for resource in (context, browser):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        pass
            if pfx_path:
                try:
                    Path(pfx_path).unlink(missing_ok=True)
                except Exception:
                    pass

    @staticmethod
    def _extraer_filas(page) -> list[dict]:
        """Extrae filas visibles sin abrir ni actuar sobre una notificacion."""
        return page.evaluate("""
            () => Array.from(document.querySelectorAll('table')).flatMap((table) => {
              const headers = Array.from(table.querySelectorAll('thead th, tr th'))
                .map((cell) => (cell.innerText || '').trim());
              return Array.from(table.querySelectorAll('tbody tr, tr')).map((row) => {
                const cells = Array.from(row.querySelectorAll(':scope > td'));
                if (cells.length < 2) return null;
                const values = cells.map((cell) => (cell.innerText || '').trim());
                const links = Array.from(row.querySelectorAll('a')).map((link) => ({
                  text: (link.innerText || '').trim(),
                  href: link.href || '', id: link.id || '', title: link.title || ''
                }));
                return {headers, values, text: (row.innerText || '').trim(), links};
              }).filter(Boolean);
            })
        """) or []

    @classmethod
    def _map_filas(cls, filas: list[dict], *, nif: str, nombre: str) -> list[NotificacionDTO]:
        resultado = []
        vistos = set()
        for fila in filas:
            texto = " ".join(str(fila.get("text") or "").split())
            if not texto or not _parece_notificacion(texto):
                continue
            headers = [str(value or "") for value in fila.get("headers") or []]
            values = [str(value or "").strip() for value in fila.get("values") or []]
            columnas = {
                _normalizar(header): values[index]
                for index, header in enumerate(headers)
                if index < len(values) and header.strip()
            }
            referencia = _valor_columna(columnas, "REFERENCIA", "EXPEDIENTE", "IDENTIFICADOR")
            if not referencia:
                referencia = _referencia_enlaces(fila.get("links") or [])
            if not referencia:
                referencia = "DEV-" + hashlib.sha256(texto.encode("utf-8")).hexdigest()[:24]
            if referencia in vistos:
                continue
            vistos.add(referencia)
            fecha_disponible, fecha_vencimiento = _fechas_fila(columnas, texto)
            estado_texto = _valor_columna(columnas, "ESTADO", "SITUACION") or texto
            asunto = _valor_columna(
                columnas, "ASUNTO", "CONCEPTO", "DESCRIPCION", "NOTIFICACION",
            ) or texto[:500]
            organismo = _valor_columna(
                columnas, "ORGANISMO", "EMISOR", "REMITENTE",
            ) or "Direccion General de Trafico"
            tipo = _valor_columna(columnas, "TIPO", "CLASE") or "NOTIFICACION"
            resultado.append(NotificacionDTO(
                referencia=referencia[:300],
                asunto=asunto[:500],
                descripcion=organismo[:500],
                tipo_acto=tipo[:120],
                nif_interesado=nif,
                nombre_interesado=nombre,
                fecha_puesta_disposicion=fecha_disponible,
                fecha_vencimiento=fecha_vencimiento,
                estado=normalizar_estado_dehu(estado_texto),
                metadatos={
                    "provider": "DEV",
                    "row": {"headers": headers, "values": values},
                    "endpoint": urlsplit(DEV_LIST_URL).path,
                },
            ))
        return resultado

    @staticmethod
    def _diagnostico(page, opciones: OpcionesSync, filas: list[dict]) -> None:
        if not opciones.modo_diagnostico or not opciones.carpeta_diagnostico:
            return
        destino = Path(opciones.carpeta_diagnostico)
        destino.mkdir(parents=True, exist_ok=True)
        # Solo estructura de filas; nunca se guardan cookies, PFX ni HTML de sesion.
        (destino / "dev_filas.json").write_text(
            json.dumps(filas, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        page.screenshot(path=str(destino / "dev_listado.png"), full_page=True)


def _normalizar(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", str(value or "").upper())
        if unicodedata.category(char) != "Mn"
    )


def _valor_columna(columnas: dict, *aliases: str) -> str:
    for key, value in columnas.items():
        if any(alias in key for alias in aliases) and str(value or "").strip():
            return str(value).strip()
    return ""


def _referencia_enlaces(links: list[dict]) -> str:
    for link in links:
        href = str(link.get("href") or "")
        query = parse_qs(urlsplit(href).query)
        for key in ("id", "referencia", "expediente", "notificacion"):
            value = (query.get(key) or [""])[0].strip()
            if value:
                return value
        for value in (link.get("id"), link.get("title"), link.get("text")):
            match = re.search(r"[A-Z0-9][A-Z0-9/_-]{7,}", str(value or ""), re.I)
            if match:
                return match.group(0)
    return ""


def _fechas_fila(columnas: dict, texto: str) -> tuple[str | None, str | None]:
    available = _valor_columna(
        columnas, "PUESTA A DISPOSICION", "RECEPCION", "ALTA", "FECHA",
    )
    expiration = _valor_columna(
        columnas, "VENCIMIENTO", "CADUCIDAD", "LIMITE",
    )
    matches = re.findall(r"\b(?:\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})\b", texto)
    if not available and matches:
        available = matches[0]
    if not expiration and len(matches) > 1:
        expiration = matches[1]
    return available or None, expiration or None


def _parece_notificacion(texto: str) -> bool:
    normal = _normalizar(texto)
    return bool(
        re.search(r"\b\d{2}/\d{2}/\d{4}\b|\b\d{4}-\d{2}-\d{2}\b", texto)
        or any(word in normal for word in (
            "PENDIENTE", "LEIDA", "ACEPTADA", "RECHAZADA", "CADUCADA",
            "NOTIFICACION", "COMUNICACION", "EXPEDIENTE",
        ))
    ) and "NO EXISTE NINGUNA" not in normal


registrar_conector(ConectorDEV())
