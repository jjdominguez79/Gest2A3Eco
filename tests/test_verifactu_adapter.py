"""Tests del adaptador AEAT nulo: nunca transmite, siempre devuelve 'incident'."""

from services.verifactu.adapter import AeatSubmissionPort, NullAeatAdapter


def test_null_adapter_never_reports_accepted():
    adapter = NullAeatAdapter()
    result = adapter.submit_alta(xml="<RegistroAlta/>", huella="A" * 64)
    assert result.status == "incident"
    assert result.status != "accepted"
    assert result.error_code == "not_configured"


def test_null_adapter_anulacion_never_reports_accepted():
    adapter = NullAeatAdapter()
    result = adapter.submit_anulacion(xml="<RegistroAnulacion/>", huella="B" * 64)
    assert result.status == "incident"


def test_null_adapter_satisfies_the_port_protocol():
    adapter: AeatSubmissionPort = NullAeatAdapter()
    assert hasattr(adapter, "submit_alta")
    assert hasattr(adapter, "submit_anulacion")
