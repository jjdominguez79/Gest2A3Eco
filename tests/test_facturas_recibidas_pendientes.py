from pathlib import Path

from models.gestor_base import SCHEMA, GestorBase
from services.facturas_recibidas_pendientes_service import (
    FacturasRecibidasPendientesService,
)
from services.ocr_recibidas_service import mark_docs_as_generated
from services.estado_facturas_recibidas import estado_efectivo
from views.ui_facturas_recibidas_pendientes import UIFacturasRecibidasPendientes
from views.ui_gestion_documental import UIGestionDocumental


class _Cursor:
    rowcount = 2


class _Connection:
    def __init__(self):
        self.calls = []
        self.commits = 0

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), tuple(params)))
        return _Cursor()

    def commit(self):
        self.commits += 1


def _gestor_with_connection(connection):
    gestor = object.__new__(GestorBase)
    gestor.conn = connection
    return gestor


def test_schema_separa_estado_contable_e_impresion_del_ocr():
    assert "estado_contable TEXT NOT NULL DEFAULT 'pendiente'" in SCHEMA
    assert "metodo_contabilizacion TEXT" in SCHEMA
    assert "contabilizada_manualmente_at TEXT" in SCHEMA
    assert "veces_impresa INTEGER NOT NULL DEFAULT 0" in SCHEMA
    assert "documento_archivo_id TEXT" in SCHEMA
    assert "buzon_origen TEXT" in SCHEMA


def test_upsert_factura_recibida_sincroniza_su_documento_archivado():
    connection = _Connection()
    gestor = _gestor_with_connection(connection)

    gestor.upsert_factura_recibida_doc({
        "id": "ocr-1",
        "documento_archivo_id": "archivo-1",
        "codigo_empresa": "E00001",
        "ejercicio": 2026,
        "estado_contable": "pendiente_contabilizar",
        "numero_asiento": "",
    })

    statements = [sql for sql, _params in connection.calls]
    assert any("UPDATE facturas_recibidas_docs SET documento_archivo_id" in sql for sql in statements)
    assert any("UPDATE documentos_archivo SET estado_contable" in sql for sql in statements)
    assert connection.commits == 1


def test_registro_documental_inicializa_estado_contable_pendiente():
    connection = _Connection()
    gestor = _gestor_with_connection(connection)

    document_id = gestor.registrar_documento_archivo({
        "id": "doc-new",
        "codigo_empresa": "E00001",
        "ejercicio": 2026,
        "categoria_id": "facturas_recibidas",
        "nombre_original": "factura.pdf",
        "nombre_archivo": "factura.pdf",
        "ruta": "X:/factura.pdf",
        "hash_archivo": "abc",
    })

    sql, params = connection.calls[0]
    assert document_id == "doc-new"
    assert sql.count("?") == len(params)
    assert "estado_contable" in sql
    assert "pendiente" in params


def test_marca_facturas_como_contabilizadas_manualmente():
    connection = _Connection()
    gestor = _gestor_with_connection(connection)

    changed = gestor.cambiar_estado_contable_documentos(
        ["doc-1", "doc-2"],
        "contabilizada_manual",
        usuario="Empleado",
        fecha_contable="2026-09-26",
        numero_asiento="42",
        observaciones="Contabilizada en A3",
    )

    sql, params = connection.calls[0]
    assert changed == 2
    assert "estado_contable='contabilizada_manual'" in sql
    assert "metodo_contabilizacion='manual_a3_papel'" in sql
    assert "categoria_id='facturas_recibidas'" in sql
    assert "Empleado" in params
    assert "2026-09-26" in params
    assert any(
        "UPDATE facturas_recibidas_docs" in statement
        and "estado_contable='contabilizada_manual'" in statement
        for statement, _params in connection.calls
    )
    assert any(
        "UPDATE documentos_ocr SET estado='contabilizada'" in statement
        for statement, _params in connection.calls
    )
    assert connection.commits == 1


def test_estado_manual_con_asiento_no_se_convierte_en_ocr_suenlace():
    assert estado_efectivo(
        estado="contabilizada_manual", numero_asiento="05/00042",
    ) == "contabilizada_manual"


def test_devolver_a_pendientes_limpia_datos_contables():
    connection = _Connection()
    gestor = _gestor_with_connection(connection)

    gestor.cambiar_estado_contable_documentos(["doc-1"], "pendiente")

    sql, _params = connection.calls[0]
    assert "estado_contable='pendiente'" in sql
    assert "metodo_contabilizacion=NULL" in sql
    assert "numero_asiento=NULL" in sql
    assert "observaciones_contables=NULL" in sql


def test_asiento_capturado_actualiza_archivo_y_proyeccion_ocr():
    connection = _Connection()
    gestor = _gestor_with_connection(connection)
    gestor.get_documento_archivo = lambda _document_id: {
        "id": "archive-1", "categoria_id": "facturas_recibidas",
        "codigo_empresa": "E00001", "ocr_documento_id": "ocr-1",
    }

    changed = gestor.actualizar_asiento_documento_archivo(
        "archive-1", "05/00042",
    )

    statements = [sql for sql, _params in connection.calls]
    assert changed is True
    assert "estado_contable='contabilizada'" in statements[0]
    assert "metodo_contabilizacion='ocr_suenlace'" in statements[0]
    assert "UPDATE facturas_recibidas_docs" in statements[1]
    assert "UPDATE asientos_contables" in statements[2]
    assert all("05/00042" in params for _sql, params in connection.calls)
    assert connection.commits == 1


def test_captura_desde_ocr_actualiza_la_fuente_documental():
    connection = _Connection()
    gestor = _gestor_with_connection(connection)

    changed = gestor.actualizar_numero_asiento_factura_recibida(
        "E00001", "ocr-1", "05/00042",
    )

    statements = [sql for sql, _params in connection.calls]
    assert changed is True
    assert "estado_contable='contabilizada'" in statements[0]
    assert any("UPDATE documentos_archivo" in sql for sql in statements)
    assert any("ocr_documento_id" in sql for sql in statements)


def test_generar_suenlace_deja_la_factura_exportada_hasta_tener_asiento():
    class Gestor:
        def __init__(self):
            self.saved = None

        def upsert_factura_recibida_doc(self, payload):
            self.saved = dict(payload)

        def get_documento_ocr(self, _document_id):
            return None

        def get_asiento_contable_por_documento(self, _document_id):
            return None

    gestor = Gestor()
    mark_docs_as_generated(gestor, [{
        "id": "ocr-1", "estado_contable": "pendiente_contabilizar",
        "numero_asiento": "",
    }])

    assert gestor.saved["generada"] is True
    assert gestor.saved["estado_contable"] == "exportada_a3"


class _GestorService:
    def __init__(self, documents):
        self.documents = documents
        self.printed = []
        self.state_changes = []
        self.captured_entries = []

    def get_documento_archivo(self, document_id):
        return self.documents.get(document_id)

    def registrar_impresion_documentos(self, document_ids, usuario):
        self.printed.append((list(document_ids), usuario))
        return len(document_ids)

    def cambiar_estado_contable_documentos(self, ids, state, **kwargs):
        self.state_changes.append((list(ids), state, kwargs))
        return len(ids)

    def get_factura_recibida_archivo_para_captura(self, document_id):
        return self.documents.get(document_id)

    def actualizar_asiento_documento_archivo(self, document_id, entry_number):
        self.captured_entries.append((document_id, entry_number))
        return True


def test_impresion_multiple_registra_solo_archivos_enviados(tmp_path):
    first = tmp_path / "factura-1.pdf"
    second = tmp_path / "factura-2.pdf"
    first.write_bytes(b"%PDF-1")
    second.write_bytes(b"%PDF-2")
    gestor = _GestorService({
        "doc-1": {
            "id": "doc-1", "categoria_id": "facturas_recibidas",
            "ruta": str(first), "nombre_original": first.name,
        },
        "doc-2": {
            "id": "doc-2", "categoria_id": "facturas_recibidas",
            "ruta": str(second), "nombre_original": second.name,
        },
    })
    sent = []
    service = FacturasRecibidasPendientesService(
        gestor, imprimir_archivo=lambda path: sent.append(Path(path).name),
    )

    result = service.imprimir(["doc-1", "doc-2"], usuario="Empleado")

    assert sent == ["factura-1.pdf", "factura-2.pdf"]
    assert result.completados == ["factura-1.pdf", "factura-2.pdf"]
    assert result.errores == []
    assert gestor.printed == [(["doc-1", "doc-2"], "Empleado")]


def test_ocr_encola_y_omite_documentos_ya_analizados(monkeypatch, tmp_path):
    nueva = tmp_path / "nueva.pdf"
    nueva.write_bytes(b"%PDF-1")
    gestor = _GestorService({
        "new": {
            "id": "new", "categoria_id": "facturas_recibidas",
            "nombre_original": "nueva.pdf", "ocr_documento_id": None,
            "codigo_empresa": "E00001", "ejercicio": 2026,
            "ruta": str(nueva),
        },
        "old": {
            "id": "old", "categoria_id": "facturas_recibidas",
            "nombre_original": "anterior.pdf", "ocr_documento_id": "ocr-1",
        },
    })
    processed = []

    class _Cola:
        def __init__(self, _gestor):
            pass

        def encolar(self, **datos):
            processed.append(datos)
            return "job-1", True

    monkeypatch.setattr(
        "services.facturas_recibidas_pendientes_service.OcrBackgroundService",
        _Cola,
    )

    result = FacturasRecibidasPendientesService(gestor).enviar_a_ocr(
        ["new", "old"], usuario="Empleado",
    )

    assert processed == [{
        "empresa_id": "E00001", "ejercicio": 2026,
        "ruta_origen": str(nueva), "documento_archivo_id": "new",
        "usuario": "Empleado",
    }]
    assert result.completados == ["nueva.pdf"]
    assert result.omitidos == ["anterior.pdf"]


def test_captura_asientos_a3_para_varias_empresas():
    gestor = _GestorService({
        "doc-1": {
            "id": "doc-1", "categoria_id": "facturas_recibidas",
            "codigo_empresa": "E00123", "ejercicio": 2026,
            "nombre_original": "factura.pdf", "numero_factura_captura": "F-24",
            "descripcion_captura": "Su Fra Nº. F-24",
            "fecha_captura": "2026-05-15",
            "estado_contable": "exportada_a3",
        },
        "doc-2": {
            "id": "doc-2", "categoria_id": "facturas_recibidas",
            "codigo_empresa": "E00999", "ejercicio": 2025,
            "nombre_original": "sin-ocr.pdf", "numero_factura_captura": "",
        },
    })
    searches = []

    def find_entry(company, year, number, description, *, mes=None):
        searches.append((company, year, number, description, mes))
        return "05/00042"

    result = FacturasRecibidasPendientesService(
        gestor, buscar_asiento=find_entry,
    ).capturar_asientos(["doc-1", "doc-2"])

    assert searches == [("E00123", 2026, "F-24", "Su Fra Nº. F-24", 5)]
    assert gestor.captured_entries == [("doc-1", "05/00042")]
    assert result.completados == ["F-24 -> asiento 05/00042"]
    assert result.omitidos == ["sin-ocr.pdf: faltan datos OCR de la factura"]


def test_captura_asiento_manual_conserva_la_via_y_la_evidencia_de_a3():
    gestor = _GestorService({
        "doc-1": {
            "id": "doc-1", "categoria_id": "facturas_recibidas",
            "codigo_empresa": "E00123", "ejercicio": 2026,
            "nombre_original": "factura.pdf", "numero_factura_captura": "F-24",
            "descripcion_captura": "Su Fra Nº. F-24",
            "fecha_captura": "2026-05-15",
            "estado_contable": "pendiente",
        },
    })
    service = FacturasRecibidasPendientesService(
        gestor, buscar_asiento=lambda *_args, **_kwargs: "05/00042",
    )

    result = service.capturar_asientos(["doc-1"], usuario="Empleado")

    assert result.completados == ["F-24 -> asiento 05/00042"]
    assert gestor.captured_entries == []
    assert gestor.state_changes == [(
        ["doc-1"],
        "contabilizada_manual",
        {
            "usuario": "Empleado",
            "fecha_contable": "",
            "numero_asiento": "05/00042",
            "observaciones": "Asiento capturado automaticamente en A3ECO",
        },
    )]


def test_filtro_global_combina_estado_empresa_y_busqueda():
    rows = [
        {
            "id": "one", "codigo_empresa": "E00001", "ejercicio": 2026,
            "empresa_nombre": "Cliente Uno", "nombre_original": "Luz.pdf",
            "estado_contable": "pendiente",
        },
        {
            "id": "two", "codigo_empresa": "E00002", "ejercicio": 2026,
            "empresa_nombre": "Cliente Dos", "nombre_original": "Agua.pdf",
            "estado_contable": "contabilizada_manual",
        },
        {
            "id": "three", "codigo_empresa": "E00001", "ejercicio": 2026,
            "empresa_nombre": "Cliente Uno", "nombre_original": "Gas.pdf",
            "estado_contable": "contabilizada", "numero_factura_captura": "G-3",
        },
    ]

    filtered = UIFacturasRecibidasPendientes.filter_rows(
        rows,
        empresa="E00001 - Cliente Uno",
        estado="Pendientes",
        texto="luz",
    )

    assert [row["id"] for row in filtered] == ["one"]

    captured = UIFacturasRecibidasPendientes.filter_rows(
        rows, estado="Contabilizadas por OCR/SUENLACE", texto="G-3",
    )
    assert [row["id"] for row in captured] == ["three"]


def test_estado_distingue_exportacion_ocr_de_asiento_confirmado():
    exportada = {
        "ocr_documento_id": "ocr-1",
        "estado_documento_ocr": "contabilizada",
        "estado_contable": "pendiente",
        "metodo_contabilizacion": "",
    }

    assert UIFacturasRecibidasPendientes._ocr_state_label(exportada) == "Exportada para A3"
    assert UIFacturasRecibidasPendientes._accounting_state_label(
        exportada["estado_contable"],
        metodo=exportada["metodo_contabilizacion"],
        exportada_ocr=UIFacturasRecibidasPendientes._exportada_desde_ocr(exportada),
    ) == "OCR/SUENLACE · pendiente de asiento A3"
    assert UIFacturasRecibidasPendientes._accounting_state_label(
        "contabilizada", metodo="ocr_suenlace",
    ) == "OCR/SUENLACE · asiento confirmado en A3"
    assert UIFacturasRecibidasPendientes._accounting_state_label(
        "contabilizada_manual", metodo="manual_a3_papel",
    ) == "Manual en A3 (papel)"


def test_gestion_documental_muestra_via_de_contabilizacion():
    assert UIGestionDocumental._estado_documental_label({
        "estado_contable": "contabilizada_manual",
        "metodo_contabilizacion": "manual_a3_papel",
    }) == "Manual en A3 (papel)"
    assert UIGestionDocumental._estado_documental_label({
        "estado_contable": "contabilizada",
        "metodo_contabilizacion": "ocr_suenlace",
        "ocr_documento_id": "ocr-1",
    }) == "OCR/SUENLACE · asiento confirmado en A3"
