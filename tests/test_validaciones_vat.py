from utils.validaciones import (
    inferir_pais_desde_identificacion,
    es_nif_iva_intracomunitario,
    validar_nif_cif_nie,
    validar_nif_o_nif_iva_intracomunitario,
)


def test_validacion_espanola_sigue_funcionando():
    assert validar_nif_cif_nie("B99286320")
    assert validar_nif_o_nif_iva_intracomunitario("B99286320")


def test_vat_intracomunitario_acepta_formato_valido():
    assert es_nif_iva_intracomunitario("DE123456789")
    assert validar_nif_o_nif_iva_intracomunitario("FRAB123456789")


def test_vat_intracomunitario_rechaza_formato_invalido():
    assert not es_nif_iva_intracomunitario("DE123")
    assert not validar_nif_o_nif_iva_intracomunitario("XX123456789")


def test_infiere_pais_desde_identificacion():
    assert inferir_pais_desde_identificacion("B99286320") == "ES"
    assert inferir_pais_desde_identificacion("DE123456789") == "DE"
    assert inferir_pais_desde_identificacion("ABC") == ""
