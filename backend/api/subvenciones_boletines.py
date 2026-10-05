"""Ingesta de ayudas publicadas directamente en boletines oficiales.

Los boletines son la fuente primaria de muchas ayudas directas y medidas que no
se registran como convocatorias independientes en la BDNS.  Este modulo usa
exclusivamente canales oficiales (API BOE y RSS/XML de los diarios) y devuelve
registros normalizados que el servicio de subvenciones puede persistir.
"""

from __future__ import annotations

import hashlib
import html as html_lib
import io
import json
import logging
import os
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Iterable
from urllib.parse import urlparse

import httpx

LOG = logging.getLogger(__name__)

BOE_SUMARIO = "https://www.boe.es/datosabiertos/api/boe/sumario/{fecha}"


@dataclass(frozen=True)
class FuenteBoletin:
    codigo: str
    nombre: str
    ccaa: str
    urls: tuple[str, ...]


# Fuentes oficiales con sindicación estable y pública. Se pueden ampliar sin
# desplegar código mediante SUBSIDIES_BULLETIN_FEEDS_JSON.
FUENTES_AUTONOMICAS: tuple[FuenteBoletin, ...] = (
    FuenteBoletin(
        "BOJA", "Boletín Oficial de la Junta de Andalucía", "ES61",
        tuple(f"https://www.juntadeandalucia.es/boja/distribucion/s5{x}.xml" for x in (1, 3, 5)),
    ),
    FuenteBoletin(
        "BOC-CAN", "Boletín Oficial de Canarias", "ES70",
        (
            "https://www.gobiernodecanarias.org/boc/feeds/capitulo/disposiciones_generales.rss",
            "https://www.gobiernodecanarias.org/boc/feeds/capitulo/otras_resoluciones.rss",
            "https://www.gobiernodecanarias.org/boc/feeds/capitulo/otros_anuncios.rss",
        ),
    ),
    FuenteBoletin(
        "BOC-CANT", "Boletín Oficial de Cantabria", "ES13",
        ("https://www.cantabria.es/o/BOC/feed/6802095",),
    ),
    FuenteBoletin(
        "BOCYL", "Boletín Oficial de Castilla y León", "ES41",
        ("https://bocyl.jcyl.es/rss.do",),
    ),
    FuenteBoletin(
        "DOE", "Diario Oficial de Extremadura", "ES43",
        tuple(f"https://doe.juntaex.es/rss/rss.php?seccion={x}" for x in range(6)),
    ),
    FuenteBoletin(
        "DOG", "Diario Oficial de Galicia", "ES11",
        tuple(
            f"https://www.xunta.gal/diario-oficial-galicia/rss/Seccion{x}_gl.rss"
            for x in (1, 6, 10, 11)
        ),
    ),
    FuenteBoletin(
        "BOCM", "Boletín Oficial de la Comunidad de Madrid", "ES30",
        ("https://www.bocm.es/ultimo-boletin.xml",),
    ),
    FuenteBoletin(
        "BOPV", "Boletín Oficial del País Vasco", "ES21",
        ("https://www.euskadi.eus/bopv2/datos/Ultimo.xml",),
    ),
)

_AYUDA = re.compile(
    r"\b(ayudas?|subvenciones?|becas?|incentivos?|bonificaciones?|"
    r"compensaciones?|financiaci[oó]n subvencionada)\b", re.I,
)
_ACCIONABLE = re.compile(
    r"\b(se convoca|convocatoria|extracto|se establece(?:n)? (?:un sistema de )?ayudas?|"
    r"ayudas? directas?|podr[aá]n ser beneficiari|ser[aá]n beneficiari|"
    r"plazo de presentaci[oó]n|solicitud(?:es)? se presentar|se prorroga|"
    r"se modifica|modificaci[oó]n|ampliaci[oó]n del plazo)\b", re.I,
)
_NO_ACCIONABLE = re.compile(
    r"\b(concesi[oó]n de subvenci[oó]n|subvenciones concedidas|resoluci[oó]n de concesi[oó]n|"
    r"se deniega|relaci[oó]n de (?:personas beneficiarias|beneficiarios|titulares)|"
    r"publica la relaci[oó]n|justificaci[oó]n de subvenciones|"
    r"suplementos? de cr[eé]dito|medidas aplicables)\b", re.I,
)
_BDNS = re.compile(r"BDNS\s*(?:\(\s*Identif\.?\s*\))?\s*[:.]\s*(\d{5,})", re.I)
_ARTICLE = re.compile(r"^Art[ií]culo\s+(\d+(?:\s*[a-záéíóú]+)?)\s*[.ºª]*\s*(.*)", re.I)
_DATE_RANGE = re.compile(
    r"(?:entre|desde)\s+(?:el\s+)?(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})"
    r"\s+(?:y|hasta)\s+(?:el\s+)?(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})",
    re.I,
)
_UNTIL = re.compile(
    r"(?:hasta|finaliza(?:r[aá])?|finalizar[aá]?\s+el)\s+(?:el\s+)?(\d{1,2})\s+de\s+"
    r"([a-záéíóú]+)\s+de\s+(\d{4})", re.I,
)
_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _plain(value: str) -> str:
    value = html_lib.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _ascii(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", value or "")
        if unicodedata.category(char) != "Mn"
    )


def _parse_date(value: str | None) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    for pattern, candidate in (
        ("%Y%m%d", raw[:8]), ("%Y-%m-%d", raw[:10]), ("%d/%m/%Y", raw[:10]),
        ("%a, %d %b %Y %z", raw), ("%a, %d %b %Y", raw),
    ):
        try:
            return datetime.strptime(candidate, pattern).date()
        except ValueError:
            pass
    try:
        return parsedate_to_datetime(raw).date()
    except (TypeError, ValueError, OverflowError):
        return None


def _dates_from_text(text: str) -> tuple[date | None, date | None, str]:
    normalized = _plain(text).lower()
    match = _DATE_RANGE.search(normalized)
    if match:
        try:
            start = date(int(match.group(3)), _MONTHS[_ascii(match.group(2))], int(match.group(1)))
            end = date(int(match.group(6)), _MONTHS[_ascii(match.group(5))], int(match.group(4)))
            return start, end, _plain(match.group(0))
        except (KeyError, ValueError):
            pass
    match = _UNTIL.search(normalized)
    if match:
        try:
            end = date(int(match.group(3)), _MONTHS[_ascii(match.group(2))], int(match.group(1)))
            return None, end, _plain(match.group(0))
        except (KeyError, ValueError):
            pass
    exercise = re.search(r"(?:ejercicio|año)\s+(20\d{2})", normalized)
    if exercise:
        return None, date(int(exercise.group(1)), 12, 31), ""
    final_month = re.search(
        r"(?:para|durante)\s+los\s+meses\s+de\s+"
        r".{0,100}?\by\s+"
        r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
        r"\s+de\s+(20\d{2})", normalized,
    )
    if final_month:
        month = _MONTHS[_ascii(final_month.group(1))]
        year = int(final_month.group(2))
        next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        return None, next_month - timedelta(days=1), ""
    return None, None, ""


def _labels(text: str) -> list[str]:
    normalized = _ascii(text).lower()
    mapping = (
        ("transporte", ("transporte", "taxi", "vehiculo", "ferroviari", "maritimo")),
        ("autonomos", ("autonom",)),
        ("empleo", ("empleo", "contratacion", "desemplead")),
        ("digitalizacion", ("digital", "tic", "tecnologia")),
        ("industria", ("industr",)),
        ("comercio", ("comerc",)),
        ("hosteleria", ("hosteler", "restauracion")),
        ("turismo", ("turism",)),
        ("agricultura", ("agrari", "agricult", "ganader")),
        ("pesca", ("pesca", "pesquer")),
        ("energia", ("energia", "energet", "gasoleo", "carburante")),
        ("vivienda", ("vivienda", "rehabilitacion")),
        ("formacion", ("formacion", "estudio", "educa")),
        ("innovacion", ("innovacion", "i+d")),
        ("cultura", ("cultura", "libro", "musica", "arte")),
        ("social", ("social", "discapacidad", "conciliacion")),
        ("medio_ambiente", ("ambiente", "ecolog", "sostenib")),
    )
    result = [label for label, words in mapping if any(word in normalized for word in words)]
    return result[:3] or ["otros"]


def _beneficiaries(text: str) -> str:
    sentences = re.split(r"(?<=[.;])\s+(?=[A-ZÁÉÍÓÚ0-9])", _plain(text))
    selected = [
        sentence for sentence in sentences
        if re.search(r"\b(ser[aá]n|podr[aá]n ser|personas?|entidades?) beneficiari", sentence, re.I)
    ]
    return " ".join(selected[:2])[:1200]


def _summary(text: str, title: str, deadline: str) -> dict:
    clean = _plain(text)
    paragraphs = [part.strip() for part in re.split(r"(?<=[.])\s+", clean) if part.strip()]
    beneficiary = _beneficiaries(clean)
    amount = next((p for p in paragraphs if re.search(r"\b(cuant[ií]a|importe|euros?|€)\b", p, re.I)), "")
    requirements = [
        p[:300] for p in paragraphs
        if re.search(r"\b(deber[aá]n|requisitos?|estar de alta|titulares? de)\b", p, re.I)
    ][:5]
    return {
        "resumen": (paragraphs[0] if paragraphs else title)[:900],
        "beneficiarios": beneficiary[:600],
        "que_financia": title[:600],
        "cuantia": amount[:300],
        "requisitos": requirements,
        "plazo": deadline[:300],
        "etiquetas": _labels(f"{title} {clean}"),
    }


def _hash(raw: dict) -> str:
    return hashlib.sha256(
        json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"),
    ).hexdigest()


def _code(prefix: str, source_id: str, suffix: str = "") -> str:
    raw = re.sub(r"[^A-Za-z0-9-]+", "-", source_id).strip("-")
    value = f"{prefix}-{raw}{('-' + suffix) if suffix else ''}"
    if len(value) <= 80:
        return value
    return f"{prefix}-{hashlib.sha1(value.encode()).hexdigest()[:18]}"


def _scope_for_feed(source: FuenteBoletin, title: str) -> dict:
    organ = title.split(":", 1)[0].strip()
    normalized = _ascii(organ).upper()
    local = any(word in normalized for word in ("AYUNTAMIENTO", "CONCELLO", "AJUNTAMENT", "UDALA"))
    provincial = any(word in normalized for word in ("DIPUTACION", "CABILDO", "CONSELL INSULAR"))
    municipality = ""
    if local:
        municipality = re.sub(
            r"^(AYUNTAMIENTO|CONCELLO|AJUNTAMENT|UDALA)\s+(DE\s+|D')?", "", organ,
            flags=re.I,
        ).strip()
    return {
        "ambito": "LOCAL" if local or provincial else "AUTONOMICA",
        "alcance_nacional": False,
        "ccaa_json": [source.ccaa],
        "provincias_json": [],
        "municipio_nombre": municipality,
        "municipio_slug": re.sub(r"[^a-z0-9]+", "-", _ascii(municipality).lower()).strip("-"),
        "es_provincial": provincial,
    }


def _normalized_record(
    *, code: str, source: str, source_name: str, source_code: str, title: str,
    organ: str, published: date | None, text: str, links: list[dict], scope: dict,
    raw: dict, nature: str = "convocatoria",
) -> dict:
    start, end, deadline = _dates_from_text(text)
    beneficiary = _beneficiaries(text)
    return {
        "codigo_bdns": code,
        "fuente": source,
        "fuente_nombre": source_name,
        "codigo_fuente": source_code,
        "naturaleza": nature,
        "titulo": _plain(title)[:2000],
        "organo_nivel1": "ESTADO" if source == "BOE" else "AUTONOMICO",
        "organo_nivel2": organ[:250],
        "organo_nivel3": "",
        "fecha_recepcion": published,
        "fecha_inicio": start,
        "fecha_fin": end,
        "texto_inicio": deadline if start else "",
        "texto_fin": deadline,
        "abierto": False if end and end < date.today() else None,
        "presupuesto": None,
        "tipo_convocatoria": nature.replace("_", " ").title(),
        "finalidad": _plain(text)[:2000],
        "beneficiarios_json": [beneficiary] if beneficiary else [],
        "sectores_json": _labels(f"{title} {text}"),
        "instrumentos_json": ["Ayuda directa"] if nature == "ayuda_directa" else [],
        "mrr": "next generation" in text.lower() or "mecanismo de recuperación" in text.lower(),
        "enlaces_json": links,
        "resumen_json": _summary(text, title, deadline),
        "resumen_estado": "ok",
        "resumen_modelo": "extraccion-boletines-v1",
        "hash_fuente": _hash(raw),
        "hash_resumen": _hash(raw),
        "raw_json": raw,
        **scope,
    }


def _is_actionable(title: str, text: str = "") -> bool:
    combined = _plain(f"{title} {text}")
    if not _AYUDA.search(combined):
        return False
    title_plain = _plain(title)
    if not _AYUDA.search(title_plain):
        return False
    if _NO_ACCIONABLE.search(title_plain) and not re.search(r"\bconvoca", title_plain, re.I):
        return False
    if re.search(r"bases reguladoras", title_plain, re.I) and not re.search(
        r"\b(convocatoria|se convoca|ayuda directa)\b", title_plain, re.I,
    ):
        return False
    return bool(_ACCIONABLE.search(combined))


class _OfficialHttp:
    def __init__(self, client: httpx.Client | None = None):
        timeout = float(os.getenv("SUBSIDIES_BULLETIN_TIMEOUT", "40"))
        self.client = client or httpx.Client(
            timeout=timeout, follow_redirects=True,
            headers={"User-Agent": "Gestinem-Ayudas/2.0 (+https://gestinem.es)"},
        )
        self.pause = float(os.getenv("SUBSIDIES_BULLETIN_PAUSE", "0.15"))

    def get(self, url: str, *, accept: str = "*/*") -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.client.get(url, headers={"Accept": accept})
                if response.status_code == 404:
                    return response
                response.raise_for_status()
                if self.pause:
                    time.sleep(self.pause)
                return response
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"La fuente oficial no responde ({url}): {last_error}")


def _walk_boe(node, context: dict | None = None) -> Iterable[dict]:
    context = dict(context or {})
    if isinstance(node, dict):
        if "seccion" in node and isinstance(node["seccion"], (dict, list)):
            pass
        if "codigo" in node and "nombre" in node and any(
            token in str(node.get("nombre", "")).lower()
            for token in ("disposiciones", "anuncios", "otras")
        ):
            context["seccion"] = str(node.get("codigo") or "")
        if node.get("identificador") and node.get("titulo") and (
            node.get("url_xml") or node.get("url_html")
        ):
            yield {**node, **context}
        for value in node.values():
            yield from _walk_boe(value, context)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_boe(value, context)


def _xml_text(root: ET.Element, path: str) -> str:
    node = root.find(path)
    return _plain("".join(node.itertext())) if node is not None else ""


class BoeClient(_OfficialHttp):
    """Lee el sumario BOE y descompone las normas con varias líneas de ayuda."""

    def listar_desde(self, since: date, until: date) -> list[dict]:
        result: list[dict] = []
        current = since
        seen: set[str] = set()
        while current <= until:
            response = self.get(
                BOE_SUMARIO.format(fecha=current.strftime("%Y%m%d")),
                accept="application/json",
            )
            current += timedelta(days=1)
            if response.status_code == 404:
                continue
            try:
                payload = response.json()
            except ValueError as exc:
                LOG.warning("Sumario BOE no válido: %s", exc)
                continue
            for item in _walk_boe(payload.get("data") or {}):
                identifier = str(item.get("identificador") or "")
                if not identifier or identifier in seen:
                    continue
                seen.add(identifier)
                title = _plain(str(item.get("titulo") or ""))
                # Los títulos de reales decretos pueden ser genéricos. Se leen
                # todas las disposiciones generales y los anuncios ya marcados.
                if not _AYUDA.search(title) and str(item.get("seccion") or "") != "1":
                    continue
                xml_url = str(item.get("url_xml") or "")
                if not xml_url:
                    continue
                try:
                    xml_response = self.get(xml_url, accept="application/xml")
                    result.extend(self._parse_document(xml_response.content, item))
                except Exception as exc:
                    LOG.warning("No se pudo leer %s: %s", identifier, exc)
        return result

    def _parse_document(self, content: bytes, item: dict) -> list[dict]:
        root = ET.fromstring(content)
        identifier = _xml_text(root, "./metadatos/identificador") or str(item["identificador"])
        document_title = _xml_text(root, "./metadatos/titulo") or _plain(str(item.get("titulo") or ""))
        published = _parse_date(_xml_text(root, "./metadatos/fecha_publicacion"))
        department = _xml_text(root, "./metadatos/departamento")
        html_url = _xml_text(root, "./metadatos/url_html") or str(item.get("url_html") or "")
        if not html_url:
            html_url = f"https://www.boe.es/diario_boe/txt.php?id={identifier}"
        pdf_url = _xml_text(root, "./metadatos/url_pdf")
        links = [{"tipo": "boletin", "titulo": "Publicación oficial en el BOE", "url": html_url}]
        if pdf_url:
            links.append({"tipo": "documento", "titulo": "PDF oficial", "url": pdf_url})
        paragraphs: list[tuple[str, str]] = []
        for node in root.iter():
            if node.tag.rsplit("}", 1)[-1] != "p":
                continue
            text = _plain("".join(node.itertext()))
            if text:
                paragraphs.append((str(node.attrib.get("class") or ""), text))
        full_text = "\n".join(text for _kind, text in paragraphs)
        bdns = _BDNS.search(full_text)
        if bdns:
            return [{
                "merge_bdns": bdns.group(1),
                "source": "BOE",
                "source_code": identifier,
                "links": links,
                "raw": {"identificador": identifier, "titulo": document_title},
            }]
        records: list[dict] = []
        articles: list[tuple[str, str, list[str]]] = []
        current_number = ""
        current_title = ""
        current_body: list[str] = []
        for kind, text in paragraphs:
            match = _ARTICLE.match(text) if kind == "articulo" or text.lower().startswith("artículo") else None
            if match:
                if current_number:
                    articles.append((current_number, current_title, current_body))
                current_number, current_title, current_body = match.group(1), match.group(2), []
            elif current_number:
                current_body.append(text)
        if current_number:
            articles.append((current_number, current_title, current_body))
        for number, article_title, body in articles:
            block = "\n".join(body)
            if not _is_actionable(article_title, block):
                continue
            nature = "ayuda_directa" if re.search(
                r"ayudas? directas?|ayuda extraordinaria|autom[aá]tic", f"{article_title} {block}", re.I,
            ) else "convocatoria"
            source_code = f"{identifier}#articulo-{_ascii(number).replace(' ', '-')}"
            raw = {
                "identificador": identifier, "articulo": number,
                "titulo_documento": document_title, "texto": block[:50000],
            }
            records.append(_normalized_record(
                code=_code("BOE", identifier.removeprefix("BOE-"), _ascii(number).replace(" ", "-")),
                source="BOE", source_name="Boletín Oficial del Estado",
                source_code=source_code, title=article_title or document_title,
                organ=department, published=published, text=block, links=links,
                scope={
                    "ambito": "ESTATAL", "alcance_nacional": True,
                    "ccaa_json": [], "provincias_json": [],
                    "municipio_nombre": "", "municipio_slug": "", "es_provincial": False,
                },
                raw=raw, nature=nature,
            ))
        if not records and _is_actionable(document_title, full_text):
            raw = {"identificador": identifier, "titulo": document_title, "texto": full_text[:50000]}
            records.append(_normalized_record(
                code=_code("BOE", identifier.removeprefix("BOE-")), source="BOE",
                source_name="Boletín Oficial del Estado", source_code=identifier,
                title=document_title, organ=department, published=published,
                text=full_text, links=links,
                scope={
                    "ambito": "ESTATAL", "alcance_nacional": True,
                    "ccaa_json": [], "provincias_json": [],
                    "municipio_nombre": "", "municipio_slug": "", "es_provincial": False,
                }, raw=raw,
            ))
        return records


def _children_text(node: ET.Element, names: tuple[str, ...]) -> str:
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1].lower() in names:
            value = _plain("".join(child.itertext()))
            if value:
                return value
    return ""


def _feed_entries(content: bytes) -> Iterable[dict]:
    root = ET.fromstring(content)
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].lower() not in {"item", "entry"}:
            continue
        link = ""
        for child in node.iter():
            if child.tag.rsplit("}", 1)[-1].lower() == "link":
                link = (child.attrib.get("href") or child.text or "").strip()
                if link:
                    break
        yield {
            "title": _children_text(node, ("title",)),
            "link": link,
            "description": _children_text(node, ("description", "summary", "content", "encoded")),
            "published": _parse_date(_children_text(node, ("pubdate", "date", "published", "updated"))),
            "guid": _children_text(node, ("guid", "id")),
        }


def _pdf_text(content: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    maximum = int(os.getenv("SUBSIDIES_BULLETIN_MAX_CHARS", "60000"))
    parts: list[str] = []
    size = 0
    for page in reader.pages:
        value = page.extract_text() or ""
        parts.append(value)
        size += len(value)
        if size >= maximum:
            break
    return "\n".join(parts)[:maximum]


def _html_text(content: bytes) -> str:
    try:
        from lxml import html
        root = html.fromstring(content)
        for unwanted in root.xpath("//script|//style|//nav|//header|//footer"):
            unwanted.drop_tree()
        candidates = root.xpath("//article|//main")
        target = candidates[0] if candidates else root
        return _plain(target.text_content())[:60000]
    except Exception:
        return _plain(content.decode("utf-8", errors="replace"))[:60000]


def _title_from_document(feed_title: str, text: str) -> str:
    title = _plain(feed_title)
    if ":" in title:
        _organ, candidate = title.split(":", 1)
        if len(candidate.strip()) > 30:
            title = candidate.strip()
    # Los PDF del BOC repiten el CVE inmediatamente antes del título completo.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines[:80]):
        match = re.search(r"CVE-\d{4}-\d+\s+(.+)", line)
        if not match or len(match.group(1)) < 15:
            continue
        parts = [match.group(1)]
        for following in lines[index + 1:index + 8]:
            if following.startswith(("CVE-", "Boletín Oficial", "boc.cantabria.es", "Pág.")):
                break
            parts.append(following)
            if following.endswith("."):
                break
        candidate = _plain(" ".join(parts))
        if _AYUDA.search(candidate):
            return candidate[:2000]
    return title


def _sources_from_environment() -> tuple[FuenteBoletin, ...]:
    raw = os.getenv("SUBSIDIES_BULLETIN_FEEDS_JSON", "").strip()
    if not raw:
        return FUENTES_AUTONOMICAS
    try:
        extra = json.loads(raw)
        parsed = tuple(FuenteBoletin(
            codigo=str(item["codigo"]), nombre=str(item["nombre"]),
            ccaa=str(item["ccaa"]), urls=tuple(item["urls"]),
        ) for item in extra)
        return FUENTES_AUTONOMICAS + parsed
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        LOG.error("SUBSIDIES_BULLETIN_FEEDS_JSON no válido: %s", exc)
        return FUENTES_AUTONOMICAS


class BoletinesAutonomicosClient(_OfficialHttp):
    def __init__(self, client: httpx.Client | None = None, *, sources=None):
        super().__init__(client)
        self.sources = tuple(sources) if sources is not None else _sources_from_environment()

    def listar_desde(self, since: date) -> list[dict]:
        result: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for source in self.sources:
            for feed_url in source.urls:
                try:
                    response = self.get(feed_url, accept="application/rss+xml, application/xml, text/xml")
                    entries = list(_feed_entries(response.content))
                except Exception as exc:
                    LOG.warning("No se pudo leer el canal %s: %s", feed_url, exc)
                    continue
                for entry in entries:
                    published = entry["published"]
                    if published and published < since:
                        continue
                    link = entry["link"] or entry["guid"]
                    key = (source.codigo, link or entry["title"])
                    if not link or key in seen:
                        continue
                    seen.add(key)
                    teaser = f"{entry['title']} {entry['description']}"
                    if not _AYUDA.search(teaser):
                        continue
                    try:
                        document = self.get(link)
                        content_type = (document.headers.get("content-type") or "").lower()
                        text = _pdf_text(document.content) if (
                            "pdf" in content_type or document.content.startswith(b"%PDF")
                        ) else _html_text(document.content)
                    except Exception as exc:
                        LOG.warning("No se pudo leer el anuncio %s: %s", link, exc)
                        text = _plain(entry["description"])
                    title = _title_from_document(entry["title"], text)
                    if not _is_actionable(title, text):
                        continue
                    bdns = _BDNS.search(text)
                    source_id = ""
                    if source.codigo == "BOC-CANT":
                        cve = re.search(r"CVE-(\d{4})-(\d+)", text)
                        if cve:
                            source_id = f"CVE-{cve.group(1)}-{cve.group(2)}"
                    if not source_id:
                        parts = [part for part in urlparse(link).path.split("/") if part]
                        source_id = "-".join(parts[-3:]) or entry["guid"]
                    links = [{"tipo": "boletin", "titulo": f"Publicación oficial en {source.codigo}", "url": link}]
                    raw = {
                        "fuente": source.codigo, "codigo": source_id,
                        "titulo": title, "url": link, "texto": text[:50000],
                    }
                    if bdns:
                        result.append({
                            "merge_bdns": bdns.group(1), "source": source.codigo,
                            "source_code": source_id, "links": links, "raw": raw,
                        })
                        continue
                    organ = _plain(entry["title"].split(":", 1)[0])
                    nature = "ayuda_directa" if re.search(r"ayudas? directas?", text, re.I) else "convocatoria"
                    result.append(_normalized_record(
                        code=_code(source.codigo, source_id), source=source.codigo,
                        source_name=source.nombre, source_code=source_id,
                        title=title, organ=organ, published=published,
                        text=text or entry["description"], links=links,
                        scope=_scope_for_feed(source, entry["title"]), raw=raw,
                        nature=nature,
                    ))
        return result
