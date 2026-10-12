from models.gestor_base import GestorBase


class _ConexionGrabadora:
    def __init__(self, *, fallar_borrado=False, bloquear_borrado=False):
        self.operaciones = []
        self.commits = 0
        self.rollbacks = 0
        self.fallar_borrado = fallar_borrado
        self.bloquear_borrado = bloquear_borrado
        self.rowcount = 1

    def execute(self, sql, params):
        sql_normalizado = " ".join(sql.split())
        self.operaciones.append((sql_normalizado, params))
        if self.fallar_borrado and sql_normalizado.startswith("DELETE FROM facturas_emitidas_docs"):
            raise RuntimeError("fallo simulado")
        self.rowcount = (
            0
            if self.bloquear_borrado
            and sql_normalizado.startswith("DELETE FROM facturas_emitidas_docs")
            else 1
        )
        return self

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_eliminar_factura_libera_primero_sus_albaranes():
    gestor = GestorBase.__new__(GestorBase)
    gestor.conn = _ConexionGrabadora()

    gestor.eliminar_factura_emitida("E00701", "fac-58", 2026)

    assert gestor.conn.operaciones == [
        (
            "UPDATE albaranes_emitidas_docs SET facturado=0, factura_id=NULL, "
            "fecha_facturacion=NULL WHERE codigo_empresa=? AND ejercicio=? AND factura_id=?",
            ("E00701", 2026, "fac-58"),
        ),
        (
            "DELETE FROM facturas_emitidas_docs WHERE codigo_empresa=? AND ejercicio=? AND id=? "
            "AND COALESCE(estado_contable,'') NOT IN ('pendiente','generado','contabilizada') "
            "AND COALESCE(TRIM(numero_asiento),'')='' AND COALESCE(generada,0)=0",
            ("E00701", 2026, "fac-58"),
        ),
    ]
    assert gestor.conn.commits == 1
    assert gestor.conn.rollbacks == 0


def test_eliminar_factura_revierte_la_liberacion_si_falla_el_borrado():
    gestor = GestorBase.__new__(GestorBase)
    gestor.conn = _ConexionGrabadora(fallar_borrado=True)

    try:
        gestor.eliminar_factura_emitida("E00701", "fac-58", 2026)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Se esperaba el fallo simulado")

    assert gestor.conn.commits == 0
    assert gestor.conn.rollbacks == 1


def test_eliminar_factura_bloqueada_no_desvincula_albaranes_ni_confirma():
    gestor = GestorBase.__new__(GestorBase)
    gestor.conn = _ConexionGrabadora(bloquear_borrado=True)

    try:
        gestor.eliminar_factura_emitida("E00701", "fac-contabilizada", 2026)
    except ValueError as exc:
        assert "bloqueada" in str(exc)
    else:
        raise AssertionError("Se esperaba el bloqueo de la factura contabilizada")

    assert gestor.conn.commits == 0
    assert gestor.conn.rollbacks == 1
