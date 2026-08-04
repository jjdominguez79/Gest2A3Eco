from pathlib import Path

from models.gestor_sqlite import GestorSQLite
from services.documentos_recibidos_a3_service import preparar_documentos_para_suenlace


def _doc(path: Path, doc_id: str, numero: str) -> dict:
    return {
        "id": doc_id, "codigo_empresa": "E00001", "ejercicio": 2026,
        "origen_path": str(path), "pdf_path": str(path), "estado_ocr": "procesado",
        "estado_validacion": "validada", "estado_contable": "pendiente_contabilizar",
        "proveedor_nombre": "Proveedor SL", "numero_factura": numero,
    }


def test_asigna_referencia_y_copia_el_pdf_a_aplicacion_y_a3(tmp_path, monkeypatch):
    gestor = GestorSQLite(tmp_path / "test.db")
    gestor.upsert_empresa({"codigo": "E00001", "ejercicio": 2026, "nombre": "Empresa"})
    source = tmp_path / "entrada.pdf"
    source.write_bytes(b"pdf de prueba")
    doc = _doc(source, "doc-1", "F-1")
    gestor.upsert_factura_recibida_doc(doc)

    prepared = preparar_documentos_para_suenlace(gestor, "E00001", 2026, [doc], a3_root=tmp_path / "A3ECO")

    saved = gestor.get_factura_recibida_doc("doc-1")
    assert prepared[0]["pdf_ref"] == "R00000001"
    assert Path(saved["pdf_path"]) == source
    assert Path(saved["pdf_path"]).read_bytes() == b"pdf de prueba"
    assert (tmp_path / "A3ECO" / "E00001" / "FACTURAS" / "2026" / "R00000001.pdf").read_bytes() == b"pdf de prueba"
    assert saved["datos_extra"]["pdf_path_a3"].endswith("R00000001.pdf")


def test_referencia_compartida_no_colisiona_entre_emitidas_y_recibidas(tmp_path, monkeypatch):
    gestor = GestorSQLite(tmp_path / "test.db")
    gestor.upsert_empresa({"codigo": "E00001", "ejercicio": 2026, "nombre": "Empresa", "pdf_ref_seq": 0})
    gestor.upsert_factura_emitida({
        "id": "emitida", "codigo_empresa": "E00001", "ejercicio": 2026,
        "serie": "A", "numero": "1", "pdf_ref": "E00000009",
    })
    source = tmp_path / "entrada.pdf"
    source.write_bytes(b"pdf")
    doc = _doc(source, "recibida", "F-2")
    gestor.upsert_factura_recibida_doc(doc)

    prepared = preparar_documentos_para_suenlace(gestor, "E00001", 2026, [doc], a3_root=tmp_path / "A3ECO")

    assert prepared[0]["pdf_ref"] == "R00000010"


def test_resuelve_la_empresa_en_a3_compartido_antes_que_configuracion_local(
    tmp_path, monkeypatch,
):
    import services.documentos_recibidos_a3_service as module

    compartida = tmp_path / "servidor" / "A3ECO"
    (compartida / "E00724").mkdir(parents=True)
    local_obsoleta = tmp_path / "local" / "A3"
    (local_obsoleta / "A3ECO" / "E00724").mkdir(parents=True)
    monkeypatch.setattr(module, "A3_SHARED_ROOT", compartida)
    monkeypatch.setattr(
        module, "load_app_config", lambda: {"a3_base_path": str(local_obsoleta)},
    )

    assert module._a3_eco_root(None, "E00724") == compartida
