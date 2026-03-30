from __future__ import annotations

from services.auth_service import AuthorizationService


class SecuredGestorSQLite:
    """
    Proxy del gestor real para aplicar filtrado y comprobaciones de seguridad.
    """

    def __init__(self, base_gestor, authorization: AuthorizationService):
        self._base = base_gestor
        self.security = authorization

    def __getattr__(self, item):
        return getattr(self._base, item)

    @property
    def db_path(self):
        return self._base.db_path

    @property
    def conn(self):
        return self._base.conn

    def listar_empresas(self):
        rows = self._base.listar_empresas()
        if self.security.session.is_admin():
            return rows
        return [row for row in rows if self.security.can_read_company(str(row.get("codigo") or ""))]

    def get_empresa(self, codigo: str, ejercicio: int | None = None):
        self.security.ensure_company_read(codigo)
        return self._base.get_empresa(codigo, ejercicio)

    def listar_bancos(self, codigo_empresa: str, ejercicio: int):
        self.security.ensure_company_read(codigo_empresa)
        return self._base.listar_bancos(codigo_empresa, ejercicio)

    def listar_emitidas(self, codigo_empresa: str, ejercicio: int):
        self.security.ensure_company_read(codigo_empresa)
        return self._base.listar_emitidas(codigo_empresa, ejercicio)

    def listar_recibidas(self, codigo_empresa: str, ejercicio: int):
        self.security.ensure_company_read(codigo_empresa)
        return self._base.listar_recibidas(codigo_empresa, ejercicio)

    def listar_facturas_emitidas(self, codigo_empresa: str, ejercicio: int):
        self.security.ensure_company_read(codigo_empresa)
        return self._base.listar_facturas_emitidas(codigo_empresa, ejercicio)

    def listar_facturas_emitidas_global(self, codigo_empresa: str, ejercicio: int | None = None, tercero_id: str | None = None):
        self.security.ensure_company_read(codigo_empresa)
        return self._base.listar_facturas_emitidas_global(codigo_empresa, ejercicio, tercero_id)

    def listar_facturas_emitidas_todas(self, codigo_empresa: str | None = None, ejercicio: int | None = None, tercero_id: str | None = None):
        if codigo_empresa:
            self.security.ensure_company_read(codigo_empresa)
            return self._base.listar_facturas_emitidas_todas(codigo_empresa, ejercicio, tercero_id)
        rows = self._base.listar_facturas_emitidas_todas(codigo_empresa, ejercicio, tercero_id)
        if self.security.session.is_admin():
            return rows
        return [row for row in rows if self.security.can_read_company(str(row.get("codigo_empresa") or ""))]

    def listar_ejercicios_facturas_emitidas(self, codigo_empresa: str):
        self.security.ensure_company_read(codigo_empresa)
        return self._base.listar_ejercicios_facturas_emitidas(codigo_empresa)

    def listar_clientes_facturas_emitidas(self, codigo_empresa: str, ejercicio: int | None = None):
        self.security.ensure_company_read(codigo_empresa)
        return self._base.listar_clientes_facturas_emitidas(codigo_empresa, ejercicio)

    def listar_albaranes_emitidas(self, codigo_empresa: str, ejercicio: int):
        self.security.ensure_company_read(codigo_empresa)
        return self._base.listar_albaranes_emitidas(codigo_empresa, ejercicio)

    def listar_terceros_empresa(self, codigo_empresa: str, ejercicio: int):
        self.security.ensure_company_read(codigo_empresa)
        return self._base.listar_terceros_empresa(codigo_empresa, ejercicio)

    def listar_terceros_por_empresa(self, codigo_empresa: str, ejercicio: int):
        self.security.ensure_company_read(codigo_empresa)
        return self._base.listar_terceros_por_empresa(codigo_empresa, ejercicio)

    def get_tercero_empresa(self, codigo_empresa: str, tercero_id: str, ejercicio: int):
        self.security.ensure_company_read(codigo_empresa)
        return self._base.get_tercero_empresa(codigo_empresa, tercero_id, ejercicio)

    def upsert_banco(self, plantilla):
        self.security.ensure_company_write(plantilla.get("codigo_empresa"))
        return self._base.upsert_banco(plantilla)

    def eliminar_banco(self, codigo_empresa: str, banco: str, ejercicio: int):
        self.security.ensure_company_write(codigo_empresa)
        return self._base.eliminar_banco(codigo_empresa, banco, ejercicio)

    def upsert_emitida(self, plantilla):
        self.security.ensure_company_write(plantilla.get("codigo_empresa"))
        return self._base.upsert_emitida(plantilla)

    def eliminar_emitida(self, codigo_empresa: str, nombre: str, ejercicio: int):
        self.security.ensure_company_write(codigo_empresa)
        return self._base.eliminar_emitida(codigo_empresa, nombre, ejercicio)

    def upsert_recibida(self, plantilla):
        self.security.ensure_company_write(plantilla.get("codigo_empresa"))
        return self._base.upsert_recibida(plantilla)

    def eliminar_recibida(self, codigo_empresa: str, nombre: str, ejercicio: int):
        self.security.ensure_company_write(codigo_empresa)
        return self._base.eliminar_recibida(codigo_empresa, nombre, ejercicio)

    def upsert_factura_emitida(self, factura: dict):
        self.security.ensure_company_write(factura.get("codigo_empresa"))
        return self._base.upsert_factura_emitida(factura)

    def eliminar_factura_emitida(self, codigo_empresa: str, factura_id: str, ejercicio: int):
        self.security.ensure_company_write(codigo_empresa)
        return self._base.eliminar_factura_emitida(codigo_empresa, factura_id, ejercicio)

    def marcar_facturas_emitidas_generadas(self, codigo_empresa: str, ids: list, fecha: str, ejercicio: int):
        self.security.ensure_company_write(codigo_empresa)
        return self._base.marcar_facturas_emitidas_generadas(codigo_empresa, ids, fecha, ejercicio)

    def desmarcar_facturas_emitidas_generadas(self, codigo_empresa: str, ids: list, ejercicio: int):
        self.security.ensure_company_write(codigo_empresa)
        return self._base.desmarcar_facturas_emitidas_generadas(codigo_empresa, ids, ejercicio)

    def marcar_factura_emitida_enviada(self, codigo_empresa: str, factura_id: str, fecha: str, canal: str | None, ejercicio: int):
        self.security.ensure_company_write(codigo_empresa)
        return self._base.marcar_factura_emitida_enviada(codigo_empresa, factura_id, fecha, canal, ejercicio)

    def upsert_albaran_emitida(self, albaran: dict):
        self.security.ensure_company_write(albaran.get("codigo_empresa"))
        return self._base.upsert_albaran_emitida(albaran)

    def eliminar_albaran_emitida(self, codigo_empresa: str, albaran_id: str, ejercicio: int):
        self.security.ensure_company_write(codigo_empresa)
        return self._base.eliminar_albaran_emitida(codigo_empresa, albaran_id, ejercicio)

    def marcar_albaranes_facturados(self, codigo_empresa: str, ids: list, factura_id: str, fecha: str, ejercicio: int):
        self.security.ensure_company_write(codigo_empresa)
        return self._base.marcar_albaranes_facturados(codigo_empresa, ids, factura_id, fecha, ejercicio)

    def upsert_tercero_empresa(self, rel: dict):
        self.security.ensure_company_write(rel.get("codigo_empresa"))
        return self._base.upsert_tercero_empresa(rel)

    def eliminar_tercero_empresa(self, codigo_empresa: str, tercero_id: str):
        self.security.ensure_company_write(codigo_empresa)
        return self._base.eliminar_tercero_empresa(codigo_empresa, tercero_id)

    def upsert_empresa(self, emp: dict):
        codigo = str(emp.get("codigo") or "")
        if not self.security.can_manage_company_catalog():
            raise PermissionError("Solo administradores y empleados pueden gestionar empresas.")
        if codigo and not self.security.can_manage_companies():
            existente = self._base.get_empresa(codigo, emp.get("ejercicio"))
            if existente:
                self.security.ensure_company_write(codigo)
        return self._base.upsert_empresa(emp)

    def copiar_empresa(self, codigo_origen: str, ejercicio_origen: int, nueva_empresa: dict):
        self.security.ensure_admin("Solo el administrador puede copiar empresas.")
        return self._base.copiar_empresa(codigo_origen, ejercicio_origen, nueva_empresa)

    def eliminar_empresa(self, codigo: str, ejercicio: int):
        self.security.ensure_admin("Solo el administrador puede eliminar empresas.")
        return self._base.eliminar_empresa(codigo, ejercicio)

    def listar_usuarios(self):
        self.security.ensure_admin("Solo el administrador puede gestionar usuarios.")
        return self._base.listar_usuarios()

    def get_usuario(self, user_id: int):
        self.security.ensure_admin("Solo el administrador puede gestionar usuarios.")
        return self._base.get_usuario(user_id)

    def get_usuario_by_username(self, username: str):
        self.security.ensure_admin("Solo el administrador puede gestionar usuarios.")
        return self._base.get_usuario_by_username(username)

    def listar_permisos_usuario(self, user_id: int):
        self.security.ensure_admin("Solo el administrador puede gestionar usuarios.")
        return self._base.listar_permisos_usuario(user_id)

    def upsert_usuario(self, usuario: dict):
        self.security.ensure_admin("Solo el administrador puede gestionar usuarios.")
        return self._base.upsert_usuario(usuario)

    def reemplazar_permisos_usuario(self, user_id: int, permisos: dict[str, str]):
        self.security.ensure_admin("Solo el administrador puede gestionar usuarios.")
        return self._base.reemplazar_permisos_usuario(user_id, permisos)

    def actualizar_password_usuario(self, user_id: int, password_hash: str, *, must_change_password: bool = False):
        self.security.ensure_admin("Solo el administrador puede gestionar usuarios.")
        return self._base.actualizar_password_usuario(user_id, password_hash, must_change_password=must_change_password)
