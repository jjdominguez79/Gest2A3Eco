from services.facturae import FacturaeExporter


def _emisor():
    return {
        "nombre": "Empresa Demo SL",
        "nombre_legal": "Empresa Demo SL",
        "nif": "B12345678",
        "direccion": "Calle Mayor 1",
        "cp": "28001",
        "poblacion": "Madrid",
        "provincia": "Madrid",
        "pais": "ES",
        "telefono": "910000000",
        "email": "admin@demo.es",
    }


def _receptor():
    return {
        "nombre": "Cliente Demo SA",
        "nombre_legal": "Cliente Demo SA",
        "nif": "A12345674",
        "direccion": "Avenida Norte 2",
        "cp": "46001",
        "poblacion": "Valencia",
        "provincia": "Valencia",
        "pais": "ES",
        "email": "cliente@demo.es",
    }


def _factura(lineas, **overrides):
    factura = {
        "serie": "A",
        "numero": "15",
        "fecha_asiento": "05/07/2026",
        "fecha_expedicion": "05/07/2026",
        "fecha_operacion": "05/07/2026",
        "descripcion": "Servicios profesionales",
        "moneda_codigo": "EUR",
        "lineas": lineas,
        "retencion_aplica": 0,
        "retencion_importe": 0.0,
        "descuento_total_tipo": "",
        "descuento_total_valor": 0.0,
    }
    factura.update(overrides)
    return factura


def _linea(base, pct_iva, cuota_iva, **overrides):
    linea = {
        "concepto": "Linea de prueba",
        "unidades": 1,
        "precio": base,
        "base": base,
        "pct_iva": pct_iva,
        "cuota_iva": cuota_iva,
        "pct_irpf": 0,
        "cuota_irpf": 0,
    }
    linea.update(overrides)
    return linea


def test_facturae_simple_generates_xml(tmp_path):
    exporter = FacturaeExporter()
    factura = _factura([_linea(100, 21, 21)])

    result = exporter.export(factura, _emisor(), _receptor(), str(tmp_path / "facturae.xml"))

    assert result.ok is True
    assert "<InvoiceNumber>15</InvoiceNumber>" in result.xml_content
    assert "<TaxTypeCode>01</TaxTypeCode>" in result.xml_content
    assert "<TaxRate>21.00</TaxRate>" in result.xml_content


def test_facturae_multi_iva_generates_grouped_taxes(tmp_path):
    exporter = FacturaeExporter()
    factura = _factura([
        _linea(100, 21, 21),
        _linea(200, 10, 20),
    ])

    result = exporter.export(factura, _emisor(), _receptor(), str(tmp_path / "facturae_multi.xml"))

    assert result.ok is True
    assert result.xml_content.count("<TaxTypeCode>01</TaxTypeCode>") >= 3
    assert "<TaxRate>10.00</TaxRate>" in result.xml_content
    assert "<TaxRate>21.00</TaxRate>" in result.xml_content


def test_facturae_with_irpf_generates_withheld_taxes(tmp_path):
    exporter = FacturaeExporter()
    factura = _factura(
        [_linea(100, 21, 21, pct_irpf=15, cuota_irpf=15)],
        retencion_aplica=1,
        retencion_importe=15.0,
    )

    result = exporter.export(factura, _emisor(), _receptor(), str(tmp_path / "facturae_irpf.xml"))

    assert result.ok is True
    assert "<TaxesWithheld>" in result.xml_content
    assert "<TaxTypeCode>04</TaxTypeCode>" in result.xml_content


def test_facturae_public_admin_requires_dir3(tmp_path):
    exporter = FacturaeExporter()
    factura = _factura([_linea(100, 21, 21)])
    relacion = {
        "facturae_es_administracion_publica": 1,
        "facturae_dir3_oficina_contable": "LA000001",
        "facturae_dir3_organo_gestor": "LA000002",
        "facturae_dir3_unidad_tramitadora": "LA000003",
        "facturae_referencia_expediente": "EXP-1",
    }

    result = exporter.export(factura, _emisor(), _receptor(), str(tmp_path / "facturae_dir3.xml"), relacion)

    assert result.ok is True
    assert "<AdministrativeCentres>" in result.xml_content
    assert "LA000001" in result.xml_content


def test_facturae_missing_dir3_fails_validation():
    exporter = FacturaeExporter()
    factura = _factura([_linea(100, 21, 21)])
    relacion = {"facturae_es_administracion_publica": 1}

    errors = exporter.validate(factura, _emisor(), _receptor(), relacion)

    assert any("DIR3" in error for error in errors)


def test_facturae_total_mismatch_fails_validation():
    exporter = FacturaeExporter()
    factura = _factura([_linea(100, 21, 30)])

    errors = exporter.validate(factura, _emisor(), _receptor())

    assert any("descuadre" in error or "no cuadra" in error for error in errors)


def test_facturae_without_lines_fails_validation():
    exporter = FacturaeExporter()
    factura = _factura([])

    errors = exporter.validate(factura, _emisor(), _receptor())

    assert any("al menos una linea" in error for error in errors)


def test_facturae_export_persistence_update_contains_path(tmp_path):
    exporter = FacturaeExporter()
    factura = _factura([_linea(100, 21, 21)])

    result = exporter.export(factura, _emisor(), _receptor(), str(tmp_path / "facturae_ok.xml"))
    updated = exporter.build_factura_persistence_update(factura, result)

    assert updated["facturae_status"] == "generado"
    assert updated["facturae_xml_path"].endswith("facturae_ok.xml")
