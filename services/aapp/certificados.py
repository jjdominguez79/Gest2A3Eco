"""
Obtencion automatizada de certificados administrativos (Hacienda, Seguridad
Social, etc.) usando el certificado digital unico del cliente (Opcion A).

Arquitectura (espejo del modulo de notificaciones):
  - TIPOS: catalogo de certificados soportados (tipo -> organismo, descripcion, url).
  - ProveedorCertificado: interfaz que implementa el flujo de cada organismo.
  - registro por tipo: obtener_proveedor(tipo).
  - solicitar_certificado(): orquesta -> resuelve el certificado del cliente,
    ejecuta el proveedor, guarda el resultado en cert_solicitudes y devuelve el DTO.

Los proveedores concretos (AEAT, TGSS...) por automatizacion de sede se calibran
igual que DEHu: primera pasada con navegador visible + diagnostico. Mientras no
esten calibrados, devuelven un resultado 'PENDIENTE' claro (no simulan exito).
"""
from __future__ import annotations

import os
import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime

from services.aapp.base import OpcionesSync
from services.aapp.cert_store import CertStore

# tipo -> (organismo, descripcion, url_sede)
TIPOS = {
    "AEAT_CORRIENTE": ("AEAT", "Estar al corriente de obligaciones tributarias",
                       "https://sede.agenciatributaria.gob.es/"),
    "AEAT_CENSAL":    ("AEAT", "Certificado de situacion censal",
                       "https://sede.agenciatributaria.gob.es/"),
    "AEAT_IAE":       ("AEAT", "Certificado de situacion en el IAE",
                       "https://sede.agenciatributaria.gob.es/"),
    "TGSS_CORRIENTE": ("TGSS", "Estar al corriente en la Seguridad Social",
                       "https://sede.seg-social.gob.es/"),
    "TGSS_COTIZACION": ("TGSS", "Certificado de situacion de cotizacion",
                        "https://sede.seg-social.gob.es/"),
    "TGSS_SUBVENCIONES": ("TGSS", "Estar al corriente - Certificado subvenciones",
                          "https://sede.seg-social.gob.es/"),
    "TGSS_LICITACION": ("TGSS", "Estar al corriente - Licitacion contratos sector publico",
                        "https://sede.seg-social.gob.es/"),
    "TGSS_ART42": ("TGSS", "Estar al corriente - Articulo 42 (subcontratacion)",
                   "https://sede.seg-social.gob.es/"),
    "TGSS_SIN_DEUDA_FECHA": ("TGSS", "Certificado sin deuda a una fecha",
                             "https://sede.seg-social.gob.es/"),
    "TGSS_INFORME_DEUDA": ("TGSS", "Informe de deuda total",
                           "https://sede.seg-social.gob.es/"),
    "TGSS_DETALLE_DEUDA": ("TGSS", "Informe detalle de deuda",
                           "https://sede.seg-social.gob.es/"),
}


@dataclass
class ResultadoCertificado:
    ok: bool
    tipo: str
    estado: str = "PENDIENTE"        # PENDIENTE / OBTENIDO / ERROR
    resultado: str | None = None     # POSITIVO / NEGATIVO (al corriente si/no), si aplica
    pdf_path: str | None = None
    referencia: str | None = None
    mensaje: str = ""
    error_detalle: str | None = None
    solicitud_id: str | None = None


class ProveedorCertificado:
    codigo_organismo: str = ""
    tipos: set = frozenset()

    def obtener(self, cert_material, tipo: str, opciones: OpcionesSync) -> ResultadoCertificado:
        raise NotImplementedError


# ── registro ────────────────────────────────────────────────────────────────
_REGISTRO: dict = {}


def registrar_proveedor(prov: ProveedorCertificado) -> None:
    for t in prov.tipos:
        _REGISTRO[t] = prov


def obtener_proveedor(tipo: str) -> ProveedorCertificado | None:
    return _REGISTRO.get(tipo)


def tipos_disponibles() -> list:
    return sorted(_REGISTRO.keys())


# ── proveedor base por automatizacion de sede (esqueleto, calibrable) ─────────
class SedePlaywrightProvider(ProveedorCertificado):
    """Abre la sede con el certificado del cliente. El flujo concreto de cada
    certificado se calibra por organismo (pendiente). Sirve de base comun."""

    def __init__(self, codigo_organismo: str, tipos: set, url_sede: str, urls: dict | None = None):
        self.codigo_organismo = codigo_organismo
        self.tipos = set(tipos)
        self.url_sede = url_sede
        self.urls = urls or {}  # url especifica por tipo (entrada directa al tramite)

    def obtener(self, cert_material, tipo: str, opciones: OpcionesSync) -> ResultadoCertificado:
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return ResultadoCertificado(
                ok=False, tipo=tipo, estado="ERROR",
                mensaje="Playwright no esta instalado. pip install playwright && playwright install chromium",
                error_detalle="ModuleNotFoundError: playwright",
            )
        client_certs = [{
            "origin": o,
            "pfxPath": cert_material.ruta_archivo,
            "passphrase": cert_material.password or "",
        } for o in self._origenes()]
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=opciones.headless)
                try:
                    ctx = browser.new_context(accept_downloads=True, client_certificates=client_certs)
                except TypeError as exc:
                    browser.close()
                    return ResultadoCertificado(ok=False, tipo=tipo, estado="ERROR",
                                                mensaje="Actualiza Playwright (client_certificates).",
                                                error_detalle=str(exc))
                ctx.set_default_timeout(opciones.timeout_ms)
                page = ctx.new_page()
                descargado = {"path": None}

                def _on_download(dl):
                    try:
                        destino = opciones.ruta_pdf_destino
                        if not destino:
                            carpeta = opciones.carpeta_descargas or os.getcwd()
                            destino = os.path.join(carpeta, dl.suggested_filename or f"cert_{tipo}.pdf")
                        os.makedirs(os.path.dirname(destino), exist_ok=True)
                        dl.save_as(destino)
                        descargado["path"] = destino
                        opciones.trace(f"[{self.codigo_organismo}] PDF guardado en {destino}")
                    except Exception as exc:
                        opciones.trace(f"[{self.codigo_organismo}] no se pudo guardar la descarga: {exc}")

                page.on("download", _on_download)

                # Captura automatica de CADA pantalla (cada carga de pagina) para
                # poder calibrar los pasos intermedios. Tambien en pestanas nuevas.
                pasos = {"n": 0}

                def _snap(pg):
                    if not opciones.modo_diagnostico:
                        return
                    try:
                        pasos["n"] += 1
                        self._diag(pg, opciones, f"{tipo}_paso{pasos['n']:02d}")
                    except Exception:
                        pass

                page.on("load", lambda: _snap(page))
                try:
                    ctx.on("page", lambda pg: pg.on("load", lambda: _snap(pg)))
                except Exception:
                    pass

                destino_url = self.urls.get(tipo) or self.url_sede
                opciones.trace(f"[{self.codigo_organismo}] abriendo {destino_url}")
                try:
                    page.goto(destino_url, wait_until="domcontentloaded")
                    try:
                        page.wait_for_selector(
                            "input[name='certificado'], form#seleccionCertificado, a.pr_enlaceDocumento",
                            timeout=15000)
                    except Exception:
                        pass
                    # SEDESS: replicar el camino real (evita ERR_TOO_MANY_REDIRECTS):
                    # desplegar acordeon + "Obtener Acceso" -> pestana del tramite.
                    if self.codigo_organismo == "TGSS":
                        page = self._ss_acceso(page, ctx, opciones)
                        try:
                            page.on("download", _on_download)
                            page.wait_for_selector(
                                "input[name='certificado'], form#seleccionCertificado, a.pr_enlaceDocumento",
                                timeout=20000)
                        except Exception:
                            pass
                    if opciones.pausa_login_segundos > 0:
                        opciones.trace(f"[{self.codigo_organismo}] modo aprendizaje: navega hasta el "
                                       f"certificado '{tipo}' y descargalo. Esperando...")
                        page.wait_for_timeout(opciones.pausa_login_segundos * 1000)
                    page.wait_for_timeout(1500)  # margen para una descarga en curso
                    # Paso de SEDESS: elegir tipo de certificado y pulsar Continuar.
                    if self._ss_generar_certificado(page, opciones, tipo):
                        page.wait_for_timeout(2000)
                    self._diag(page, opciones, tipo)
                    err = self._ss_error_mensaje(page)
                    if err:
                        return ResultadoCertificado(ok=False, tipo=tipo, estado="ERROR", mensaje=err)
                    # Localizar el documento generado (enlace) y guardarlo como PDF.
                    doc = self._descargar_documento(page, opciones, tipo)
                    ruta_pdf = descargado["path"] or doc
                    if ruta_pdf:
                        return ResultadoCertificado(
                            ok=True, tipo=tipo, estado="OBTENIDO",
                            pdf_path=ruta_pdf,
                            resultado=self._resultado_corriente(page),
                            mensaje="Certificado descargado.",
                        )
                    try:
                        url_actual = page.url
                    except Exception:
                        url_actual = "?"
                    return ResultadoCertificado(
                        ok=False, tipo=tipo, estado="PENDIENTE",
                        mensaje=(f"No se encontro el documento generado para '{tipo}'. "
                                 f"Se quedo en: {url_actual}. Comprueba si el login "
                                 "(Cl@ve/certificado) se completo o si el portal pidio "
                                 "algun dato mas (p.ej. una fecha)."),
                    )
                finally:
                    ctx.close()
                    browser.close()
        except Exception as exc:
            return ResultadoCertificado(ok=False, tipo=tipo, estado="ERROR",
                                        mensaje=f"Error accediendo a {self.codigo_organismo}: {exc}",
                                        error_detalle=traceback.format_exc())

    def _ss_login_idp(self, page, opciones):
        """En la pagina de login del IdP de la SS (idp.seg-social.es/PGIS/Login)
        elige el acceso por certificado si aparece un selector. Con el certificado
        ya ofrecido para ese dominio, muchas veces autentica solo."""
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        url = (page.url or "").lower()
        if "login" not in url and "pgis" not in url and "idp" not in url:
            return
        selectores = [
            "text=Acceso DNIe / Certificado electr",
            "text=DNIe / Certificado electr",
            "text=Certificado electr",
            "text=Acceso con certificado",
            "text=Certificado digital",
            "a[href*='ertificad']",
            "button:has-text('Certificad')",
            "[id*='ertificad']",
            "text=DNIe",
        ]
        for sel in selectores:
            try:
                el = page.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=6000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    opciones.trace(f"[TGSS] IdP: acceso por certificado via '{sel}'")
                    return
            except Exception:
                continue
        opciones.trace(f"[TGSS] IdP: no se hallo selector de certificado en {page.url}")

    def _ss_acceso(self, page, ctx, opciones):
        """En 'Informes y Certificados' despliega el acordeon de 'estar al
        corriente' y pulsa 'Obtener Acceso'. Devuelve la pagina activa (la
        pestana nueva del tramite si se abre)."""
        activa = page
        for sel in ("a.accordion-activator:has-text('estar al corriente')",
                    "text=Certificados de estar al corriente",
                    "li[aria-label*='estar al corriente'] a.accordion-activator"):
            try:
                el = page.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=5000)
                    page.wait_for_timeout(800)
                    opciones.trace("[TGSS] acordeon 'estar al corriente' desplegado")
                    break
            except Exception:
                continue
        boton = ("a[id^='btnacceder_'], a[title*='Obtener Acceso'], "
                 "a:has-text('Obtener Acceso')")
        try:
            with ctx.expect_page(timeout=20000) as pinfo:
                page.locator(boton).first.click(timeout=8000)
            activa = pinfo.value
            activa.wait_for_load_state("domcontentloaded")
            opciones.trace(f"[TGSS] tramite abierto en pestana nueva: {activa.url}")
            self._ss_login_idp(activa, opciones)
        except Exception as exc:
            opciones.trace(f"[TGSS] no se abrio pestana nueva ({exc}); intento en la misma")
            try:
                page.locator(boton).first.click(timeout=5000)
                page.wait_for_load_state("domcontentloaded")
                activa = page
            except Exception:
                pass
        return activa

    def _ss_generar_certificado(self, page, opciones, tipo):
        """En el formulario de SEDESS elige el tipo de certificado y pulsa
        Continuar. Devuelve True si actuo sobre el formulario."""
        try:
            if page.locator("form#seleccionCertificado, input[name='certificado']").count() == 0:
                return False
        except Exception:
            return False
        valor = SS_CERT_RADIO.get(tipo, "1")
        try:
            page.locator(f"input[name='certificado'][value='{valor}']").first.check(timeout=5000)
            opciones.trace(f"[{self.codigo_organismo}] tipo certificado seleccionado (valor {valor})")
        except Exception:
            try:
                page.locator("#certificado_1").check(timeout=3000)
            except Exception:
                pass
        for sel in ("button[name='SPM.ACC.CONTINUAR']", "#ENVIO_11",
                    "button:has-text('Continuar')", "button:has-text('Generar')"):
            try:
                el = page.locator(sel)
                if el.count() > 0:
                    el.first.click(timeout=6000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=opciones.timeout_ms)
                    except Exception:
                        pass
                    opciones.trace(f"[{self.codigo_organismo}] pulsado Continuar via '{sel}'")
                    return True
            except Exception:
                continue
        return False

    def _ss_error_mensaje(self, page):
        """Detecta mensajes de error visibles habituales (p.ej. limite de
        certificados por CIF). Best-effort."""
        try:
            txt = page.inner_text("body")
        except Exception:
            try:
                txt = page.content()
            except Exception:
                return None
        low = " ".join(txt.split()).lower()
        patrones = [
            r"(m[a\u00e1]ximo[^.]{0,60}certificad[^.]{0,80})",
            r"(supera[^.]{0,40}m[a\u00e1]ximo[^.]{0,80})",
            r"(l[i\u00ed]mite[^.]{0,40}certificad[^.]{0,80})",
            r"(no[^.]{0,20}posible[^.]{0,60}certificad[^.]{0,80})",
        ]
        for pat in patrones:
            m = re.search(pat, low)
            if m:
                return "Seguridad Social: " + m.group(1).strip()[:180]
        return None

    def _descargar_documento(self, page, opciones, tipo):
        """Busca el enlace del documento generado y lo guarda como PDF via la
        sesion autenticada (evita el problema de "descarga sin extension")."""
        selectores = [
            "a.pr_enlaceDocumento",
            "a[data-pc_tipo='documento']",
            "a[href*='ViewDoc']",
            "a[href*='.pdf']",
            "a:has-text('Certificado')",
        ]
        href = None
        origen = page
        try:
            paginas = [page] + [pp for pp in page.context.pages if pp is not page]
        except Exception:
            paginas = [page]
        for pg in paginas:
            for sel in selectores:
                try:
                    el = pg.locator(sel)
                    if el.count() > 0:
                        href = el.first.get_attribute("href")
                        if href:
                            origen = pg
                            break
                except Exception:
                    continue
            if href:
                break
        if not href:
            return None
        if href.startswith("/") or not href.lower().startswith("http"):
            from urllib.parse import urljoin
            href = urljoin(origen.url, href)
        destino = opciones.ruta_pdf_destino
        if not destino:
            carpeta = opciones.carpeta_descargas or os.getcwd()
            destino = os.path.join(carpeta, f"cert_{tipo}.pdf")
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        # 1) Peticion con cabeceras de navegacion (el portal exige que parezca
        #    una navegacion, no un XHR; si no, devuelve HTML en vez del PDF).
        body = self._pdf_bytes_request(origen, href, opciones)
        # 2) Si no es un PDF valido, abrir la URL en una pestana y capturar la
        #    respuesta/descarga reales (incluido visor con iframe/embed).
        if body is None:
            body = self._pdf_bytes_navegando(origen, href, destino, opciones)
        if body == "SAVED":
            opciones.trace(f"[{self.codigo_organismo}] documento guardado en {destino} (descarga)")
            return destino
        if body:
            with open(destino, "wb") as fh:
                fh.write(body)
            opciones.trace(f"[{self.codigo_organismo}] documento guardado en {destino} ({len(body)} bytes)")
            return destino
        opciones.trace(f"[{self.codigo_organismo}] no se obtuvo un PDF valido de {href}")
        return None

    @staticmethod
    def _es_pdf(b):
        return bool(b) and b[:4] == b"%PDF"

    def _pdf_bytes_request(self, origen, href, opciones):
        try:
            resp = origen.context.request.get(
                href, timeout=opciones.timeout_ms,
                headers={"Accept": "application/pdf,application/octet-stream,*/*;q=0.8",
                         "Referer": origen.url,
                         "Sec-Fetch-Mode": "navigate",
                         "Sec-Fetch-Dest": "document"})
            if resp.ok:
                b = resp.body()
                if self._es_pdf(b):
                    return b
                opciones.trace(f"[{self.codigo_organismo}] respuesta no-PDF (inicio {b[:12]!r})")
        except Exception as exc:
            opciones.trace(f"[{self.codigo_organismo}] request PDF error: {exc}")
        return None

    def _pdf_bytes_navegando(self, origen, href, destino, opciones):
        got = {"body": None, "saved": False}
        try:
            pg = origen.context.new_page()
        except Exception:
            return None

        def _cap(resp):
            try:
                ct = (resp.headers or {}).get("content-type", "").lower()
                if "pdf" in ct or "viewdoc" in resp.url.lower() or resp.url.split("?")[0].lower().endswith(".pdf"):
                    b = resp.body()
                    if self._es_pdf(b):
                        got["body"] = b
            except Exception:
                pass

        def _dl(dl):
            try:
                dl.save_as(destino)
                got["saved"] = True
            except Exception:
                pass

        pg.on("response", _cap)
        pg.on("download", _dl)
        try:
            try:
                pg.goto(href, wait_until="load", timeout=opciones.timeout_ms)
            except Exception:
                pass
            pg.wait_for_timeout(2000)
            if got["body"] is None and not got["saved"]:
                for sel in ("embed[src]", "iframe[src]", "object[data]"):
                    try:
                        el = pg.locator(sel)
                        if el.count() > 0:
                            src = el.first.get_attribute("src") or el.first.get_attribute("data")
                            if src:
                                from urllib.parse import urljoin
                                b = self._pdf_bytes_request(pg, urljoin(pg.url, src), opciones)
                                if b:
                                    got["body"] = b
                                    break
                    except Exception:
                        continue
        finally:
            try:
                pg.close()
            except Exception:
                pass
        return "SAVED" if got["saved"] else got["body"]

    def _resultado_corriente(self, page):
        """Intenta deducir POSITIVO/NEGATIVO del texto de la pagina (best-effort)."""
        try:
            txt = (page.content() or "").lower()
        except Exception:
            return None
        if "no se encuentra al corriente" in txt or "no esta al corriente" in txt or "informe de deuda" in txt:
            return "NEGATIVO"
        if "se encuentra al corriente" in txt or "esta al corriente" in txt or "al corriente" in txt:
            return "POSITIVO"
        return None

    def _origenes(self):
        base = self.url_sede.rstrip("/")
        extra = []
        if self.codigo_organismo == "TGSS":
            extra = ["https://sede.seg-social.gob.es", "https://sp.seg-social.es",
                     "https://sede.seg-social.es", "https://w6.seg-social.es",
                     "https://w2.seg-social.es",
                     "https://idp.seg-social.es", "https://idp.seg-social.gob.es",
                     "https://portal.seg-social.gob.es"]
        elif self.codigo_organismo == "AEAT":
            extra = ["https://sede.agenciatributaria.gob.es",
                     "https://www1.agenciatributaria.gob.es",
                     "https://www2.agenciatributaria.gob.es",
                     "https://www3.agenciatributaria.gob.es"]
        clave = ["https://se-pasarela.clave.gob.es", "https://pasarela.clave.gob.es",
                 "https://afirma.clave.gob.es", "https://componentes.clave.gob.es"]
        origenes = []
        for o in [base] + extra + clave:
            if o and o not in origenes:
                origenes.append(o)
        return origenes

    def _diag(self, page, opciones, tipo):
        if not opciones.modo_diagnostico:
            return
        carpeta = opciones.carpeta_diagnostico or os.getcwd()
        os.makedirs(carpeta, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            page.screenshot(path=os.path.join(carpeta, f"cert_{self.codigo_organismo}_{tipo}_{ts}.png"), full_page=True)
            with open(os.path.join(carpeta, f"cert_{self.codigo_organismo}_{tipo}_{ts}.html"), "w", encoding="utf-8") as fh:
                fh.write(page.content())
            opciones.trace(f"[{self.codigo_organismo}] diagnostico guardado en {carpeta}")
        except Exception:
            pass


# Radio "name=certificado" del formulario de SEDESS: 1=generico, 3=subvenciones,
# 5=articulo 42, 2=licitacion, 4=sin deuda a fecha, 6=informe deuda, 7=detalle deuda.
SS_CERT_RADIO = {
    "TGSS_CORRIENTE": "1",       # certificado generico
    "TGSS_SUBVENCIONES": "3",    # certificado subvenciones
    "TGSS_LICITACION": "2",      # licitacion contratos sector publico
    "TGSS_ART42": "5",           # articulo 42 (subcontratacion)  [puede requerir fecha]
    "TGSS_SIN_DEUDA_FECHA": "4", # sin deuda a una fecha           [puede requerir fecha]
    "TGSS_INFORME_DEUDA": "6",   # informe de deuda total
    "TGSS_DETALLE_DEUDA": "7",   # informe detalle de deuda
}

# Pagina "Informes y Certificados" (Ciudadanos) de SEDESS: contiene el acordeon
# "Certificados de estar al corriente..." con el boton "Obtener Acceso".
# >>> AJUSTAR si la URL real difiere (mirar la barra de direcciones).
SS_URL_INFORMES = ("https://sede.seg-social.gob.es/wps/portal/sede/sede/Ciudadanos/"
                   "informes+y+certificados/n201736")

# Entrada directa al tramite (redirector). NO se navega directamente porque da
# ERR_TOO_MANY_REDIRECTS: se llega pulsando "Obtener Acceso" desde SS_URL_INFORMES.
SS_URL_CORRIENTE = (
    "https://sede.seg-social.gob.es/wps/portal/sede/Seguridad/PortalRedirectorN1A"
    "?idApp=2265&idContenido=eb51e9c3-1a2a-4027-8a96-f68107f3bde7"
    "&idPagina=com.ss.sede.Ciudadanos&N1&A"
)

# Registrar proveedores para AEAT y TGSS.
registrar_proveedor(SedePlaywrightProvider("AEAT",
    {"AEAT_CORRIENTE", "AEAT_CENSAL", "AEAT_IAE"}, TIPOS["AEAT_CORRIENTE"][2]))
# Todos estos tipos comparten el mismo tramite "Estar al corriente" (misma URL
# de entrada); el radio "name=certificado" (SS_CERT_RADIO) elige cual descargar.
_TGSS_CORRIENTE_TIPOS = {
    "TGSS_CORRIENTE", "TGSS_SUBVENCIONES", "TGSS_LICITACION", "TGSS_ART42",
    "TGSS_SIN_DEUDA_FECHA", "TGSS_INFORME_DEUDA", "TGSS_DETALLE_DEUDA",
}
_tgss_urls = {t: SS_URL_INFORMES for t in _TGSS_CORRIENTE_TIPOS}
registrar_proveedor(SedePlaywrightProvider("TGSS",
    _TGSS_CORRIENTE_TIPOS | {"TGSS_COTIZACION"}, TIPOS["TGSS_CORRIENTE"][2],
    urls=_tgss_urls))


# ── carpetas de salida (patron por cliente, como los PDF) ─────────────────────
CARPETA_CERT_DEFECTO = r"\\GestinemMain\Doc_Compartidos\Gest2A3Eco\Certificados"


def _carpeta_base_certificados() -> str:
    # Prioridad: variable de entorno > config (certificados_output_dir) > por defecto.
    env = os.environ.get("GEST2A3ECO_CERT_DIR")
    if env:
        return env
    try:
        from utils.utilidades import load_app_config
        v = (load_app_config().get("certificados_output_dir") or "").strip()
        if v:
            return v
    except Exception:
        pass
    return CARPETA_CERT_DEFECTO


def _safe_nombre(v) -> str:
    s = (v or "").strip()
    for ch in '<>:"/\\|?*':
        s = s.replace(ch, " ")
    return " ".join(s.split())


def carpeta_certificados_cliente(gestor, codigo_empresa) -> str:
    base = _carpeta_base_certificados()
    emp = gestor.get_empresa(codigo_empresa) or {}
    nombre = _safe_nombre(emp.get("nombre")) or _safe_nombre(codigo_empresa) or "Sin_cliente"
    carpeta = os.path.join(base, nombre)
    try:
        os.makedirs(carpeta, exist_ok=True)
    except Exception:
        pass
    return carpeta


def ruta_pdf_certificado(carpeta, tipo, cif) -> str:
    fecha = datetime.now().strftime("%Y%m%d")
    partes = [p for p in [tipo, _safe_nombre(cif), fecha] if p]
    return os.path.join(carpeta, "_".join(partes) + ".pdf")


# ── validacion de requisitos por organismo ───────────────────────────────────
def _datos_ss(gestor, codigo_empresa) -> dict:
    emp = gestor.get_empresa(codigo_empresa) or {}
    naf = (emp.get("naf") or "").strip()
    try:
        cccs = [c.get("ccc") for c in gestor.listar_ccc(codigo_empresa, solo_activos=True) if c.get("ccc")]
    except Exception:
        cccs = []
    return {"naf": naf or None, "cccs": cccs}


def requisitos_ok(gestor, codigo_empresa, tipo):
    """Valida los requisitos previos por organismo. Devuelve (ok, mensaje)."""
    organismo = TIPOS.get(tipo, (None,))[0]
    if organismo == "TGSS":
        datos = _datos_ss(gestor, codigo_empresa)
        if not datos.get("naf") and not datos.get("cccs"):
            return False, ("El cliente no tiene NAF ni CCC. La Seguridad Social no permite "
                           "este tramite sin al menos uno. Anadelo en la ficha del cliente "
                           "(pestana 'Seguridad Social').")
    return True, ""


# ── orquestador ───────────────────────────────────────────────────────────────
def solicitar_certificado(gestor, codigo_empresa: str, tipo: str,
                          opciones: OpcionesSync | None = None) -> ResultadoCertificado:
    """Resuelve el certificado del cliente, ejecuta el proveedor y guarda la
    solicitud en cert_solicitudes. No lanza excepciones."""
    opciones = opciones or OpcionesSync()
    organismo, _descr, _url = TIPOS.get(tipo, (None, tipo, None))
    ahora = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    ok = False
    estado = "ERROR"
    resultado = None
    pdf = None
    referencia = None
    mensaje = ""
    error = None
    try:
        ok_req, msg_req = requisitos_ok(gestor, codigo_empresa, tipo)
        if not ok_req:
            raise Exception(msg_req)
        material = CertStore(gestor).material_para_empresa(codigo_empresa)
        if organismo == "TGSS":
            opciones.datos_ss = _datos_ss(gestor, codigo_empresa)
        # Carpeta de salida por cliente (patron de los PDF) y ruta destino del PDF.
        _emp = gestor.get_empresa(codigo_empresa) or {}
        opciones.carpeta_descargas = carpeta_certificados_cliente(gestor, codigo_empresa)
        opciones.ruta_pdf_destino = ruta_pdf_certificado(
            opciones.carpeta_descargas, tipo, _emp.get("cif"))
        prov = obtener_proveedor(tipo)
        if prov is None:
            raise Exception(f"No hay proveedor para el certificado '{tipo}'.")
        res = prov.obtener(material, tipo, opciones)
        ok = res.ok
        estado = res.estado or ("OBTENIDO" if res.ok else "ERROR")
        resultado = res.resultado
        pdf = res.pdf_path
        referencia = res.referencia
        mensaje = res.mensaje
        error = res.error_detalle
    except Exception as exc:
        estado = "ERROR"
        mensaje = str(exc)
        error = traceback.format_exc()

    sid = None
    try:
        sid = gestor.upsert_cert_solicitud({
            "codigo_empresa": codigo_empresa,
            "tipo": tipo,
            "organismo": organismo,
            "estado": estado,
            "resultado": resultado,
            "fecha_solicitud": ahora,
            "fecha_obtencion": ahora if estado == "OBTENIDO" else None,
            "pdf_path": pdf,
            "referencia": referencia,
            "mensaje": (mensaje or "")[:2000],
        })
    except Exception:
        pass

    return ResultadoCertificado(ok=ok, tipo=tipo, estado=estado, resultado=resultado,
                                pdf_path=pdf, referencia=referencia, mensaje=mensaje,
                                error_detalle=error, solicitud_id=sid)
