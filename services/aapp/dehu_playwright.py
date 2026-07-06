"""
Conector DEHu (Direccion Electronica Habilitada unica) por automatizacion de
navegador con el certificado del cliente (Opcion A).

Realidad tecnica del portal (verificada con volcados reales)
------------------------------------------------------------
- DEHu (https://dehu.redsara.es) es una aplicacion Angular (SPA).
- El acceso ("Acceder a DEHu") redirige a Cl@ve; se elige "DNIe / Certificado
  electronico". El certificado TLS lo pide Cl@ve/@firma (*.clave.gob.es).
- Ya autenticado, los datos se sirven por una API REST interna:
    GET /api/v1/notifications?limit=&page=            -> pendientes  {count,total,limit,page,items[]}
    GET /api/v1/realized_notifications?limit=&page=   -> realizadas
  Campos de cada item: identifier, concept, emitterEntity, emitterSourceEntity,
  nifTitular, sentReference, availabilityDate, expirationDate, bondType, state...
  Por eso, tras autenticar, llamamos DIRECTAMENTE a esa API (reutilizando la
  sesion del navegador) y paginamos, en lugar de raspar el DOM.

Puesta en marcha (modo aprendizaje)
-----------------------------------
La 1a vez: navegador visible + pausa para identificarte a mano con el certificado.
Se graba la API en la carpeta de diagnostico. Requiere:
    pip install playwright && playwright install chromium
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime

from .base import (
    ConectorOrganismo,
    NotificacionDTO,
    OpcionesSync,
    ResultadoSync,
    registrar_conector,
)

DEHU_URL_DEFECTO = "https://dehu.redsara.es"

ORIGENES_CLAVE = [
    "https://se-pasarela.clave.gob.es",
    "https://pasarela.clave.gob.es",
    "https://afirma.clave.gob.es",
    "https://componentes.clave.gob.es",
]

_RED_IGNORAR = re.compile(r"(visitas-web|ruxit|ruxitagent|action_name=|/beacon|google|matomo)", re.I)

# Endpoints REST de DEHu (pendientes y realizadas).
_ENDPOINTS = ("/api/v1/notifications", "/api/v1/realized_notifications")


class ConectorDEHU(ConectorOrganismo):
    codigo_organismo = "DEHU"

    def __init__(self, base_url=None):
        self.base_url = (base_url or DEHU_URL_DEFECTO).rstrip("/")

    def sincronizar(self, buzon, cert_material, opciones):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return ResultadoSync(
                ok=False, organismo_codigo=self.codigo_organismo,
                mensaje="Playwright no esta instalado. Ejecuta: pip install playwright && playwright install chromium",
                error_detalle="ModuleNotFoundError: playwright",
            )

        base = (buzon.get("url_portal") or self.base_url).rstrip("/")
        opciones.trace(f"[DEHU] abriendo {base} con certificado '{cert_material.nombre}'")

        origenes = [base] + ORIGENES_CLAVE + list(opciones.origenes_certificado or [])
        client_certs = [{
            "origin": o,
            "pfxPath": cert_material.ruta_archivo,
            "passphrase": cert_material.password or "",
        } for o in origenes]

        page = None
        capturas = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=opciones.headless)
                try:
                    context = browser.new_context(
                        accept_downloads=True,
                        ignore_https_errors=False,
                        client_certificates=client_certs,
                    )
                except TypeError as exc:
                    browser.close()
                    return ResultadoSync(
                        ok=False, organismo_codigo=self.codigo_organismo,
                        mensaje=("Tu version de Playwright no soporta 'client_certificates'. "
                                 "Actualiza:  pip install -U playwright"),
                        error_detalle=str(exc),
                    )
                context.set_default_timeout(opciones.timeout_ms)
                page = context.new_page()

                if opciones.capturar_red:
                    self._instalar_captura_red(page, capturas, opciones)

                try:
                    notifs = self._flujo(page, base, buzon, cert_material, opciones, capturas)
                    return ResultadoSync(
                        ok=True, organismo_codigo=self.codigo_organismo,
                        notificaciones=notifs,
                        mensaje=f"{len(notifs)} notificacion(es) detectada(s).",
                    )
                except Exception:
                    self._diagnostico(page, opciones, "error", capturas, forzar=True)
                    raise
                finally:
                    context.close()
                    browser.close()
        except Exception as exc:
            import traceback
            return ResultadoSync(
                ok=False, organismo_codigo=self.codigo_organismo,
                mensaje=f"Error accediendo a DEHu: {exc}",
                error_detalle=traceback.format_exc(),
            )

    def _flujo(self, page, base, buzon, cert_material, opciones, capturas):
        page.goto(base + "/", wait_until="domcontentloaded")
        self._diagnostico(page, opciones, "01_inicio", capturas)

        if self._click_acceder(page, opciones):
            page.wait_for_load_state("networkidle")
            self._diagnostico(page, opciones, "02_tras_acceder", capturas)

        self._elegir_certificado_clave(page, opciones)
        self._diagnostico(page, opciones, "03_clave", capturas)

        if opciones.pausa_login_segundos > 0:
            opciones.trace(
                "[DEHU] MODO APRENDIZAJE: identificate con el certificado en la ventana. "
                f"Esperando hasta {opciones.pausa_login_segundos}s..."
            )
            self._esperar_login(page, base, opciones)
            self._diagnostico(page, opciones, "04_autenticado", capturas, forzar=True)

        # Fuente principal: API REST interna (reutiliza la sesion autenticada).
        registros = self._fetch_api(page, base, opciones)
        self._diagnostico(page, opciones, "05_listado", capturas, forzar=True)
        if registros:
            return self._map_registros(registros, cert_material, opciones.nif_filtro)
        # Respaldo: lo capturado por red o el DOM.
        notifs = self._desde_capturas(capturas, cert_material, opciones.nif_filtro)
        if not notifs:
            self._abrir_notificaciones(page, base, opciones)
            notifs = self._extraer_tabla(page, buzon, cert_material)
        return notifs

    # ── API REST ───────────────────────────────────────────────────────
    def _fetch_api(self, page, base, opciones):
        """Llama a los endpoints REST paginando. Devuelve lista de items dict."""
        registros = []
        try:
            req = page.context.request
        except Exception:
            return registros
        nif_raw = (opciones.nif_filtro or "").strip().upper()
        filtro = f"&titularNif={nif_raw}" if nif_raw else ""
        for endpoint in _ENDPOINTS:
            page_num = 1
            while True:
                url = f"{base}{endpoint}?limit=100&page={page_num}{filtro}"
                try:
                    resp = req.get(url, timeout=opciones.timeout_ms)
                    if not resp.ok:
                        opciones.trace(f"[DEHU][api] {resp.status} {url}")
                        break
                    data = resp.json()
                except Exception as exc:
                    opciones.trace(f"[DEHU][api] error {endpoint}: {exc}")
                    break
                items = data.get("items") if isinstance(data, dict) else None
                if not items:
                    break
                for it in items:
                    if isinstance(it, dict):
                        it["_endpoint"] = endpoint
                registros.extend(items)
                total = (data.get("total") or 0) if isinstance(data, dict) else 0
                limit = (data.get("limit") or 100) if isinstance(data, dict) else 100
                opciones.trace(f"[DEHU][api] {endpoint} pagina {page_num}: {len(items)} (total {total})")
                if page_num * (limit or 100) >= total:
                    break
                page_num += 1
        return registros

    def _map_registros(self, registros, cert_material, nif_filtro=None):
        objetivo = _norm_nif(nif_filtro) if nif_filtro else None
        notifs = []
        vistos = set()
        for r in registros:
            if not isinstance(r, dict):
                continue
            if objetivo and _norm_nif(r.get("nifTitular")) != objetivo:
                continue
            ref = r.get("identifier") or r.get("sentReference")
            if not ref or ref in vistos:
                continue
            vistos.add(ref)
            realizada = "realized" in (r.get("_endpoint") or "")
            estado = r.get("state") or ("REALIZADA" if realizada else "PENDIENTE")
            notifs.append(NotificacionDTO(
                referencia=str(ref),
                asunto=r.get("concept") or "(sin asunto)",
                descripcion=r.get("emitterEntity"),
                tipo_acto=r.get("bondType"),
                nif_interesado=r.get("nifTitular") or cert_material.nif_titular,
                nombre_interesado=cert_material.nombre,
                fecha_puesta_disposicion=_norm_fecha(r.get("availabilityDate")),
                fecha_vencimiento=_norm_fecha(r.get("expirationDate")),
                estado=_map_estado(estado),
                metadatos={
                    "emitterSourceEntity": r.get("emitterSourceEntity"),
                    "sentReference": r.get("sentReference"),
                    "endpoint": r.get("_endpoint"),
                    "finalDate": r.get("finalDate"),
                    "raw": r,
                },
            ))
        return notifs

    # ── red / captura (respaldo y diagnostico) ─────────────────────────
    def _instalar_captura_red(self, page, capturas, opciones):
        def _on_response(resp):
            try:
                url = resp.url
                if _RED_IGNORAR.search(url):
                    return
                try:
                    rt = resp.request.resource_type
                except Exception:
                    rt = ""
                ct = (resp.headers or {}).get("content-type", "")
                if rt not in ("xhr", "fetch") and "json" not in ct.lower():
                    return
                body = None
                if "json" in ct.lower():
                    try:
                        body = resp.json()
                    except Exception:
                        try:
                            body = resp.text()
                        except Exception:
                            body = None
                capturas.append({"url": url, "status": resp.status,
                                 "resource_type": rt, "content_type": ct, "body": body})
                opciones.trace(f"[DEHU][xhr] {resp.status} {rt} {url}")
            except Exception:
                pass
        page.on("response", _on_response)

    def _esperar_login(self, page, base, opciones):
        """Espera a que la sesion quede autenticada (la API responde 200)."""
        fin = time.time() + opciones.pausa_login_segundos
        while time.time() < fin:
            page.wait_for_timeout(2000)
            try:
                resp = page.context.request.get(f"{base}/api/v1/notifications?limit=1&page=1",
                                                 timeout=8000)
                if resp.ok:
                    page.wait_for_timeout(1000)
                    return
            except Exception:
                continue

    def _desde_capturas(self, capturas, cert_material, nif_filtro=None):
        registros = []
        for cap in capturas:
            body = cap.get("body")
            if isinstance(body, dict) and isinstance(body.get("items"), list):
                for it in body["items"]:
                    if isinstance(it, dict):
                        it.setdefault("_endpoint", cap.get("url", ""))
                registros.extend(body["items"])
        return self._map_registros(registros, cert_material, nif_filtro)

    # ── clicks tolerantes ──────────────────────────────────────────────
    def _click_acceder(self, page, opciones):
        selectores = [
            '[aria-label="Acceder a DEHú"]',
            '[aria-label="Acceder a DEHu"]',
            'text=Acceder a DEH',
            '.access-btn',
        ]
        for sel in selectores:
            try:
                el = page.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=6000)
                    opciones.trace(f"[DEHU] click acceso via '{sel}'")
                    return True
            except Exception:
                continue
        opciones.trace("[DEHU] no se encontro el boton 'Acceder a DEHu'")
        return False

    def _elegir_certificado_clave(self, page, opciones):
        selectores = [
            "text=Acceso DNIe / Certificado electr",
            "text=DNIe / Certificado electr",
            "text=Certificado electr",
            "text=DNIe",
            "#certificateButton",
            "[id*='certificad']",
        ]
        for sel in selectores:
            try:
                el = page.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=5000)
                    page.wait_for_load_state("networkidle")
                    opciones.trace(f"[DEHU] acceso por certificado via '{sel}'")
                    return
            except Exception:
                continue

    def _abrir_notificaciones(self, page, base, opciones):
        for sel in ('text=Notificaciones pendientes', 'a:has-text("Notificaciones")', 'text=Notificaciones'):
            try:
                el = page.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=6000)
                    page.wait_for_load_state("networkidle")
                    return True
            except Exception:
                continue
        return False

    def _hay_tabla(self, page):
        try:
            return page.locator("table tbody tr, [role='row']").count() > 0
        except Exception:
            return False

    def _extraer_tabla(self, page, buzon, cert_material):
        notifs = []
        try:
            filas = page.locator("table tbody tr")
            n = filas.count()
        except Exception:
            return notifs
        for i in range(n):
            fila = filas.nth(i)
            celdas = fila.locator("td")
            textos = []
            for j in range(celdas.count()):
                try:
                    textos.append((celdas.nth(j).inner_text() or "").strip())
                except Exception:
                    textos.append("")
            if not any(textos):
                continue
            notifs.append(NotificacionDTO(
                referencia="DEHU-DOM-" + str(i),
                asunto=(textos[1] if len(textos) > 1 else textos[0]) or "(sin asunto)",
                descripcion=textos[0] if textos else None,
                nif_interesado=cert_material.nif_titular,
                nombre_interesado=cert_material.nombre,
                fecha_puesta_disposicion=_primera_fecha(textos),
                metadatos={"celdas": textos},
            ))
        return notifs

    def _diagnostico(self, page, opciones, etiqueta, capturas, forzar=False):
        if not (opciones.modo_diagnostico or forzar) or page is None:
            return
        carpeta = opciones.carpeta_diagnostico or opciones.carpeta_descargas or os.getcwd()
        os.makedirs(carpeta, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            page.screenshot(path=os.path.join(carpeta, f"dehu_{etiqueta}_{ts}.png"), full_page=True)
            with open(os.path.join(carpeta, f"dehu_{etiqueta}_{ts}.html"), "w", encoding="utf-8") as fh:
                fh.write(page.content())
            if capturas:
                with open(os.path.join(carpeta, f"dehu_api_{etiqueta}_{ts}.json"), "w", encoding="utf-8") as fh:
                    json.dump(capturas, fh, ensure_ascii=False, indent=2, default=str)
            opciones.trace(f"[DEHU] diagnostico '{etiqueta}' guardado en {carpeta}")
        except Exception as exc:
            opciones.trace(f"[DEHU] no se pudo guardar diagnostico '{etiqueta}': {exc}")


# ── helpers ────────────────────────────────────────────────────────────────
_FECHA_RE = re.compile(r"\b(\d{2})[/-](\d{2})[/-](\d{4})\b")
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})")


def _norm_fecha(v):
    if not v:
        return None
    s = str(v)
    m = _ISO_RE.search(s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = _FECHA_RE.search(s)
    if m:
        d, mth, y = m.groups()
        return f"{y}-{mth}-{d}"
    return None


def _primera_fecha(textos):
    for t in textos:
        f = _norm_fecha(t)
        if f:
            return f
    return None


def _norm_nif(v):
    return re.sub(r"[^0-9A-Z]", "", str(v or "").upper())


def _map_estado(s):
    s = (s or "").upper()
    if "ACEPTAD" in s:
        return "ACEPTADA"
    if "RECHAZ" in s:
        return "RECHAZADA"
    if "LEID" in s or "LEÍD" in s:
        return "LEIDA"
    return "PENDIENTE"


registrar_conector(ConectorDEHU())
