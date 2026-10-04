"""Ingesta BDNS, clasificacion territorial, resumen y avisos de ayudas."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import time
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from backend.api import messaging_firebase
from backend.api.feature_flags import is_subsidies_enabled
from backend.api.messaging_models import (
    MessagingAppDevice,
    MessagingClient,
    MessagingOrganization,
)
from backend.api.subvenciones_models import (
    SubvencionConvocatoria,
    SubvencionConfiguracion,
    SubvencionEntrega,
    SubvencionEjecucion,
    SubvencionPreferencia,
    SubvencionSuscripcion,
)

LOG = logging.getLogger(__name__)
BDNS_API = "https://www.infosubvenciones.es/bdnstrans/api"
BDNS_FICHA = "https://www.infosubvenciones.es/bdnstrans/GE/es/convocatorias"
_LOCK_ID = 73190618
_NUTS = re.compile(r"^\s*(ES\d{0,3})\b")
_PROVINCIALES = ("DIPUTACI", "CABILDO", "CONSELL INSULAR", "CONSELL DE ")

CCAA = {
    "ES11": "Galicia", "ES12": "Principado de Asturias", "ES13": "Cantabria",
    "ES21": "Pais Vasco", "ES22": "Comunidad Foral de Navarra", "ES23": "La Rioja",
    "ES24": "Aragon", "ES30": "Comunidad de Madrid", "ES41": "Castilla y Leon",
    "ES42": "Castilla-La Mancha", "ES43": "Extremadura", "ES51": "Cataluna",
    "ES52": "Comunitat Valenciana", "ES53": "Illes Balears", "ES61": "Andalucia",
    "ES62": "Region de Murcia", "ES63": "Ceuta", "ES64": "Melilla", "ES70": "Canarias",
}

_NOMBRE_A_CCAA = {
    "GALICIA": "ES11", "XUNTA": "ES11", "ASTURIAS": "ES12",
    "PRINCIPADO DE ASTURIAS": "ES12", "CANTABRIA": "ES13",
    "PAIS VASCO": "ES21", "EUSKADI": "ES21", "NAVARRA": "ES22",
    "COMUNIDAD FORAL DE NAVARRA": "ES22", "LA RIOJA": "ES23",
    "RIOJA": "ES23", "ARAGON": "ES24", "MADRID": "ES30",
    "COMUNIDAD DE MADRID": "ES30", "CASTILLA Y LEON": "ES41",
    "CASTILLA-LA MANCHA": "ES42", "CASTILLA LA MANCHA": "ES42",
    "EXTREMADURA": "ES43", "CATALUNA": "ES51", "CATALUNYA": "ES51",
    "COMUNITAT VALENCIANA": "ES52", "COMUNIDAD VALENCIANA": "ES52",
    "ILLES BALEARS": "ES53", "BALEARES": "ES53", "ISLAS BALEARES": "ES53",
    "ANDALUCIA": "ES61", "MURCIA": "ES62", "REGION DE MURCIA": "ES62",
    "CEUTA": "ES63", "MELILLA": "ES64", "CANARIAS": "ES70",
}

_CP_TERRITORIO = {
    "01": ("ES21", "ES211", "Araba/Alava"), "02": ("ES42", "ES421", "Albacete"),
    "03": ("ES52", "ES521", "Alicante"), "04": ("ES61", "ES611", "Almeria"),
    "05": ("ES41", "ES411", "Avila"), "06": ("ES43", "ES431", "Badajoz"),
    "07": ("ES53", "ES530", "Illes Balears"), "08": ("ES51", "ES511", "Barcelona"),
    "09": ("ES41", "ES412", "Burgos"), "10": ("ES43", "ES432", "Caceres"),
    "11": ("ES61", "ES612", "Cadiz"), "12": ("ES52", "ES522", "Castellon"),
    "13": ("ES42", "ES422", "Ciudad Real"), "14": ("ES61", "ES613", "Cordoba"),
    "15": ("ES11", "ES111", "A Coruna"), "16": ("ES42", "ES423", "Cuenca"),
    "17": ("ES51", "ES512", "Girona"), "18": ("ES61", "ES614", "Granada"),
    "19": ("ES42", "ES424", "Guadalajara"), "20": ("ES21", "ES212", "Gipuzkoa"),
    "21": ("ES61", "ES615", "Huelva"), "22": ("ES24", "ES241", "Huesca"),
    "23": ("ES61", "ES616", "Jaen"), "24": ("ES41", "ES413", "Leon"),
    "25": ("ES51", "ES513", "Lleida"), "26": ("ES23", "ES230", "La Rioja"),
    "27": ("ES11", "ES112", "Lugo"), "28": ("ES30", "ES300", "Madrid"),
    "29": ("ES61", "ES617", "Malaga"), "30": ("ES62", "ES620", "Murcia"),
    "31": ("ES22", "ES220", "Navarra"), "32": ("ES11", "ES113", "Ourense"),
    "33": ("ES12", "ES120", "Asturias"), "34": ("ES41", "ES414", "Palencia"),
    "35": ("ES70", "ES704,ES705,ES708", "Las Palmas"), "36": ("ES11", "ES114", "Pontevedra"),
    "37": ("ES41", "ES415", "Salamanca"), "38": ("ES70", "ES703,ES706,ES707,ES709", "Santa Cruz de Tenerife"),
    "39": ("ES13", "ES130", "Cantabria"), "40": ("ES41", "ES416", "Segovia"),
    "41": ("ES61", "ES618", "Sevilla"), "42": ("ES41", "ES417", "Soria"),
    "43": ("ES51", "ES514", "Tarragona"), "44": ("ES24", "ES242", "Teruel"),
    "45": ("ES42", "ES425", "Toledo"), "46": ("ES52", "ES523", "Valencia"),
    "47": ("ES41", "ES418", "Valladolid"), "48": ("ES21", "ES213", "Bizkaia"),
    "49": ("ES41", "ES419", "Zamora"), "50": ("ES24", "ES243", "Zaragoza"),
    "51": ("ES63", "ES630", "Ceuta"), "52": ("ES64", "ES640", "Melilla"),
}

PROVINCIAS = {
    province_code: province_name
    for _ccaa_code, province_code, province_name in _CP_TERRITORIO.values()
    if province_code
}


def _sin_tildes(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", value or "")
        if unicodedata.category(c) != "Mn"
    )


def slug(value: str | None) -> str:
    if not value:
        return ""
    normalized = _sin_tildes(value).lower()
    normalized = re.sub(
        r"^(ayuntamiento|ajuntament|concello|udala|ayto\.?)\s+(de\s+|d')?",
        "", normalized,
    )
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def territorio_organizacion(org: MessagingOrganization) -> dict:
    prefix = re.sub(r"\D", "", str(org.postal_code or ""))[:2]
    ccaa, provincia, provincia_nombre = _CP_TERRITORIO.get(prefix, ("", "", org.province or ""))
    return {
        "ccaa": ccaa,
        "ccaa_nombre": CCAA.get(ccaa, ""),
        "provincia": provincia,
        "provincia_nombre": provincia_nombre,
        "municipio": str(org.city or "").strip(),
        "municipio_slug": slug(org.city),
    }


def _nivel(value: str) -> str:
    normalized = _sin_tildes(value).upper()
    if normalized.startswith(("ESTAT", "ESTADO")) or normalized == "AGE":
        return "ESTATAL"
    if normalized.startswith("AUTONOM"):
        return "AUTONOMICA"
    if normalized.startswith("LOCAL"):
        return "LOCAL"
    return "OTROS"


def clasificar(detalle: dict) -> dict:
    organo = detalle.get("organo") or {}
    ambito = _nivel(str(organo.get("nivel1") or ""))
    ccaa: set[str] = set()
    provincias: set[str] = set()
    nacional_region = False
    for region in detalle.get("regiones") or []:
        description = region.get("descripcion", "") if isinstance(region, dict) else str(region)
        match = _NUTS.match(description)
        if not match:
            continue
        code = match.group(1)
        if len(code) <= 3:
            nacional_region = True
        elif len(code) == 4:
            ccaa.add(code)
        else:
            provincias.add(code)
            ccaa.add(code[:4])
    if ambito == "AUTONOMICA" and not ccaa:
        needle = _sin_tildes(str(organo.get("nivel2") or "")).upper().strip()
        exact = _NOMBRE_A_CCAA.get(needle)
        if exact:
            ccaa.add(exact)
        else:
            for code, name in CCAA.items():
                if _sin_tildes(name).upper() in needle:
                    ccaa.add(code)
                    break
    level3 = _sin_tildes(str(organo.get("nivel3") or "")).upper()
    es_provincial = ambito == "LOCAL" and any(x in level3 for x in _PROVINCIALES)
    municipio_nombre = "" if es_provincial or ambito != "LOCAL" else str(organo.get("nivel2") or "").strip()
    return {
        "ambito": ambito,
        "alcance_nacional": nacional_region or (ambito == "ESTATAL" and not ccaa),
        "ccaa_json": sorted(ccaa),
        "provincias_json": sorted(provincias),
        "es_provincial": es_provincial,
        "municipio_nombre": municipio_nombre,
        "municipio_slug": slug(municipio_nombre),
    }


def _date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value)[:10]
    for pattern in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            pass
    return None


def _descriptions(items) -> list[str]:
    return [
        str(item.get("descripcion") or "").strip()
        for item in items or [] if isinstance(item, dict) and item.get("descripcion")
    ]


def _links(detalle: dict) -> list[dict]:
    code = str(detalle.get("codigoBDNS") or detalle.get("numeroConvocatoria") or "")
    result = [{"tipo": "ficha", "titulo": "Ficha oficial en la BDNS", "url": f"{BDNS_FICHA}/{code}"}]
    api_base = os.getenv("SUBSIDIES_BDNS_BASE_URL", BDNS_API).rstrip("/")
    for announcement in detalle.get("anuncios") or []:
        if not isinstance(announcement, dict):
            continue
        url = announcement.get("url") or announcement.get("urlBoletin") or announcement.get("enlace")
        if url:
            result.append({
                "tipo": "boletin",
                "titulo": str(announcement.get("desDiarioOficial") or "Boletin oficial"),
                "url": str(url),
            })
    for document in detalle.get("documentos") or []:
        if isinstance(document, dict) and document.get("id"):
            result.append({
                "tipo": "documento",
                "titulo": str(document.get("descripcion") or "Documento oficial"),
                "url": f"{api_base}/convocatorias/documentos?idDocumento={document['id']}",
            })
    for key, kind, title in (
        ("urlBasesReguladoras", "bases", "Bases reguladoras"),
        ("sedeElectronica", "sede", "Sede electronica"),
    ):
        if detalle.get(key):
            result.append({"tipo": kind, "titulo": title, "url": str(detalle[key])})
    return result


def normalizar(detalle: dict) -> dict:
    organo = detalle.get("organo") or {}
    budget = detalle.get("presupuestoTotal")
    try:
        budget = float(str(budget).replace(",", ".")) if budget not in (None, "") else None
    except (TypeError, ValueError):
        budget = None
    raw = {k: v for k, v in detalle.items() if k != "advertencia"}
    encoded = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str).encode()
    return {
        "codigo_bdns": str(detalle.get("codigoBDNS") or detalle.get("numeroConvocatoria") or "").strip(),
        "titulo": str(detalle.get("descripcion") or "").strip(),
        "organo_nivel1": str(organo.get("nivel1") or ""),
        "organo_nivel2": str(organo.get("nivel2") or ""),
        "organo_nivel3": str(organo.get("nivel3") or ""),
        "fecha_recepcion": _date(detalle.get("fechaRecepcion")),
        "fecha_inicio": _date(detalle.get("fechaInicioSolicitud")),
        "fecha_fin": _date(detalle.get("fechaFinSolicitud")),
        "texto_inicio": str(detalle.get("textInicio") or ""),
        "texto_fin": str(detalle.get("textFin") or ""),
        "abierto": detalle.get("abierto") if isinstance(detalle.get("abierto"), bool) else None,
        "presupuesto": budget,
        "tipo_convocatoria": str(detalle.get("tipoConvocatoria") or ""),
        "finalidad": str(detalle.get("descripcionFinalidad") or ""),
        "beneficiarios_json": _descriptions(detalle.get("tiposBeneficiarios")),
        "sectores_json": _descriptions(detalle.get("sectores")),
        "instrumentos_json": _descriptions(detalle.get("instrumentos")),
        "mrr": bool(detalle.get("mrr")),
        "enlaces_json": _links(detalle),
        "hash_fuente": hashlib.sha256(encoded).hexdigest(),
        "raw_json": raw,
        **clasificar(detalle),
    }


def es_vigente(call: SubvencionConvocatoria, today: date | None = None) -> bool:
    today = today or date.today()
    if not call.visible or call.abierto is False:
        return False
    return call.fecha_fin is None or call.fecha_fin >= today


def _matches_scope(call: SubvencionConvocatoria, level: str, code: str) -> bool:
    if level == "NACIONAL":
        return bool(call.alcance_nacional)
    if level == "AUTONOMICA":
        return call.ambito != "LOCAL" and code in (call.ccaa_json or [])
    if level == "PROVINCIAL":
        if call.ambito != "LOCAL" or not call.es_provincial:
            return False
        provinces = call.provincias_json or []
        selected = [item for item in code.split(",") if item]
        return bool(set(selected) & set(provinces)) or (
            not provinces and bool(selected)
            and selected[0][:4] in (call.ccaa_json or [])
        )
    if level == "MUNICIPAL":
        ccaa_code, separator, municipality = code.partition(":")
        municipality = municipality if separator else code
        if not municipality:
            return False
        ccaa_matches = not separator or not call.ccaa_json or ccaa_code in call.ccaa_json
        return (
            call.ambito == "LOCAL" and not call.es_provincial
            and call.municipio_slug == municipality and ccaa_matches
        )
    return False


def coincide_cliente(
    call: SubvencionConvocatoria,
    org: MessagingOrganization,
    preference: SubvencionPreferencia | None,
    subscriptions: list[SubvencionSuscripcion],
) -> bool:
    include_national = True if preference is None else preference.incluir_nacionales
    use_home = True if preference is None else preference.usar_territorio_empresa
    if include_national and call.alcance_nacional:
        return True
    if use_home:
        territory = territorio_organizacion(org)
        if (
            _matches_scope(call, "AUTONOMICA", territory["ccaa"])
            or _matches_scope(call, "PROVINCIAL", territory["provincia"])
            or _matches_scope(
                call, "MUNICIPAL",
                f"{territory['ccaa']}:{territory['municipio_slug']}",
            )
        ):
            return True
    return any(_matches_scope(call, item.nivel, item.codigo) for item in subscriptions)


class BdnsClient:
    def __init__(self, client: httpx.Client | None = None):
        timeout = float(os.getenv("SUBSIDIES_BDNS_TIMEOUT", "30"))
        self.client = client or httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"Accept": "application/json", "User-Agent": "Gestinem-Ayudas/1.0 (+https://gestinem.es)"},
        )
        self.pause = float(os.getenv("SUBSIDIES_BDNS_PAUSE", "0.35"))
        self.base_url = os.getenv("SUBSIDIES_BDNS_BASE_URL", BDNS_API).rstrip("/")

    def _get(self, path: str, params: dict, *, binary: bool = False):
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                response = self.client.get(f"{self.base_url}{path}", params=params)
                response.raise_for_status()
                if self.pause:
                    time.sleep(self.pause)
                return response.content if binary else response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"BDNS no responde en {path}: {last_error}")

    def listar_desde(self, since: date, page_size: int = 100) -> list[dict]:
        result: list[dict] = []
        max_pages = int(os.getenv("SUBSIDIES_BDNS_MAX_PAGES", "100"))
        for page in range(max_pages):
            data = self._get("/convocatorias/busqueda", {
                "vpd": "GE", "page": page, "pageSize": page_size,
                "order": "fechaRecepcion", "direccion": "desc",
            })
            rows = data.get("content") or []
            for row in rows:
                received = _date(row.get("fechaRecepcion"))
                if received and received < since:
                    return result
                result.append(row)
            if not rows or data.get("last"):
                break
        return result

    def detalle(self, code: str) -> dict:
        return self._get("/convocatorias", {"numConv": code, "vpd": "GE"})

    def texto_documento(self, document_id: int | str) -> str:
        try:
            from pypdf import PdfReader
            content = self._get(
                "/convocatorias/documentos", {"idDocumento": document_id}, binary=True,
            )
            reader = PdfReader(io.BytesIO(content))
            maximum = int(os.getenv("SUBSIDIES_AI_MAX_CHARS", "40000"))
            parts: list[str] = []
            for page in reader.pages:
                parts.append(page.extract_text() or "")
                if sum(len(item) for item in parts) >= maximum:
                    break
            return "\n".join(parts)[:maximum]
        except Exception as exc:  # PDFs escaneados o defectuosos no bloquean la ingesta.
            LOG.warning("No se pudo extraer el documento BDNS %s: %s", document_id, exc)
            return ""


class Resumidor:
    etiquetas = {
        "empleo", "autonomos", "digitalizacion", "innovacion", "industria", "comercio",
        "hosteleria", "turismo", "agricultura", "pesca", "energia", "vivienda",
        "formacion", "internacionalizacion", "emprendimiento", "cultura", "social",
        "medio_ambiente", "transporte", "otros",
    }

    @property
    def disponible(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())

    def resumir(self, call: SubvencionConvocatoria, document_text: str) -> dict:
        prompt = {
            "titulo": call.titulo,
            "organo": " / ".join(x for x in (call.organo_nivel2, call.organo_nivel3) if x),
            "finalidad": call.finalidad,
            "beneficiarios_oficiales": call.beneficiarios_json,
            "presupuesto_total": call.presupuesto,
            "fecha_inicio": str(call.fecha_inicio or call.texto_inicio),
            "fecha_fin": str(call.fecha_fin or call.texto_fin),
            "texto_convocatoria": document_text,
        }
        system = (
            "Redacta una ficha orientativa de una ayuda publica espanola usando solo los datos "
            "facilitados. No afirmes que el lector cumple requisitos. Devuelve exclusivamente JSON "
            "con resumen, beneficiarios, que_financia, cuantia, requisitos (lista), plazo y etiquetas "
            f"(lista de: {', '.join(sorted(self.etiquetas))})."
        )
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": os.getenv("SUBSIDIES_AI_MODEL", "claude-haiku-4-5-20251001"),
                "max_tokens": 1200,
                "system": system,
                "messages": [{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
            },
            timeout=60,
        )
        response.raise_for_status()
        text_value = "".join(
            str(item.get("text") or "") for item in response.json().get("content") or []
            if isinstance(item, dict)
        )
        match = re.search(r"\{.*\}", text_value, re.S)
        if not match:
            raise ValueError("La respuesta IA no contiene JSON")
        raw = json.loads(match.group(0))
        summary = str(raw.get("resumen") or "").strip()[:900]
        if not summary:
            raise ValueError("Resumen IA vacio")
        return {
            "resumen": summary,
            "beneficiarios": str(raw.get("beneficiarios") or "").strip()[:600],
            "que_financia": str(raw.get("que_financia") or "").strip()[:600],
            "cuantia": str(raw.get("cuantia") or "").strip()[:300],
            "requisitos": [str(x).strip()[:300] for x in (raw.get("requisitos") or [])][:5],
            "plazo": str(raw.get("plazo") or "").strip()[:300],
            "etiquetas": [x for x in (raw.get("etiquetas") or []) if x in self.etiquetas][:3] or ["otros"],
        }


def _apply(call: SubvencionConvocatoria, values: dict) -> None:
    for key, value in values.items():
        setattr(call, key, value)


class SubvencionesService:
    def __init__(
        self, db: Session, *, bdns: BdnsClient | None = None,
        summarizer: Resumidor | None = None,
    ):
        self.db = db
        self.bdns = bdns or BdnsClient()
        self.summarizer = summarizer or Resumidor()

    def _config(self) -> SubvencionConfiguracion:
        item = self.db.get(SubvencionConfiguracion, "global")
        if item is None:
            item = SubvencionConfiguracion(id="global")
            self.db.add(item)
            self.db.commit()
        return item

    def _lock(self) -> bool:
        if self.db.bind is None or self.db.bind.dialect.name != "postgresql":
            return True
        return bool(self.db.scalar(text(f"SELECT pg_try_advisory_lock({_LOCK_ID})")))

    def _unlock(self) -> None:
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            self.db.execute(text(f"SELECT pg_advisory_unlock({_LOCK_ID})"))

    def _since(self, today: date) -> date:
        last = self.db.scalar(select(SubvencionEjecucion).where(
            SubvencionEjecucion.estado == "ok",
        ).order_by(SubvencionEjecucion.fin.desc()).limit(1))
        initial_days = max(3, int(os.getenv("SUBSIDIES_INITIAL_DAYS", "14")))
        if not last or not last.fin:
            return today - timedelta(days=initial_days)
        previous = last.fin.date() if isinstance(last.fin, datetime) else today
        return max(today - timedelta(days=30), previous - timedelta(days=3))

    def _interested(self, call: SubvencionConvocatoria) -> bool:
        clients = self.db.scalars(select(MessagingClient).where(MessagingClient.active.is_(True))).all()
        preferences = {x.client_id: x for x in self.db.scalars(select(SubvencionPreferencia)).all()}
        subscriptions: dict[str, list[SubvencionSuscripcion]] = defaultdict(list)
        for item in self.db.scalars(select(SubvencionSuscripcion)).all():
            subscriptions[item.client_id].append(item)
        for client in clients:
            org = self.db.get(MessagingOrganization, client.organization_id)
            if org and org.active and is_subsidies_enabled(org) and coincide_cliente(
                call, org, preferences.get(client.id), subscriptions.get(client.id, []),
            ):
                return True
        return False

    def ingerir(self, run: SubvencionEjecucion, today: date) -> list[SubvencionConvocatoria]:
        page_size = max(10, min(500, int(os.getenv("SUBSIDIES_BDNS_PAGE_SIZE", "100"))))
        rows = self.bdns.listar_desde(self._since(today), page_size=page_size)
        run.leidas = len(rows)
        changed: list[SubvencionConvocatoria] = []
        for row in rows:
            code = str(row.get("numeroConvocatoria") or "").strip()
            if not code:
                continue
            try:
                detail = self.bdns.detalle(code)
                values = normalizar(detail)
                if not values["codigo_bdns"]:
                    continue
                call = self.db.scalar(select(SubvencionConvocatoria).where(
                    SubvencionConvocatoria.codigo_bdns == values["codigo_bdns"],
                ))
                if call and call.hash_fuente == values["hash_fuente"]:
                    continue
                if call is None:
                    call = SubvencionConvocatoria(codigo_bdns=code, titulo=values["titulo"], ambito=values["ambito"])
                    self.db.add(call)
                    run.nuevas += 1
                else:
                    run.actualizadas += 1
                _apply(call, values)
                call.resumen_estado = "pendiente"
                call.hash_resumen = ""
                self.db.commit()
                changed.append(call)
            except Exception as exc:
                LOG.exception("No se pudo importar la convocatoria %s", code)
                run.detalle = (run.detalle + f"\n{code}: {exc}")[-8000:]
                self.db.rollback()
        return changed

    def resumir(self, run: SubvencionEjecucion, limit: int = 100) -> None:
        pending = self.db.scalars(select(SubvencionConvocatoria).where(
            SubvencionConvocatoria.resumen_estado.in_(("pendiente", "error", "sin_ia")),
            SubvencionConvocatoria.visible.is_(True),
        ).order_by(SubvencionConvocatoria.fecha_recepcion.desc()).limit(limit)).all()
        if not self._config().resumenes_ia_activos or not self.summarizer.disponible:
            for call in pending:
                call.resumen_estado = "sin_ia"
            self.db.commit()
            return
        for call in pending:
            if not self._interested(call):
                continue
            try:
                documents = [
                    item for item in (call.raw_json or {}).get("documentos") or []
                    if isinstance(item, dict) and item.get("id")
                ]
                main = next(
                    (item for item in documents if "convocatoria" in str(item.get("descripcion") or "").lower()),
                    documents[0] if documents else None,
                )
                document_text = self.bdns.texto_documento(main["id"]) if main else ""
                call.resumen_json = self.summarizer.resumir(call, document_text)
                call.resumen_estado = "ok"
                call.resumen_modelo = os.getenv("SUBSIDIES_AI_MODEL", "claude-haiku-4-5-20251001")
                call.hash_resumen = call.hash_fuente
                run.resumidas += 1
            except Exception as exc:
                call.resumen_estado = "error"
                run.detalle = (run.detalle + f"\nResumen {call.codigo_bdns}: {exc}")[-8000:]
                LOG.exception("No se pudo resumir %s", call.codigo_bdns)
            self.db.commit()

    def notificar(self, run: SubvencionEjecucion, today: date) -> None:
        if not self._config().avisos_activos:
            return
        clients = self.db.scalars(select(MessagingClient).where(MessagingClient.active.is_(True))).all()
        preferences = {x.client_id: x for x in self.db.scalars(select(SubvencionPreferencia)).all()}
        subscriptions: dict[str, list[SubvencionSuscripcion]] = defaultdict(list)
        for item in self.db.scalars(select(SubvencionSuscripcion)).all():
            subscriptions[item.client_id].append(item)
        recent = self.db.scalars(select(SubvencionConvocatoria).where(
            SubvencionConvocatoria.visible.is_(True),
            SubvencionConvocatoria.creada_at >= datetime.now(timezone.utc) - timedelta(days=7),
            or_(SubvencionConvocatoria.fecha_fin.is_(None), SubvencionConvocatoria.fecha_fin >= today),
            SubvencionConvocatoria.abierto.is_not(False),
        ).order_by(SubvencionConvocatoria.fecha_recepcion.desc())).all()
        for client in clients:
            preference = preferences.get(client.id)
            if not preference or not preference.notificaciones_activas:
                continue
            org = self.db.get(MessagingOrganization, client.organization_id)
            if not org or not org.active or not is_subsidies_enabled(org):
                continue
            matched = [
                call for call in recent
                if coincide_cliente(call, org, preference, subscriptions.get(client.id, []))
                and self.db.scalar(select(func.count()).select_from(SubvencionEntrega).where(
                    SubvencionEntrega.client_id == client.id,
                    SubvencionEntrega.convocatoria_id == call.id,
                    SubvencionEntrega.estado == "enviado",
                )) == 0
            ]
            if not matched:
                continue
            devices = self.db.scalars(select(MessagingAppDevice).where(
                MessagingAppDevice.user_type == "client",
                MessagingAppDevice.user_id == client.id,
                MessagingAppDevice.active.is_(True),
            )).all()
            title = "1 ayuda nueva para ti" if len(matched) == 1 else f"{len(matched)} ayudas nuevas para ti"
            body = matched[0].titulo[:110]
            if len(matched) > 1:
                body = f"{body} y {len(matched) - 1} mas"
            successful = 0
            errors: list[str] = []
            for device in devices:
                result = messaging_firebase.send_fcm(device.push_token, {
                    "title": title, "body": body, "target_type": "subvencion",
                    "target_id": matched[0].codigo_bdns, "subvencion_id": matched[0].codigo_bdns,
                    "type": "subvenciones.available",
                }, platform=device.platform)
                if result.success:
                    successful += 1
                elif result.permanent_failure:
                    device.active = False
                else:
                    errors.append("Error transitorio FCM")
            for call in matched:
                delivery = self.db.scalar(select(SubvencionEntrega).where(
                    SubvencionEntrega.client_id == client.id,
                    SubvencionEntrega.convocatoria_id == call.id,
                )) or SubvencionEntrega(client_id=client.id, convocatoria_id=call.id)
                delivery.intentos = int(delivery.intentos or 0) + 1
                delivery.dispositivos_enviados = successful
                delivery.estado = "enviado" if successful else ("sin_dispositivo" if not devices else "fallido")
                delivery.ultimo_error = "; ".join(errors)[:1000]
                delivery.enviada_at = datetime.now(timezone.utc) if successful else None
                self.db.add(delivery)
            if successful:
                run.avisos_enviados += successful
            self.db.commit()

    def ejecutar(self, today: date | None = None) -> SubvencionEjecucion:
        run = SubvencionEjecucion()
        self.db.add(run)
        self.db.commit()
        if not self._config().servicio_activo:
            run.estado = "omitida"
            run.detalle = "Servicio desactivado desde el panel de control"
            run.fin = datetime.now(timezone.utc)
            self.db.commit()
            return run
        if not self._lock():
            run.estado = "omitida"
            run.detalle = "Ya existe otra sincronizacion en curso"
            run.fin = datetime.now(timezone.utc)
            self.db.commit()
            return run
        try:
            current = today or date.today()
            self.ingerir(run, current)
            self.resumir(run)
            self.notificar(run, current)
            run.estado = "ok"
        except Exception as exc:
            LOG.exception("Fallo en la sincronizacion de subvenciones")
            self.db.rollback()
            run = self.db.get(SubvencionEjecucion, run.id) or run
            run.estado = "error"
            run.detalle = (run.detalle + f"\n{exc}")[-8000:]
        finally:
            run.fin = datetime.now(timezone.utc)
            self.db.add(run)
            self.db.commit()
            self._unlock()
        return run
