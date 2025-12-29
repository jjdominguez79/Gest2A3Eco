from models.facturas_common import render_a3_tipoC_alta_cuenta
from utils.utilidades import validar_subcuenta_longitud


class TercerosEmpresaController:
    def __init__(self, gestor, codigo, ejercicio, ndig, view):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._ndig = ndig
        self._view = view

    def refresh(self):
        self._view.set_terceros(self._gestor.listar_terceros_por_empresa(self._codigo, self._ejercicio))
        self._view.clear_subcuentas()

    def load_subcuentas(self):
        tid = self._view.get_selected_id()
        if not tid:
            self._view.set_subcuentas("", "", "", "")
            return
        rel = self._gestor.get_tercero_empresa(self._codigo, tid, self._ejercicio) or {}
        self._view.set_subcuentas(
            rel.get("subcuenta_cliente", ""),
            rel.get("subcuenta_proveedor", ""),
            rel.get("subcuenta_ingreso", ""),
            rel.get("subcuenta_gasto", ""),
        )

    def guardar_subcuentas(self):
        tid = self._view.get_selected_id()
        if not tid:
            self._view.show_info("Gest2A3Eco", "Selecciona un tercero.")
            return
        sc = self._view.get_subcuenta_cliente().strip()
        sp = self._view.get_subcuenta_proveedor().strip()
        si = self._view.get_subcuenta_ingreso().strip()
        sg = self._view.get_subcuenta_gasto().strip()
        try:
            if sc:
                validar_subcuenta_longitud(sc, self._ndig, "subcuenta cliente")
            if sp:
                validar_subcuenta_longitud(sp, self._ndig, "subcuenta proveedor")
            if si:
                validar_subcuenta_longitud(si, self._ndig, "subcuenta ingreso")
            if sg:
                validar_subcuenta_longitud(sg, self._ndig, "subcuenta gasto")
        except Exception as e:
            self._view.show_error("Gest2A3Eco", str(e))
            return
        if self._subcuenta_en_uso(sc, tid, "subcuenta_cliente"):
            self._view.show_error("Gest2A3Eco", f"La subcuenta cliente {sc} ya esta asignada en esta empresa.")
            return
        if self._subcuenta_en_uso(sp, tid, "subcuenta_proveedor"):
            self._view.show_error("Gest2A3Eco", f"La subcuenta proveedor {sp} ya esta asignada en esta empresa.")
            return
        rel = {
            "tercero_id": tid,
            "codigo_empresa": self._codigo,
            "ejercicio": self._ejercicio,
            "subcuenta_cliente": sc,
            "subcuenta_proveedor": sp,
            "subcuenta_ingreso": si,
            "subcuenta_gasto": sg,
        }
        self._gestor.upsert_tercero_empresa(rel)
        self._view.show_info("Gest2A3Eco", "Subcuentas guardadas.")

    def copiar_desde_ejercicio(self):
        ejercicios = [e for e in self._gestor.listar_ejercicios_empresa(self._codigo) if e != self._ejercicio]
        if not ejercicios:
            self._view.show_info("Gest2A3Eco", "No hay otros ejercicios disponibles para copiar.")
            return
        origen = self._view.ask_copiar_ejercicio(ejercicios)
        if origen is None:
            return
        copiados, omitidos = self._gestor.copiar_terceros_empresa(self._codigo, origen, self._ejercicio)
        self.refresh()
        if omitidos:
            self._view.show_info(
                "Gest2A3Eco",
                f"Copiados {copiados} terceros desde {origen}. Omitidos {omitidos} ya existentes.",
            )
        else:
            self._view.show_info("Gest2A3Eco", f"Copiados {copiados} terceros desde {origen}.")

    def generar_suenlace_terceros(self):
        empresa = self._gestor.get_empresa(self._codigo, self._ejercicio) or {}
        ndig = int(empresa.get("digitos_plan", 8))
        terceros = self._gestor.listar_terceros_por_empresa(self._codigo, self._ejercicio)
        if not terceros:
            self._view.show_info("Gest2A3Eco", "No hay terceros asignados a esta empresa.")
            return
        registros = []
        cuentas_usadas = set()
        fecha_alta = f"{int(self._ejercicio):04d}0101"
        for t in terceros:
            nif = str(t.get("nif") or "").strip().upper()
            nombre = str(t.get("nombre") or "").strip()
            base_kwargs = {
                "codigo_empresa": str(self._codigo),
                "fecha_alta": fecha_alta,
                "ndig_plan": ndig,
                "nombre": nombre,
                "nif": nif,
                "via": str(t.get("direccion") or "").strip(),
                "municipio": str(t.get("poblacion") or "").strip(),
                "cp": str(t.get("cp") or "").strip(),
                "provincia": str(t.get("provincia") or "").strip(),
                "pais": "011",
                "telefono": str(t.get("telefono") or "").strip(),
                "email": str(t.get("email") or "").strip(),
                "tipo_documento": "02",
                "actualizar_saldo": "N",
                "saldo_inicial": 0.0,
                "ampliacion": " ",
            }
            sub_cli = str(t.get("subcuenta_cliente") or "").strip()
            if sub_cli and sub_cli not in cuentas_usadas:
                registros.append(
                    render_a3_tipoC_alta_cuenta(
                        cuenta=sub_cli,
                        cuenta_contrapartida=str(t.get("subcuenta_ingreso") or "").strip(),
                        **base_kwargs,
                    )
                )
                registros.append(registros[-1])
                cuentas_usadas.add(sub_cli)
            sub_pro = str(t.get("subcuenta_proveedor") or "").strip()
            if sub_pro and sub_pro not in cuentas_usadas:
                registros.append(
                    render_a3_tipoC_alta_cuenta(
                        cuenta=sub_pro,
                        cuenta_contrapartida=str(t.get("subcuenta_gasto") or "").strip(),
                        **base_kwargs,
                    )
                )
                registros.append(registros[-1])
                cuentas_usadas.add(sub_pro)
        if not registros:
            self._view.show_info("Gest2A3Eco", "No hay subcuentas para generar.")
            return
        save_path = self._view.ask_save_dat_path(f"E{self._codigo}_.dat")
        if not save_path:
            return
        with open(save_path, "w", encoding="latin-1", newline="") as f:
            f.writelines(registros)
        self._view.show_info("Gest2A3Eco", f"Fichero generado:\n{save_path}")

    def _subcuenta_en_uso(self, subcuenta: str, tercero_id: str, field: str) -> bool:
        if not subcuenta:
            return False
        for rel in self._gestor.listar_terceros_empresa(self._codigo, self._ejercicio):
            if str(rel.get("tercero_id")) == str(tercero_id):
                continue
            if str(rel.get(field) or "").strip() == subcuenta:
                return True
        return False
