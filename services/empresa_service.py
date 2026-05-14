from __future__ import annotations

from datetime import datetime


class EmpresaService:
    def __init__(self, gestor):
        self._gestor = gestor

    def listar_empresas_panel(self, query: str = "", include_inactive: bool = False) -> list[dict]:
        grouped = {}
        for row in self._gestor.listar_empresas():
            codigo = str(row.get("codigo") or "").strip()
            if not codigo:
                continue
            grouped.setdefault(codigo, []).append(dict(row))

        filtro = str(query or "").strip().lower()
        out = []
        for codigo, items in grouped.items():
            ejercicios = sorted(
                {self._as_int(item.get("ejercicio")) for item in items if self._as_int(item.get("ejercicio")) is not None}
            )
            preferred = self._pick_preferred_row(items)
            permiso = self._company_permission_label(codigo)
            estado = self._estado_configuracion(preferred)
            item = {
                "codigo": codigo,
                "nombre": str(preferred.get("nombre") or ""),
                "cif": str(preferred.get("cif") or ""),
                "ejercicio": preferred.get("ejercicio"),
                "ultimo_ejercicio": preferred.get("ejercicio"),
                "digitos_plan": int(preferred.get("digitos_plan") or 8),
                "activo": any(bool(x.get("activo", True)) for x in items),
                "ejercicios": ejercicios,
                "ejercicios_txt": ", ".join(str(x) for x in ejercicios),
                "permiso": permiso,
                "estado_configuracion": estado,
            }
            if not include_inactive and not item["activo"]:
                continue
            text = " ".join(
                [
                    item["codigo"],
                    item["nombre"],
                    item["cif"],
                    item["ejercicios_txt"],
                ]
            ).lower()
            if filtro and filtro not in text:
                continue
            out.append(item)
        out.sort(key=lambda row: (str(row.get("nombre") or "").lower(), str(row.get("codigo") or "")))
        return out

    def get_dashboard_context(self, codigo: str, ejercicio: int) -> dict:
        empresa = self._gestor.get_empresa(codigo, ejercicio) or {}
        ejercicios = []
        try:
            ejercicios = self._gestor.listar_ejercicios_empresa(codigo)
        except Exception:
            ejercicios = [ejercicio]
        emitidas = self._safe_list(lambda: self._gestor.listar_facturas_emitidas(codigo, ejercicio))
        bancos = self._safe_list(lambda: self._gestor.listar_bancos(codigo, ejercicio))
        plantillas_emitidas = self._safe_list(lambda: self._gestor.listar_emitidas(codigo, ejercicio))
        plantillas_recibidas = self._safe_list(lambda: self._gestor.listar_recibidas(codigo, ejercicio))
        recibidas_docs = self._safe_list(lambda: self._gestor.listar_facturas_recibidas_docs(codigo, ejercicio))
        terceros = self._safe_list(lambda: self._gestor.listar_terceros_por_empresa(codigo, ejercicio))
        plan_cuentas = self._safe_list(lambda: self._gestor.get_plan_cuentas(codigo, 0))
        cuentas_bancarias_struct = self._safe_list(lambda: self._gestor.listar_cuentas_bancarias(codigo, 0))
        if not plan_cuentas:
            plan_cuentas = self._safe_list(lambda: self._gestor.get_plan_cuentas(codigo, ejercicio))
        if not cuentas_bancarias_struct:
            cuentas_bancarias_struct = self._safe_list(lambda: self._gestor.listar_cuentas_bancarias(codigo, ejercicio))

        total_facturas = len(emitidas)
        generadas = sum(1 for fac in emitidas if fac.get("generada"))
        enviadas = sum(1 for fac in emitidas if fac.get("enviado"))
        borradores = sum(1 for fac in emitidas if fac.get("borrador"))
        cuentas_bancarias = []
        if cuentas_bancarias_struct:
            for item in cuentas_bancarias_struct:
                text = str(item.get("iban") or item.get("descripcion") or "").strip()
                if text:
                    cuentas_bancarias.append(text)
        else:
            cuentas_bancarias = self._split_multiline(empresa.get("cuentas_bancarias") or empresa.get("cuenta_bancaria") or "")

        checks = {
            "empresa": bool(empresa.get("nombre")) and bool(empresa.get("cif")),
            "bancos": bool(cuentas_bancarias),
            "plan": bool(plan_cuentas),
            "facturacion": bool(plantillas_emitidas),
            "importaciones": bool(bancos or plantillas_recibidas),
        }
        completados = sum(1 for ok in checks.values() if ok)
        if completados == len(checks):
            estado_config = "Completa"
        elif completados >= 3:
            estado_config = "Parcial"
        else:
            estado_config = "Inicial"

        ultimos_procesos = []
        for fac in emitidas:
            estado = "BORRADOR"
            if fac.get("enviado"):
                estado = "ENVIADA"
            elif fac.get("generada"):
                estado = "GENERADA"
            ultimos_procesos.append(
                {
                    "fecha": fac.get("fecha_envio") or fac.get("fecha_generacion") or fac.get("fecha_asiento") or "",
                    "descripcion": f"Factura {fac.get('serie', '')}{fac.get('numero', '')} - {fac.get('nombre', '')}".strip(" -"),
                    "estado": estado,
                }
            )
        for doc in recibidas_docs:
            ultimos_procesos.append(
                {
                    "fecha": doc.get("fecha_generacion") or doc.get("updated_at") or doc.get("fecha_asiento") or "",
                    "descripcion": f"OCR recibida {doc.get('numero_factura', '')} - {doc.get('proveedor_nombre', '')}".strip(" -"),
                    "estado": doc.get("estado_contable") or doc.get("estado_validacion") or doc.get("estado_ocr") or "PENDIENTE",
                }
            )
        ultimos_procesos.sort(key=lambda item: self._sort_datetime(item.get("fecha")), reverse=True)
        ultimos_procesos = ultimos_procesos[:8]

        avisos = []
        if not checks["plan"]:
            avisos.append("Plan contable no importado desde A3.")
        if not checks["bancos"]:
            avisos.append("No hay cuentas bancarias configuradas.")
        if not checks["facturacion"]:
            avisos.append("No hay plantillas de facturas emitidas.")
        if not checks["importaciones"]:
            avisos.append("No hay plantillas de importacion para Excel.")
        if not avisos:
            avisos.append("Sin avisos pendientes.")

        return {
            "empresa": empresa,
            "ejercicios": ejercicios,
            "permiso": self._company_permission_label(codigo),
            "can_write": self._can_write_company(codigo),
            "resumen_facturacion": {
                "total": total_facturas,
                "borrador": borradores,
                "generadas": generadas,
                "enviadas": enviadas,
            },
            "resumen_ocr": {
                "total": len(recibidas_docs),
                "pendientes": sum(1 for doc in recibidas_docs if (doc.get("estado_validacion") or "") != "validada"),
                "validadas": sum(1 for doc in recibidas_docs if (doc.get("estado_validacion") or "") == "validada"),
                "estado": "Activo" if recibidas_docs else "Sin documentos",
            },
            "resumen_contabilidad": {
                "plantillas_bancos": len(bancos),
                "plantillas_emitidas": len(plantillas_emitidas),
                "plantillas_recibidas": len(plantillas_recibidas),
                "plan_cuentas": len(plan_cuentas),
            },
            "estado_configuracion": estado_config,
            "terceros_count": len(terceros),
            "cuentas_bancarias": cuentas_bancarias,
            "ultimos_procesos": ultimos_procesos,
            "avisos": avisos,
        }

    def _safe_list(self, fn):
        try:
            return list(fn() or [])
        except Exception:
            return []

    def _pick_preferred_row(self, items: list[dict]) -> dict:
        preferred = None
        best_ej = None
        for item in items:
            eje = self._as_int(item.get("ejercicio"))
            if preferred is None or (eje is not None and (best_ej is None or eje > best_ej)):
                preferred = item
                best_ej = eje
        return preferred or {}

    def _estado_configuracion(self, empresa: dict) -> str:
        if not empresa:
            return "Inicial"
        checks = 0
        if empresa.get("nombre"):
            checks += 1
        if empresa.get("cif"):
            checks += 1
        if empresa.get("cuentas_bancarias") or empresa.get("cuenta_bancaria"):
            checks += 1
        if checks >= 3:
            return "Parcial"
        if checks >= 1:
            return "Inicial"
        return "Pendiente"

    def _company_permission_label(self, codigo: str) -> str:
        security = getattr(self._gestor, "security", None)
        if not security:
            return "Completo"
        if getattr(security.session, "is_admin", lambda: False)():
            return "Completo"
        permiso = security.permission_for_company(codigo)
        if getattr(permiso, "value", "") == "escritura":
            return "Escritura"
        if getattr(permiso, "value", "") == "lectura":
            return "Lectura"
        return "Sin acceso"

    def _can_write_company(self, codigo: str) -> bool:
        security = getattr(self._gestor, "security", None)
        if not security:
            return True
        return bool(security.can_write_company(codigo))

    def _split_multiline(self, raw: str) -> list[str]:
        text = str(raw or "")
        for sep in (";", ","):
            text = text.replace(sep, "\n")
        out = []
        for item in text.splitlines():
            value = item.strip()
            if value:
                out.append(value)
        return out

    def _as_int(self, value):
        try:
            return int(value)
        except Exception:
            return None

    def _sort_datetime(self, value):
        txt = str(value or "").strip()
        if not txt:
            return datetime.min
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(txt, fmt)
            except Exception:
                continue
        return datetime.min
