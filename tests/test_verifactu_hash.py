"""Vectores de prueba oficiales de la AEAT para la huella Veri*FACTU.

Los tres casos y sus hashes esperados se han transcrito literalmente de
"Detalle de las especificaciones tecnicas para generacion de la huella o
hash de los registros de facturacion" (AEAT, v0.1.2, 27/08/2024), apartado
6 ("Ejemplos"). Ver services/verifactu/README.md.

Si esta prueba falla, ``services/verifactu/hash.py`` ha dejado de
reproducir la especificacion oficial: no se debe tocar el algoritmo sin
volver a verificar contra el documento original.
"""

from services.verifactu.hash import compute_alta_hash, compute_anulacion_hash


def test_caso1_primer_registro_de_alta_sin_registro_anterior():
    """Apartado 6.1 del documento: primer registro de un SIF."""
    result = compute_alta_hash(
        id_emisor_factura="89890001K",
        num_serie_factura="12345678/G33",
        fecha_expedicion_factura="01-01-2024",
        tipo_factura="F1",
        cuota_total="12.35",
        importe_total="123.45",
        huella_registro_anterior="",
        fecha_hora_huso_gen_registro="2024-01-01T19:20:30+01:00",
    )
    assert result == (
        "3C464DAF61ACB827C65FDA19F352A4E3BDC2C640E9E9FC4CC058073F38F12F60"
    )


def test_caso2_registro_de_alta_con_registro_anterior():
    """Apartado 6.2 del documento: segundo registro o sucesivo."""
    result = compute_alta_hash(
        id_emisor_factura="89890001K",
        num_serie_factura="12345679/G34",
        fecha_expedicion_factura="01-01-2024",
        tipo_factura="F1",
        cuota_total="12.35",
        importe_total="123.45",
        huella_registro_anterior=(
            "3C464DAF61ACB827C65FDA19F352A4E3BDC2C640E9E9FC4CC058073F38F12F60"
        ),
        fecha_hora_huso_gen_registro="2024-01-01T19:20:35+01:00",
    )
    assert result == (
        "F7B94CFD8924EDFF273501B01EE5153E4CE8F259766F88CF6ACB8935802A2B97"
    )


def test_caso3_registro_de_anulacion_con_registro_anterior():
    """Apartado 6.3 del documento: registro de anulacion, segundo o sucesivo."""
    result = compute_anulacion_hash(
        id_emisor_factura_anulada="89890001K",
        num_serie_factura_anulada="12345679/G34",
        fecha_expedicion_factura_anulada="01-01-2024",
        huella_registro_anterior=(
            "F7B94CFD8924EDFF273501B01EE5153E4CE8F259766F88CF6ACB8935802A2B97"
        ),
        fecha_hora_huso_gen_registro="2024-01-01T19:20:40+01:00",
    )
    assert result == (
        "177547C0D57AC74748561D054A9CEC14B4C4EA23D1BEFD6F2E69E3A388F90C68"
    )


def test_hash_is_always_64_uppercase_hex_characters():
    result = compute_alta_hash(
        id_emisor_factura="B12345678",
        num_serie_factura="APP-000001",
        fecha_expedicion_factura="05-03-2026",
        tipo_factura="F1",
        cuota_total="21.00",
        importe_total="121.00",
        huella_registro_anterior="",
        fecha_hora_huso_gen_registro="2026-03-05T10:00:00+01:00",
    )
    assert len(result) == 64
    assert result == result.upper()
    assert all(c in "0123456789ABCDEF" for c in result)


def test_different_previous_hash_changes_the_result():
    """El encadenamiento real depende del hash anterior, no se ignora."""
    kwargs = dict(
        id_emisor_factura="B12345678", num_serie_factura="APP-000002",
        fecha_expedicion_factura="05-03-2026", tipo_factura="F1",
        cuota_total="21.00", importe_total="121.00",
        fecha_hora_huso_gen_registro="2026-03-05T10:05:00+01:00",
    )
    hash_a = compute_alta_hash(huella_registro_anterior="AAA", **kwargs)
    hash_b = compute_alta_hash(huella_registro_anterior="BBB", **kwargs)
    assert hash_a != hash_b
