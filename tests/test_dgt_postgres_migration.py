from models.gestor_postgres import FilaPostgres, GestorPostgres


class _Resultado:
    def __init__(self, *, one=None, rows=None):
        self._one = one
        self._rows = rows or []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._rows


class _Conexion:
    def __init__(self):
        self.sentencias = []
        self.commits = 0

    def execute(self, sql, _params=None):
        self.sentencias.append(sql)
        if "information_schema.columns" in sql:
            columnas = (
                "cuenta_bancaria", "cuentas_bancarias", "pdf_ref_seq",
                "serie_emitidas_rect", "siguiente_num_emitidas_rect",
                "logo_max_width_mm", "logo_max_height_mm", "pais", "naf",
                "responsable", "activo",
            )
            rows = [FilaPostgres(table_name="empresas", column_name=col) for col in columnas]
            rows.append(FilaPostgres(table_name="usuarios", column_name="must_change_password"))
            return _Resultado(rows=rows)
        if "tabla_permisos" in sql:
            return _Resultado(one=FilaPostgres(
                tabla_permisos="usuarios_permisos_globales",
                indice_permisos="idx_usuarios_permisos_globales_usuario",
                tabla_dgt_facturas=None,
                indice_dgt_facturas=None,
                tabla_avisos_correo="comunicaciones_avisos_estado",
                tabla_avisos_vistos="comunicaciones_avisos_vistos",
                tabla_categorias_documentales="categorias_documentales",
                tabla_documentos_archivo="documentos_archivo",
                tabla_decisiones_adjuntos="comunicaciones_adjuntos_decisiones",
            ))
        return _Resultado()

    def commit(self):
        self.commits += 1


def test_migracion_postgres_crea_tabla_de_facturas_dgt_si_falta():
    gestor = GestorPostgres.__new__(GestorPostgres)
    gestor.conn = _Conexion()

    gestor._aplicar_migraciones_esenciales_postgres()

    ddl = "\n".join(gestor.conn.sentencias)
    assert "CREATE TABLE IF NOT EXISTS dgt_facturas" in ddl
    assert "CREATE INDEX IF NOT EXISTS idx_dgt_facturas_factura" in ddl
    assert gestor.conn.commits == 1
