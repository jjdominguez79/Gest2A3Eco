"""Controller para el modulo de Cuotas Periodicas.

Gestiona el CRUD de cuotas y la logica de generacion de facturas borrador.
Reutiliza la logica de numeracion de FacturasEmitidasController.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime


def _parse_fecha_ddmmyyyy(txt: str) -> date | None:
    """Convierte dd/mm/yyyy a date. Devuelve None si no es valido."""
    try:
        return datetime.strptime(str(txt).strip(), "%d/%m/%Y").date()
    except Exception:
        return None


def _date_to_ddmmyyyy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _calcular_periodos(periodicidad: str, inicio: date, fin: date) -> list[str]:
    """Genera lista de strings YYYY-MM desde inicio hasta fin (inclusive) segun periodicidad."""
    step = {"mensual": 1, "bimestral": 2, "trimestral": 3, "semestral": 6, "anual": 12}.get(periodicidad, 1)
    periodos = []
    y, m = inicio.year, inicio.month
    fin_ym = (fin.year, fin.month)
    while (y, m) <= fin_ym:
        periodos.append(f"{y:04d}-{m:02d}")
        m += step
        while m > 12:
            m -= 12
            y += 1
    return periodos


class CuotasController:
    def __init__(self, gestor, codigo: str, ejercicio: int, empresa_conf: dict,
                 facturas_controller=None):
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._empresa_conf = empresa_conf
        self._facturas_ctrl = facturas_controller  # FacturasEmitidasController para numeracion
        self._view = None  # se asigna despues desde la vista

    def set_view(self, view):
        self._view = view

    # ── Permisos ──────────────────────────────────────────────────────────────

    def _can_write(self) -> bool:
        security = getattr(self._gestor, "security", None)
        return True if not security else security.can_write_company(self._codigo)

    def _ensure_write(self) -> bool:
        if self._can_write():
            return True
        if self._view:
            self._view.show_warning("Gest2A3Eco",
                                    "Esta empresa esta en modo solo lectura para el usuario actual.")
        return False

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def refresh_cuotas(self):
        if not self._view:
            return
        cuotas = self._gestor.listar_cuotas_periodicas(self._codigo, self._ejercicio)
        # Enriquecer con ultimo periodo generado
        for c in cuotas:
            periodos = self._gestor.listar_periodos_generados(c["id"])
            c["_ultimo_periodo"] = periodos[-1] if periodos else ""
            c["_num_generadas"] = len(periodos)
        self._view.set_cuotas(cuotas)

    def nueva_cuota(self):
        if not self._ensure_write():
            return
        series = self._listar_series_activas()
        defaults = self._empresa_defaults()
        result = self._view.open_cuota_dialog(
            {
                "codigo_empresa": self._codigo,
                "ejercicio": self._ejercicio,
                "activa": 1,
                "periodicidad": "mensual",
                "tipo_operacion": "01",
                "modelo_fiscal": "",
                "fecha_inicio": _date_to_ddmmyyyy(date.today()),
            },
            series=series,
            terceros=self._listar_terceros_empresa(),
            empresa_defaults=defaults,
            plantillas_word=self._listar_plantillas_word(),
            plantillas_emitidas=self._listar_plantillas_emitidas(),
        )
        if result:
            self._gestor.upsert_cuota_periodica(result)
            self.refresh_cuotas()

    def editar_cuota(self, cuota_id: str):
        if not self._ensure_write():
            return
        cuota = self._gestor.get_cuota_periodica(cuota_id)
        if not cuota:
            return
        # lineas_json puede ser str o list
        if isinstance(cuota.get("lineas_json"), str):
            try:
                cuota["lineas"] = json.loads(cuota["lineas_json"])
            except Exception:
                cuota["lineas"] = []
        else:
            cuota["lineas"] = cuota.get("lineas_json") or []
        series = self._listar_series_activas()
        defaults = self._empresa_defaults()
        result = self._view.open_cuota_dialog(
            cuota,
            series=series,
            terceros=self._listar_terceros_empresa(),
            empresa_defaults=defaults,
            plantillas_word=self._listar_plantillas_word(),
            plantillas_emitidas=self._listar_plantillas_emitidas(),
        )
        if result:
            result["id"] = cuota_id
            self._gestor.upsert_cuota_periodica(result)
            self.refresh_cuotas()

    def duplicar_cuota(self, cuota_id: str):
        if not self._ensure_write():
            return
        original = self._gestor.get_cuota_periodica(cuota_id)
        if not original:
            return
        # Copiar todos los campos y limpiar los del cliente para que el usuario los seleccione
        import copy
        copia = copy.deepcopy(original)
        copia.pop("id", None)
        copia.pop("created_at", None)
        copia.pop("updated_at", None)
        copia["tercero_id"] = None
        copia["nif"] = ""
        copia["nombre"] = ""
        copia["subcuenta_cliente"] = ""
        # Parsear lineas
        if isinstance(copia.get("lineas_json"), str):
            try:
                copia["lineas"] = json.loads(copia["lineas_json"])
            except Exception:
                copia["lineas"] = []
        else:
            copia["lineas"] = copia.get("lineas_json") or []
        series = self._listar_series_activas()
        defaults = self._empresa_defaults()
        result = self._view.open_cuota_dialog(
            copia,
            series=series,
            terceros=self._listar_terceros_empresa(),
            empresa_defaults=defaults,
            plantillas_word=self._listar_plantillas_word(),
            plantillas_emitidas=self._listar_plantillas_emitidas(),
        )
        if result:
            self._gestor.upsert_cuota_periodica(result)
            self.refresh_cuotas()

    def eliminar_cuota(self, cuota_id: str):
        if not self._ensure_write():
            return
        if not self._view.ask_confirm("Eliminar cuota",
                                      "Se eliminara la cuota y su historial de generacion.\n"
                                      "Las facturas ya generadas no se veran afectadas.\n\n"
                                      "Confirmar?"):
            return
        self._gestor.eliminar_cuota_periodica(cuota_id)
        self.refresh_cuotas()

    def toggle_activa(self, cuota_id: str):
        if not self._ensure_write():
            return
        cuota = self._gestor.get_cuota_periodica(cuota_id)
        if not cuota:
            return
        cuota["activa"] = 0 if cuota.get("activa") else 1
        self._gestor.upsert_cuota_periodica(cuota)
        self.refresh_cuotas()

    # ── Generacion ────────────────────────────────────────────────────────────

    def calcular_cuotas_pendientes(self, hasta: date | None = None) -> list[dict]:
        """Devuelve lista de dicts {cuota, periodos_pendientes} para todas las cuotas activas."""
        if hasta is None:
            hasta = date.today()
        cuotas = self._gestor.listar_cuotas_periodicas(self._codigo, self._ejercicio)
        resultado = []
        for c in cuotas:
            if not c.get("activa"):
                continue
            inicio = _parse_fecha_ddmmyyyy(c.get("fecha_inicio") or "")
            if not inicio:
                continue
            fin_str = c.get("fecha_fin") or ""
            if fin_str:
                fin = _parse_fecha_ddmmyyyy(fin_str)
                if fin is None:
                    fin = hasta
                else:
                    fin = min(fin, hasta)
            else:
                fin = hasta
            if inicio > fin:
                continue
            esperados = _calcular_periodos(c.get("periodicidad", "mensual"), inicio, fin)
            generados = set(self._gestor.listar_periodos_generados(c["id"]))
            pendientes = [p for p in esperados if p not in generados]
            if pendientes:
                resultado.append({"cuota": c, "periodos": pendientes})
        return resultado

    def generar_pendientes(self):
        """Abre el dialogo de generacion y ejecuta la generacion de los seleccionados."""
        if not self._ensure_write():
            return
        pendientes = self.calcular_cuotas_pendientes()
        if not pendientes:
            self._view.show_info("Cuotas", "No hay periodos pendientes de generar.")
            return
        params = self._view.open_generar_dialog(pendientes)
        if not params:
            return
        fecha_factura = params["fecha_factura"]
        seleccionados = params["seleccionados"]  # list of (cuota_id, periodo)
        if not seleccionados:
            self._view.show_info("Cuotas", "No se ha seleccionado ningun periodo.")
            return
        generadas = 0
        errores = []
        # Agrupar por cuota para procesar en orden
        by_cuota: dict[str, list[str]] = {}
        for cid, periodo in seleccionados:
            by_cuota.setdefault(cid, []).append(periodo)
        for cid, periodos in by_cuota.items():
            cuota = self._gestor.get_cuota_periodica(cid)
            if not cuota:
                continue
            periodos_sorted = sorted(periodos)
            for periodo in periodos_sorted:
                try:
                    self._generar_factura_desde_cuota(cuota, periodo, fecha_factura)
                    generadas += 1
                except Exception as exc:
                    errores.append(f"{cuota.get('nombre', cid)} / {periodo}: {exc}")
        msg = f"Se han generado {generadas} factura(s) en borrador."
        if errores:
            msg += f"\n\nErrores ({len(errores)}):\n" + "\n".join(errores[:5])
        self._view.show_info("Cuotas - Generacion completada", msg)
        # Refrescar la vista de facturas si es posible
        if self._facturas_ctrl:
            try:
                self._facturas_ctrl.refresh_facturas()
            except Exception:
                pass
        self.refresh_cuotas()

    def _resolver_tercero_id(self, tercero_id: str, nif: str) -> str:
        """Devuelve tercero_id resuelto: usa el de la cuota, o busca por NIF, o lanza ValueError."""
        if tercero_id:
            # Validar que el tercero aun existe
            try:
                t = self._gestor.get_tercero(str(tercero_id))
                if t:
                    return str(tercero_id)
            except Exception:
                pass
        # Intentar resolver por NIF
        nif_clean = str(nif or "").strip()
        if nif_clean:
            try:
                t = self._gestor.get_tercero_by_nif(nif_clean)
                if t:
                    return str(t["id"])
            except Exception:
                pass
            raise ValueError(
                f"No existe un tercero global con NIF {nif_clean}. "
                "Crealo primero en el maestro de terceros antes de generar esta factura."
            )
        raise ValueError(
            "La cuota no tiene tercero ni NIF asignado. "
            "Edita la cuota y asigna un cliente antes de generar."
        )

    def _generar_factura_desde_cuota(self, cuota: dict, periodo: str, fecha_factura: str):
        """Crea una factura borrador en facturas_emitidas_docs a partir de una cuota.

        Para los campos no definidos en la cuota (subcuenta_cliente, cuenta_bancaria,
        plantillas) aplica fallbacks desde terceros_empresas y la configuracion de empresa.
        """
        # Parsear lineas_json
        lineas_raw = cuota.get("lineas_json") or "[]"
        if isinstance(lineas_raw, list):
            lineas = lineas_raw
        else:
            try:
                lineas = json.loads(lineas_raw)
            except Exception:
                lineas = []

        # ── Resolver tercero_id (obligatorio) ────────────────────────────────
        tercero_id = self._resolver_tercero_id(
            str(cuota.get("tercero_id") or "").strip(),
            str(cuota.get("nif") or "").strip(),
        )

        # ── Fallbacks desde tercero y empresa ────────────────────────────────
        subcuenta_cliente = str(cuota.get("subcuenta_cliente") or "").strip()
        if not subcuenta_cliente and tercero_id:
            try:
                rel = self._gestor.get_tercero_empresa(self._codigo, tercero_id, self._ejercicio)
                subcuenta_cliente = str((rel or {}).get("subcuenta_cliente") or "").strip()
            except Exception:
                pass

        cuenta_bancaria = str(cuota.get("cuenta_bancaria") or "").strip()
        if not cuenta_bancaria:
            try:
                emp = self._gestor.get_empresa(self._codigo, self._ejercicio) or self._empresa_conf
                cuenta_bancaria = str(emp.get("cuenta_bancaria") or "").strip()
            except Exception:
                pass

        # ── Plantillas: usar las de la cuota; si no hay, buscar defaults de empresa ──
        plantilla_emitidas = str(cuota.get("plantilla_emitidas") or "").strip()
        plantilla_word = str(cuota.get("plantilla_word") or "").strip()
        if not plantilla_emitidas or not plantilla_word:
            try:
                pls = self._gestor.listar_emitidas(self._codigo, self._ejercicio)
                if pls and not plantilla_emitidas:
                    plantilla_emitidas = str(pls[0].get("nombre") or "").strip()
            except Exception:
                pass

        fid = str(int(time.time() * 1000))
        doc = {
            "id": fid,
            "codigo_empresa": cuota["codigo_empresa"],
            "ejercicio": cuota["ejercicio"],
            "tercero_id": tercero_id or None,
            "serie": cuota.get("serie") or "",
            "numero": "",
            "fecha_asiento": fecha_factura,
            "fecha_expedicion": fecha_factura,
            "fecha_operacion": fecha_factura,
            "tipo_operacion": cuota.get("tipo_operacion") or "01",
            "modelo_fiscal": cuota.get("modelo_fiscal") or "",
            "nif": cuota.get("nif") or "",
            "nombre": cuota.get("nombre") or "",
            "descripcion": cuota.get("descripcion") or "",
            "observaciones": cuota.get("observaciones") or "",
            "subcuenta_cliente": subcuenta_cliente,
            "forma_pago": cuota.get("forma_pago") or "",
            "cuenta_bancaria": cuenta_bancaria,
            "plantilla_word": plantilla_word,
            "plantilla_emitidas": plantilla_emitidas,
            "retencion_aplica": cuota.get("retencion_aplica") or 0,
            "retencion_pct": cuota.get("retencion_pct"),
            "descuento_total_tipo": cuota.get("descuento_total_tipo"),
            "descuento_total_valor": cuota.get("descuento_total_valor"),
            "moneda_codigo": cuota.get("moneda_codigo"),
            "moneda_simbolo": cuota.get("moneda_simbolo"),
            "lineas": lineas,
            "borrador": 1,
            "generada": 0,
            "fecha_generacion": "",
            "enviado": 0,
        }
        self._gestor.upsert_factura_emitida(doc)
        fecha_hoy = datetime.now().strftime("%d/%m/%Y")
        self._gestor.registrar_periodo_generado(cuota["id"], periodo, fid, fecha_hoy)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _listar_series_activas(self) -> list[str]:
        try:
            series = self._gestor.listar_series_emitidas(self._codigo, self._ejercicio, es_rectificativa=0)
            return [s["nombre"] for s in series if s.get("activa")]
        except Exception:
            return []

    def _listar_terceros_empresa(self) -> list[dict]:
        """Devuelve terceros enriquecidos con subcuenta_cliente de terceros_empresas."""
        try:
            # listar_subcuentas_facturacion ya hace el JOIN con terceros y terceros_empresas
            rows = self._gestor.listar_subcuentas_facturacion(
                self._codigo, ["cliente", "deudor"], activo=True
            )
            # Normalizar para que el dialogo pueda acceder con claves consistentes
            result = []
            seen_ids = set()
            for r in rows:
                tid = str(r.get("tercero_global_id") or r.get("tercero_id") or "")
                entry = {
                    "id": tid,
                    "nif": r.get("tercero_nif") or r.get("nif_snapshot") or "",
                    "nombre": r.get("tercero_nombre_legal") or r.get("tercero_nombre") or r.get("nombre_subcuenta") or "",
                    "subcuenta_cliente": r.get("subcuenta_cliente") or r.get("subcuenta") or "",
                }
                if tid and tid not in seen_ids:
                    seen_ids.add(tid)
                    result.append(entry)
                elif not tid:
                    result.append(entry)
            return result
        except Exception:
            try:
                return self._gestor.listar_terceros()
            except Exception:
                return []

    def _empresa_defaults(self) -> dict:
        """Devuelve defaults de la empresa: cuenta_bancaria y primera plantilla."""
        defaults = {}
        try:
            emp = self._gestor.get_empresa(self._codigo, self._ejercicio) or self._empresa_conf
            defaults["cuenta_bancaria"] = str(emp.get("cuenta_bancaria") or "").strip()
        except Exception:
            pass
        try:
            pls = self._gestor.listar_emitidas(self._codigo, self._ejercicio)
            if pls:
                defaults["plantilla_emitidas"] = str(pls[0].get("nombre") or "").strip()
        except Exception:
            pass
        return defaults

    def _listar_plantillas_word(self) -> list[str]:
        try:
            from pathlib import Path
            from utils.utilidades import get_word_templates_dir
            d = Path(get_word_templates_dir())
            if not d.exists():
                return []
            return sorted([p.name for p in d.glob("*.docx") if p.is_file()],
                          key=lambda s: s.lower())
        except Exception:
            return []

    def _listar_plantillas_emitidas(self) -> list[str]:
        try:
            items = self._gestor.listar_emitidas(self._codigo, self._ejercicio)
            return [str(p.get("nombre") or "").strip() for p in items
                    if str(p.get("nombre") or "").strip()]
        except Exception:
            return []
