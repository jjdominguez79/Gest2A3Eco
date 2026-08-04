from pathlib import Path

from models.gestor_sqlite import GestorSQLite
from services.migracion_pdf_emitidas_service import migrar_pdf_emitidas, ruta_pdf_emitida_canonica


def _insertar_factura(gestor, *, factura_id="f1", pdf_path="", pdf_path_a3=""):
    gestor.conn.execute(
        "INSERT INTO facturas_emitidas_docs "
        "(id,codigo_empresa,ejercicio,serie,numero,nombre,pdf_ref,pdf_path,pdf_path_a3) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (factura_id, "E01006", 2026, "A", "23", "Cliente Demo SL", "R00000023", pdf_path, pdf_path_a3),
    )
    gestor.conn.commit()


def test_migra_copia_y_actualiza_la_ruta_principal(tmp_path):
    gestor = GestorSQLite(tmp_path / "gestor.db")
    origen = tmp_path / "pdfs_emitidas" / "antigua.pdf"
    origen.parent.mkdir()
    origen.write_bytes(b"pdf emitida")
    _insertar_factura(gestor, pdf_path=str(origen))

    resumen = migrar_pdf_emitidas(gestor, root=tmp_path / "Empresas")

    destino = tmp_path / "Empresas" / "E01006" / "2026" / "Facturas_emitidas" / "R00000023_E01006_Cliente Demo SL.pdf"
    assert resumen.migradas == 1
    assert destino.read_bytes() == b"pdf emitida"
    assert gestor.conn.execute("SELECT pdf_path FROM facturas_emitidas_docs WHERE id='f1'").fetchone()[0] == str(destino)
    assert origen.exists()


def test_recupera_desde_a3_si_falta_la_ruta_principal(tmp_path):
    gestor = GestorSQLite(tmp_path / "gestor.db")
    a3 = tmp_path / "a3" / "R00000023.pdf"
    a3.parent.mkdir()
    a3.write_bytes(b"respaldo a3")
    _insertar_factura(gestor, pdf_path=str(tmp_path / "perdido.pdf"), pdf_path_a3=str(a3))

    resumen = migrar_pdf_emitidas(gestor, root=tmp_path / "Empresas")

    assert resumen.migradas == 1
    assert ruta_pdf_emitida_canonica({
        "id": "f1", "codigo_empresa": "E01006", "ejercicio": 2026,
        "serie": "A", "numero": "23", "nombre": "Cliente Demo SL", "pdf_ref": "R00000023",
    }, tmp_path / "Empresas").read_bytes() == b"respaldo a3"


def test_no_sobrescribe_un_destino_con_contenido_distinto(tmp_path):
    gestor = GestorSQLite(tmp_path / "gestor.db")
    origen = tmp_path / "origen.pdf"
    origen.write_bytes(b"original")
    _insertar_factura(gestor, pdf_path=str(origen))
    destino = ruta_pdf_emitida_canonica({
        "id": "f1", "codigo_empresa": "E01006", "ejercicio": 2026,
        "serie": "A", "numero": "23", "nombre": "Cliente Demo SL", "pdf_ref": "R00000023",
    }, tmp_path / "Empresas")
    destino.parent.mkdir(parents=True)
    destino.write_bytes(b"otro")

    resumen = migrar_pdf_emitidas(gestor, root=tmp_path / "Empresas")

    assert resumen.conflictos == 1
    assert gestor.conn.execute("SELECT pdf_path FROM facturas_emitidas_docs WHERE id='f1'").fetchone()[0] == str(origen)
