from pathlib import Path

import pytest

from models.gestor_base import GestorBase
from services.gestion_documental_service import GestionDocumentalService


class _GestorServicio:
    def __init__(self, documento):
        self.documento = dict(documento)
        self.cambio = None

    def get_documento_archivo(self, _documento_id):
        return dict(self.documento)

    def listar_categorias_documentales(self):
        return [
            {
                "id": "facturas_recibidas", "nombre": "Facturas recibidas",
                "carpeta": "FACTURAS_RECIBIDAS", "permite_ocr": 1,
            },
            {
                "id": "fiscal", "nombre": "Fiscal",
                "carpeta": "FISCAL", "permite_ocr": 0,
            },
        ]

    def reclasificar_documento_archivo(
        self, documento_id, categoria_id, *, ruta, nombre_archivo,
    ):
        self.cambio = (documento_id, categoria_id, ruta, nombre_archivo)
        return True


def test_reclasificar_documento_mueve_archivo_y_actualiza_categoria(
    tmp_path, monkeypatch,
):
    origen = tmp_path / "Facturas_recibidas" / "factura.pdf"
    origen.parent.mkdir()
    origen.write_bytes(b"%PDF")
    gestor = _GestorServicio({
        "id": "doc-1", "codigo_empresa": "E00001", "ejercicio": 2026,
        "categoria_id": "facturas_recibidas", "ruta": str(origen),
        "nombre_original": "factura.pdf", "nombre_archivo": "factura.pdf",
    })
    service = GestionDocumentalService(gestor, graph=object())
    monkeypatch.setattr(
        service, "_category_directory",
        lambda *_args: tmp_path / "Fiscal",
    )

    changed = service.reclasificar_documento("doc-1", "fiscal", usuario="Empleado")

    assert changed is True
    destino = Path(gestor.cambio[2])
    assert gestor.cambio[:2] == ("doc-1", "fiscal")
    assert destino.parent == tmp_path / "Fiscal"
    assert destino.read_bytes() == b"%PDF"
    assert not origen.exists()


def test_reclasificar_restaura_archivo_si_falla_la_base_de_datos(
    tmp_path, monkeypatch,
):
    origen = tmp_path / "Facturas_recibidas" / "factura.pdf"
    origen.parent.mkdir()
    origen.write_bytes(b"%PDF")
    gestor = _GestorServicio({
        "id": "doc-1", "codigo_empresa": "E00001", "ejercicio": 2026,
        "categoria_id": "facturas_recibidas", "ruta": str(origen),
        "nombre_original": "factura.pdf", "nombre_archivo": "factura.pdf",
    })
    gestor.reclasificar_documento_archivo = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("fallo PostgreSQL")
    )
    service = GestionDocumentalService(gestor, graph=object())
    monkeypatch.setattr(
        service, "_category_directory",
        lambda *_args: tmp_path / "Fiscal",
    )

    with pytest.raises(RuntimeError, match="fallo PostgreSQL"):
        service.reclasificar_documento("doc-1", "fiscal")

    assert origen.read_bytes() == b"%PDF"
    assert not (tmp_path / "Fiscal" / "factura.pdf").exists()


class _Result:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class _Conn:
    def __init__(self, categoria, *, procesando=None, proyeccion=None):
        self.categoria = categoria
        self.procesando = procesando
        self.proyeccion = proyeccion
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "FROM categorias_documentales" in sql:
            return _Result(self.categoria)
        if "estado='procesando'" in sql:
            return _Result(self.procesando)
        if "FROM facturas_recibidas_docs" in sql:
            return _Result(self.proyeccion)
        return _Result()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_reclasificacion_bloquea_factura_con_asiento():
    gestor = object.__new__(GestorBase)
    gestor.conn = _Conn({"id": "fiscal", "permite_ocr": 0})
    gestor.get_documento_archivo = lambda _documento_id: {
        "id": "doc-1", "categoria_id": "facturas_recibidas",
        "permite_ocr": 1, "numero_asiento": "05/00042",
        "estado_contable": "contabilizada",
    }

    with pytest.raises(ValueError, match="exportada o contabilizada"):
        gestor.reclasificar_documento_archivo(
            "doc-1", "fiscal", ruta="fiscal/factura.pdf",
            nombre_archivo="factura.pdf",
        )


def test_reclasificacion_pendiente_cancela_ocr_y_actualiza_documento():
    gestor = object.__new__(GestorBase)
    gestor.conn = _Conn({"id": "fiscal", "permite_ocr": 0})
    gestor.get_documento_archivo = lambda _documento_id: {
        "id": "doc-1", "categoria_id": "facturas_recibidas",
        "permite_ocr": 1, "ocr_documento_id": "ocr-1",
        "numero_asiento": "", "estado_contable": "pendiente",
    }

    changed = gestor.reclasificar_documento_archivo(
        "doc-1", "fiscal", ruta="fiscal/factura.pdf",
        nombre_archivo="factura.pdf",
    )

    assert changed is True
    statements = [sql for sql, _params in gestor.conn.calls]
    assert any("SET estado='cancelado'" in sql for sql in statements)
    assert any("DELETE FROM documentos_ocr" in sql for sql in statements)
    assert any(
        "UPDATE documentos_archivo SET categoria_id" in sql for sql in statements
    )
