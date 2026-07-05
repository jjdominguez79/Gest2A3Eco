"""
Conector DEHu (Direccion Electronica Habilitada unica) por automatizacion de
navegador con el certificado del cliente (Opcion A).

Realidad tecnica del portal (verificada con volcados reales)
------------------------------------------------------------
- DEHu (https://dehu.redsara.es) es una aplicacion Angular (SPA).
- El acceso ("Acceder a DEHu") redirige a Cl@ve; se elige "DNIe / Certificado
  electronico". El certificado TLS lo pide Cl@ve/@firma (*.clave.gob.es), por
  eso se ofrece el certificado tambien para esos origenes (ORIGENES_CLAVE).
- Ya autenticado, la lista de notificaciones se carga por XHR/fetch (API interna)
  al pulsar "Notificaciones pendientes" DENTRO de la app (routing Angular): no
  basta con navegar por URL. Por eso capturamos toda XHR/fetch JSON y abrimos la
  seccion pulsando el enlace.

Puesta en marcha (modo aprendizaje)
-----------------------------------
Navegador visible + pausa para identificarte a mano con el certificado. Durante
la pausa, PULSA "Notificaciones pendientes": se graba la XHR con los datos en la
carpeta de diagnostico (dehu_api_*.json) para fijar el mapeo definitivo.

    OpcionesSync(headless=False, pausa_login_segundos=150, modo_diagnostico=True)

Requiere:  pip install playwright  &&  playwright install chromium
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

# Ruido a ignorar en la captura de red (analitica/APM).
_RED_IGNORAR = re.compile(r"(visitas-web|ruxit|ruxitagent|action_name=|/beacon|google|matomo)", re.I)


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
                "[DEHU] MODO APRENDIZAJE: 1) identificate con el certificado; "
                "2) pulsa 'Notificaciones pendientes'. Grabando la API hasta "
                f"{opciones.pausa_login_segundos}s..."
            )
            self._esperar_datos(page, opciones, capturas)
            self._diagnostico(page, opciones, "04_autenticado", capturas, forzar=True)

        # Abrir la seccion de notificaciones DENTRO de la app (dispara la XHR).
        self._abrir_notificaciones(page, base, opciones)
        page.wait_for_timeout(2500)
        self._diagnostico(page, opciones, "05_listado", capturas, forzar=True)

        notifs = self._desde_capturas(capturas, cert_material)
        if not notifs:
            notifs = self._extraer_tabla(page, buzon, cert_material)
        return notifs

    # ── captura de red ────────────────────────────────────────────────
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

    def _esperar_datos(self, page, opciones, capturas):
        """Espera durante la pausa; corta antes si ya llego una lista de registros."""
        fin = time.time() + opciones.pausa_login_segundos
        while time.time() < fin:
            page.wait_for_timeout(2000)
            for c in capturas:
                if isinstance(c.get("body"), (list, dict)) and _buscar_lista_registros(c["body"]):
                    page.wait_for_timeout(1500)
                    return

    # ── navegacion dentro de la app ───────────────────────────────────
    def _abrir_notificaciones(self, page, base, opciones):
        selectores = [
            'text=Notificaciones pendientes',
            'a:has-text("Notificaciones pendientes")',
            'a:has-text("Notificaciones")',
            'text=Notificaciones',
        ]
        for sel in selectores:
            try:
                el = page.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=6000)
                    page.wait_for_load_state("networkidle")
                    opciones.trace(f"[DEHU] abierto 'Notificaciones' via '{sel}'")
                    return True
            except Exception:
                continue
        for ruta in ("/es/notificaciones", "/notificaciones"):
            try:
                page.goto(base + ruta, wait_until="networkidle", timeout=15000)
                return True
            except Exception:
                continue
        return False

    def _desde_capturas(self, capturas, cert_material):
        notifs = []
        for cap in capturas:
            for reg in _buscar_lista_registros(cap.get("body")):
                if not isinstance(reg, dict):
                    continue
                ref = _first(reg, ["identificador", "id", "localizador", "codigoNotificacion", "referencia"])
                if not ref:
                    continue
                notifs.append(NotificacionDTO(
                    referencia=str(ref),
                    asunto=_first(reg, ["concepto", "asunto", "titulo", "descripcion"]) or "(sin asunto)",
                    descripcion=_first(reg, ["organismoEmisor", "emisor", "organismo"]),
                    tipo_acto=_first(reg, ["tipo", "tipoEnvio", "tipoActo"]),
                    nif_interesado=_first(reg, ["nifTitular", "nif", "documentoIdentificativo"]) or cert_material.nif_titular,
                    nombre_interesado=_first(reg, ["nombreTitular", "titular", "razonSocial"]) or cert_material.nombre,
                    fecha_puesta_disposicion=_norm_fecha(_first(reg, ["fechaPuestaDisposicion", "fechaPuesta", "fechaEnvio", "fecha"])),
                    fecha_vencimiento=_norm_fecha(_first(reg, ["fechaCaducidad", "fechaLimite", "fechaVencimiento"])),
                    estado=(_first(reg, ["estado", "situacion"]) or "PENDIENTE"),
                    metadatos={"api_url": cap.get("url"), "raw": reg},
                ))
        vistos, unicas = set(), []
        for n in notifs:
            if n.referencia in vistos:
                continue
            vistos.add(n.referencia)
            unicas.append(n)
        return unicas

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
            asunto = textos[1] if len(textos) > 1 else textos[0]
            notifs.append(NotificacionDTO(
                referencia=_ref_dom(fila, textos),
                asunto=asunto or "(sin asunto)",
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


_FECHA_RE = re.compile(r"\b(\d{2})[/-](\d{2})[/-](\d{4})\b")
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})")


def _first(d, claves):
    for k in claves:
        for kk in (k, k.lower(), k.upper()):
            if kk in d and d[kk] not in (None, ""):
                return d[kk]
    return None


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


def _buscar_lista_registros(body, _prof=0):
    if _prof > 6 or body is None:
        return []
    if isinstance(body, list):
        if body and isinstance(body[0], dict):
            return body
        return []
    if isinstance(body, dict):
        for clave in ("notificaciones", "comunicaciones", "content", "items", "data",
                      "resultado", "resultados", "listaNotificaciones", "envios", "elementos"):
            v = body.get(clave)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
        for v in body.values():
            res = _buscar_lista_registros(v, _prof + 1)
            if res:
                return res
    return []


def _ref_dom(fila, textos):
    for attr in ("data-id", "data-referencia", "id"):
        try:
            val = fila.get_attribute(attr)
            if val:
                return val
        except Exception:
            pass
    import hashlib
    return "DEHU-" + hashlib.sha1("|".join(textos).encode("utf-8", "ignore")).hexdigest()[:16]


registrar_conector(ConectorDEHU())
