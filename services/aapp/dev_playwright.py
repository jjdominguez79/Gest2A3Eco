"""Diagnostico seguro del buzon DGT/DEV.

Esta primera fase identifica la aplicacion y sus respuestas autenticadas sin
abrir, aceptar, rechazar ni descargar notificaciones. El resultado se conserva
exclusivamente en el volumen privado de diagnostico del worker.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .cert_store import CertMaterial, preparar_pfx_para_navegador


DEV_ORIGIN = "https://sedeapl.dgt.gob.es:9443"
DEV_LIST_URL = (
    DEV_ORIGIN
    + "/WEB_NTRA_CONSULTA/listadoNotificacionesIdiomaPostback.faces?idioma=es"
)


@dataclass
class ResultadoDiagnosticoDEV:
    ok: bool
    estado: str
    mensaje: str
    url_final: str = ""
    titulo: str = ""
    artefactos: list[str] = field(default_factory=list)


def diagnosticar_dev(
    material: CertMaterial,
    *,
    carpeta_diagnostico: str,
    headless: bool = True,
    timeout_ms: int = 60000,
) -> ResultadoDiagnosticoDEV:
    """Accede a DEV en modo lectura y guarda evidencias para crear el conector."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - depende de la imagen worker
        return ResultadoDiagnosticoDEV(False, "ERROR", f"Playwright no disponible: {exc}")

    destino = Path(carpeta_diagnostico)
    destino.mkdir(parents=True, exist_ok=True)
    pfx_path = ""
    pfx_path, pfx_password = preparar_pfx_para_navegador(
        material, str(destino / "navegador.pfx"),
    )
    respuestas = []
    peticiones_fallidas = []
    artefactos = []

    def _respuesta(response):
        content_type = str(response.headers.get("content-type") or "").lower()
        registro = {
            "url": _url_sin_secretos(response.url),
            "status": response.status,
            "content_type": content_type.split(";", 1)[0],
        }
        if "json" in content_type:
            try:
                registro["json"] = response.json()
            except Exception:
                registro["json_error"] = True
        respuestas.append(registro)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            context = browser.new_context(client_certificates=[{
                "origin": DEV_ORIGIN,
                "pfxPath": pfx_path,
                "passphrase": pfx_password,
            }])
            page = context.new_page()
            page.on("response", _respuesta)
            page.on(
                "requestfailed",
                lambda request: peticiones_fallidas.append({
                    "url": _url_sin_secretos(request.url),
                    "error": str(request.failure or ""),
                }),
            )
            response = page.goto(
                DEV_LIST_URL, wait_until="domcontentloaded", timeout=timeout_ms,
            )
            try:
                page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 30000))
            except Exception:
                pass
            page.wait_for_timeout(2500)

            url_final = page.url
            titulo = page.title()
            # El portal DEV devuelve en algunas respuestas dos documentos
            # ``body`` (uno de ellos vacio). No usar el modo estricto de un
            # locator unico: unimos los textos visibles sin interactuar.
            textos = page.locator("body").all_inner_texts()
            texto = "\n".join(valor for valor in textos if valor.strip())
            html = page.content()
            estado = _clasificar_estado(texto, url_final, response.status if response else 0)

            captura = destino / "pagina.png"
            pagina_html = destino / "pagina.html"
            red_json = destino / "red.json"
            resumen_json = destino / "resumen.json"
            page.screenshot(path=str(captura), full_page=True)
            pagina_html.write_text(html, encoding="utf-8")
            red_json.write_text(json.dumps({
                "responses": respuestas,
                "request_failures": peticiones_fallidas,
            }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            resumen_json.write_text(json.dumps({
                "estado": estado,
                "url_final": _url_sin_secretos(url_final),
                "titulo": titulo,
                "texto": texto,
                "formularios": page.locator("form").count(),
                "enlaces": page.locator("a").count(),
                "botones": page.locator("button, input[type=submit]").count(),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            artefactos = [str(captura), str(pagina_html), str(red_json), str(resumen_json)]
            context.close()
            browser.close()
    except Exception as exc:
        return ResultadoDiagnosticoDEV(
            False, "ERROR", f"No se pudo abrir DEV: {exc}", artefactos=artefactos,
        )
    finally:
        # El PFX modernizado es solo una copia temporal y no debe persistir en
        # el volumen de diagnostico.
        try:
            Path(pfx_path).unlink(missing_ok=True)
        except Exception:
            pass

    mensajes = {
        "NO_ALTA": "El certificado es valido, pero su titular no esta dado de alta en DEV.",
        "AUTENTICADO": "Acceso autenticado a DEV completado en modo de solo lectura.",
        "NO_AUTENTICADO": "DEV no reconocio una sesion autenticada con este certificado.",
        "ERROR": "DEV devolvio una respuesta no valida.",
    }
    return ResultadoDiagnosticoDEV(
        estado in {"AUTENTICADO", "NO_ALTA"},
        estado,
        mensajes.get(estado, "Diagnostico DEV completado."),
        url_final=_url_sin_secretos(url_final),
        titulo=titulo,
        artefactos=artefactos,
    )


def _clasificar_estado(texto: str, url: str, status: int) -> str:
    limpio = _normalizar(texto)
    if any(fragmento in limpio for fragmento in (
        "NO ESTA DADO DE ALTA",
        "NO SE ENCUENTRA DADO DE ALTA",
        "NO ESTA SUSCRITO",
        "NO DISPONE DE DIRECCION ELECTRONICA VIAL",
        "NO TIENE DIRECCION ELECTRONICA VIAL",
    )):
        return "NO_ALTA"
    if status >= 400:
        return "ERROR"
    if "WEB_NTRA_CONSULTA" in url and any(fragmento in limpio for fragmento in (
        "NOTIFICACIONES", "DIRECCION ELECTRONICA VIAL", "DEV",
    )):
        return "AUTENTICADO"
    return "NO_AUTENTICADO"


def _normalizar(value: str) -> str:
    import unicodedata
    return "".join(
        char for char in unicodedata.normalize("NFD", str(value or "").upper())
        if unicodedata.category(char) != "Mn"
    )


def _url_sin_secretos(url: str) -> str:
    try:
        parts = urlsplit(str(url or ""))
        path = re.sub(r";jsessionid=[^/?#;]*", "", parts.path, flags=re.I)
        return urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    except Exception:
        return re.sub(r"[?#].*$", "", str(url or ""))
