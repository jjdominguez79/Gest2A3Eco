from pathlib import Path

from services.ocr.ocr_service import OcrService


def _service(empresa: str = "E01006", ejercicio: int = 2026):
    service = object.__new__(OcrService)
    service._empresa = empresa
    service._ejercicio = ejercicio
    return service


def test_archiva_importacion_local_en_repositorio_compartido(tmp_path, monkeypatch):
    root = tmp_path / "Empresas"
    monkeypatch.setattr("services.ocr.ocr_service.get_default_received_documents_dir", lambda: root)
    source = tmp_path / "puesto" / "Factura.pdf"
    source.parent.mkdir()
    source.write_bytes(b"pdf de prueba")

    destination = _service()._archivar_en_repositorio_compartido(source)

    assert destination == root / "E01006" / "2026" / "Facturas_recibidas" / "Factura.pdf"
    assert destination.read_bytes() == b"pdf de prueba"


def test_no_duplica_un_documento_ya_archivado(tmp_path, monkeypatch):
    root = tmp_path / "Empresas"
    monkeypatch.setattr("services.ocr.ocr_service.get_default_received_documents_dir", lambda: root)
    source = root / "E01006" / "2026" / "Facturas_recibidas" / "Factura.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"pdf compartido")

    assert _service()._archivar_en_repositorio_compartido(source) == source
