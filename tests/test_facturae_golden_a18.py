"""Tests de regresion contra `tests/fixtures/facturae/A18.xml`.

A18.xml es una factura Facturae 3.2.1 real, generada por otro programa y
aceptada sin incidencias por FACe. Sirve como "golden file" para comprobar
que el generador de Gest2A3Eco produce un XML valido contra el XSD oficial
3.2.1 (`services/facturae/schemas/facturae_3_2_1.xsd`) y con la misma
estructura que un fichero que sabemos que funciona en produccion.

Ver tambien el skill `.claude/skills/facturae-xml/SKILL.md`.
"""

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from services.facturae import FacturaeExporter
from services.facturae.facturae_codes import FACTURAE_NS, SCHEMA_VERSION

lxml_etree = pytest.importorskip(
    "lxml.etree", reason="lxml es necesario para validar contra el XSD oficial"
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "facturae"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "services" / "facturae" / "schemas" / "facturae_3_2_1.xsd"


@pytest.fixture(scope="module")
def facturae_schema():
    return lxml_etree.XMLSchema(lxml_etree.parse(str(SCHEMA_PATH)))


def _assert_xsd_valid(schema, xml_content: str) -> None:
    doc = lxml_etree.fromstring(xml_content.encode("utf-8"))
    if not schema.validate(doc):
        errors = "\n".join(str(e) for e in schema.error_log)
        pytest.fail(f"El XML no valida contra el XSD oficial Facturae {SCHEMA_VERSION}:\n{errors}")


def _a18_payload():
    """Reconstruye los datos de A18.xml como payload de Gest2A3Eco."""
    emisor = {
        "nombre": "ARTUR DURINYAN",
        "nombre_legal": "ARTUR DURINYAN",
        "nif": "Y0247383D",
        "direccion": "CL POMALUENGO 127A",
        "cp": "39660",
        "poblacion": "CASTAÑEDA",
        "provincia": "CANTABRIA",
        "pais": "ES",
    }
    receptor = {
        "nombre": "CEIP PINTOR ESCUDERO ESPRONCEDA",
        "nombre_legal": "CEIP PINTOR ESCUDERO ESPRONCEDA",
        "nif": "Q3968271A",
        "direccion": "CARRETERA AL CEMENTERIO S/N",
        "cp": "39300",
        "poblacion": "TORRELAVEGA",
        "provincia": "CANTABRIA",
        "pais": "ES",
    }
    relacion = {
        "facturae_es_administracion_publica": True,
        # Codigos DIR3 tal cual figuran en A18.xml: A06004070 hace de oficina
        # contable (RoleTypeCode 01) y A06018605 hace de organo gestor (02) y
        # de unidad tramitadora (03).
        "facturae_dir3_oficina_contable": "A06004070",
        "facturae_dir3_organo_gestor": "A06018605",
        "facturae_dir3_unidad_tramitadora": "A06018605",
    }
    factura = {
        "serie": "A",
        "numero": "18",
        "fecha_asiento": "10/08/2026",
        "fecha_expedicion": "10/08/2026",
        "fecha_operacion": "10/08/2026",
        "descripcion": "Trabajos realizados desglosados en PRESUPUESTO Nº 010",
        "moneda_codigo": "EUR",
        "retencion_aplica": 0,
        "retencion_importe": 0.0,
        "descuento_total_tipo": "",
        "descuento_total_valor": 0.0,
        "lineas": [
            {
                "concepto": "Trabajos realizados desglosados en PRESUPUESTO Nº 010",
                "unidades": 1,
                "precio": 4080.30,
                "base": 4080.30,
                "pct_iva": 21,
                "cuota_iva": 856.86,
                "pct_irpf": 0,
                "cuota_irpf": 0,
            }
        ],
    }
    return emisor, receptor, relacion, factura


def test_a18_fixture_is_itself_xsd_valid(facturae_schema):
    """El propio fichero de referencia (aceptado por FACe) debe validar.

    Si esto falla, el problema esta en el XSD local o en el fixture, no en
    el generador de Gest2A3Eco.
    """
    xml_content = (FIXTURES_DIR / "A18.xml").read_text(encoding="utf-8")
    _assert_xsd_valid(facturae_schema, xml_content)


def test_generated_xml_from_a18_data_is_xsd_valid(tmp_path, facturae_schema):
    """El XML que genera Gest2A3Eco para la factura A18 valida contra el XSD oficial."""
    emisor, receptor, relacion, factura = _a18_payload()
    exporter = FacturaeExporter()

    result = exporter.export(factura, emisor, receptor, str(tmp_path / "A18_generado.xml"), relacion)

    assert result.ok, result.errors
    assert not result.errors
    _assert_xsd_valid(facturae_schema, result.xml_content)


def test_generated_xml_matches_a18_key_data(tmp_path):
    """Compara los datos clave del XML generado con los del fichero real A18.xml."""
    emisor, receptor, relacion, factura = _a18_payload()
    exporter = FacturaeExporter()
    result = exporter.export(factura, emisor, receptor, str(tmp_path / "A18_generado.xml"), relacion)
    assert result.ok, result.errors

    generated = ET.fromstring(result.xml_content)
    golden = ET.fromstring((FIXTURES_DIR / "A18.xml").read_text(encoding="utf-8"))

    def text(root, path):
        node = root.find(path)
        return node.text if node is not None else None

    assert text(generated, ".//TaxIdentificationNumber") == text(golden, ".//TaxIdentificationNumber")
    assert text(generated, ".//InvoiceTotal") == text(golden, ".//InvoiceTotal")
    assert text(generated, ".//InvoiceNumber") == text(golden, ".//InvoiceNumber")

    generated_centres = {
        (c.find("CentreCode").text, c.find("RoleTypeCode").text)
        for c in generated.findall(".//AdministrativeCentre")
    }
    golden_centres = {
        (c.find("CentreCode").text, c.find("RoleTypeCode").text)
        for c in golden.findall(".//AdministrativeCentre")
    }
    assert generated_centres == golden_centres


def test_administrative_centres_come_before_legal_entity(tmp_path):
    """Regresion: BusinessType (XSD) exige AdministrativeCentres antes de
    LegalEntity/Individual dentro de SellerParty/BuyerParty. El generador
    llego a emitirlos en el orden contrario."""
    emisor, receptor, relacion, factura = _a18_payload()
    exporter = FacturaeExporter()
    result = exporter.export(factura, emisor, receptor, str(tmp_path / "orden.xml"), relacion)
    assert result.ok, result.errors

    buyer_party = result.xml_content.split("<BuyerParty>", 1)[1]
    assert buyer_party.index("<AdministrativeCentres>") < buyer_party.index("<LegalEntity>")


def test_batch_invoice_currency_code_is_last(tmp_path):
    """Regresion: BatchType (XSD) exige InvoiceCurrencyCode al final del
    bloque Batch, despues de los tres importes totales."""
    emisor, receptor, relacion, factura = _a18_payload()
    exporter = FacturaeExporter()
    result = exporter.export(factura, emisor, receptor, str(tmp_path / "batch.xml"), relacion)
    assert result.ok, result.errors

    batch = result.xml_content.split("<Batch>", 1)[1].split("</Batch>", 1)[0]
    assert batch.index("<TotalExecutableAmount>") < batch.index("<InvoiceCurrencyCode>")


def test_invoice_issue_data_tag_name(tmp_path):
    """Regresion: el elemento se llama InvoiceIssueData en el XSD, no IssueData."""
    emisor, receptor, relacion, factura = _a18_payload()
    exporter = FacturaeExporter()
    result = exporter.export(factura, emisor, receptor, str(tmp_path / "issuedata.xml"), relacion)
    assert result.ok, result.errors

    assert "<InvoiceIssueData>" in result.xml_content
    assert "<IssueData>" not in result.xml_content


def test_namespace_and_schema_version_match_official_xsd():
    """Regresion: el namespace/version deben ser los de Facturae 3.2.1
    (http://www.facturae.es/Facturae/2014/v3.2.1/Facturae), no la version
    2009/v3.2.2 que usaba el generador antes de esta correccion."""
    assert FACTURAE_NS == "http://www.facturae.es/Facturae/2014/v3.2.1/Facturae"
    assert SCHEMA_VERSION == "3.2.1"
