from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class UIDashboardEmpresa(ttk.Frame):
    def __init__(
        self,
        parent,
        empresa_service,
        codigo,
        ejercicio,
        *,
        on_open_facturacion,
        on_open_importaciones,
        on_open_plantillas,
        on_open_configuracion,
        on_open_ocr,
        on_back,
    ):
        super().__init__(parent)
        self._empresa_service = empresa_service
        self._codigo = codigo
        self._ejercicio = ejercicio
        self._callbacks = {
            "facturacion": on_open_facturacion,
            "importaciones": on_open_importaciones,
            "plantillas": on_open_plantillas,
            "configuracion": on_open_configuracion,
            "ocr": on_open_ocr,
            "back": on_back,
        }
        self._ctx = {}
        self._build()
        self.refresh()

    def _build(self):
        head = ttk.Frame(self, padding=12)
        head.pack(fill="x")
        self.lbl_title = ttk.Label(head, text="", font=("Segoe UI", 15, "bold"))
        self.lbl_title.pack(anchor="w")
        self.lbl_sub = ttk.Label(head, text="")
        self.lbl_sub.pack(anchor="w", pady=(2, 0))

        nav = ttk.Frame(self, padding=(12, 0, 12, 8))
        nav.pack(fill="x")
        self._nav_buttons = {}
        buttons = (
            ("inicio", "Inicio", self._callbacks["back"]),
            ("facturacion", "Facturacion", self._callbacks["facturacion"]),
            ("ocr", "OCR", self._callbacks["ocr"]),
            ("importaciones", "Excel / Importaciones", self._callbacks["importaciones"]),
            ("plantillas", "Plantillas", self._callbacks["plantillas"]),
            ("configuracion", "Configuracion empresa", self._callbacks["configuracion"]),
        )
        for key, text, command in buttons:
            btn = ttk.Button(nav, text=text, style="Primary.TButton", command=command)
            btn.pack(side=tk.LEFT, padx=(0, 6), pady=4)
            self._nav_buttons[key] = btn

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(1, weight=1)

        self.info_box = ttk.LabelFrame(body, text="Datos identificativos", padding=12)
        self.info_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        self.lbl_info = ttk.Label(self.info_box, text="", justify="left")
        self.lbl_info.pack(anchor="w")

        self.status_box = ttk.LabelFrame(body, text="Estado", padding=12)
        self.status_box.grid(row=0, column=1, sticky="nsew", pady=(0, 8))
        self.lbl_status = ttk.Label(self.status_box, text="", justify="left")
        self.lbl_status.pack(anchor="w")

        self.summary_box = ttk.LabelFrame(body, text="Resumen operativo", padding=12)
        self.summary_box.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.lbl_summary = ttk.Label(self.summary_box, text="", justify="left")
        self.lbl_summary.pack(anchor="w")

        side = ttk.Frame(body)
        side.grid(row=1, column=1, sticky="nsew")
        side.rowconfigure(0, weight=1)
        side.rowconfigure(1, weight=1)
        side.columnconfigure(0, weight=1)

        self.process_box = ttk.LabelFrame(side, text="Ultimos procesos", padding=12)
        self.process_box.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        self.lb_procesos = tk.Listbox(self.process_box, height=8)
        self.lb_procesos.pack(fill="both", expand=True)

        self.avisos_box = ttk.LabelFrame(side, text="Avisos y pendientes", padding=12)
        self.avisos_box.grid(row=1, column=0, sticky="nsew")
        self.lb_avisos = tk.Listbox(self.avisos_box, height=8)
        self.lb_avisos.pack(fill="both", expand=True)

    def refresh(self):
        self._ctx = self._empresa_service.get_dashboard_context(self._codigo, self._ejercicio)
        empresa = self._ctx.get("empresa") or {}
        self.lbl_title.configure(text=f"{empresa.get('nombre', '')} ({empresa.get('codigo', self._codigo)})")
        self.lbl_sub.configure(
            text=f"Ejercicio {empresa.get('ejercicio', self._ejercicio)} · Acceso {self._ctx.get('permiso', '')}"
        )

        bancos = self._ctx.get("cuentas_bancarias") or []
        info_lines = [
            f"Codigo A3: {empresa.get('codigo', self._codigo)}",
            f"CIF/NIF: {empresa.get('cif', '')}",
            f"Ejercicio: {empresa.get('ejercicio', self._ejercicio)}",
            f"Digitos plan: {empresa.get('digitos_plan', 8)}",
            f"Direccion: {empresa.get('direccion', '')}",
            f"Email: {empresa.get('email', '')}",
            f"Telefono: {empresa.get('telefono', '')}",
            f"Cuentas bancarias: {len(bancos)}",
        ]
        self.lbl_info.configure(text="\n".join(info_lines))

        contab = self._ctx.get("resumen_contabilidad") or {}
        status_lines = [
            f"Configuracion: {self._ctx.get('estado_configuracion', '')}",
            f"Plan contable: {contab.get('plan_cuentas', 0)} cuentas",
            f"Plantillas bancos: {contab.get('plantillas_bancos', 0)}",
            f"Plantillas emitidas: {contab.get('plantillas_emitidas', 0)}",
            f"Plantillas recibidas: {contab.get('plantillas_recibidas', 0)}",
            f"Terceros asignados: {self._ctx.get('terceros_count', 0)}",
        ]
        self.lbl_status.configure(text="\n".join(status_lines))

        fact = self._ctx.get("resumen_facturacion") or {}
        ocr = self._ctx.get("resumen_ocr") or {}
        summary_lines = [
            "Facturacion",
            f"Total facturas emitidas: {fact.get('total', 0)}",
            f"Borrador/Pendientes: {fact.get('borrador', 0)}",
            f"Generadas: {fact.get('generadas', 0)}",
            f"Enviadas: {fact.get('enviadas', 0)}",
            "",
            "OCR",
            f"Estado: {ocr.get('estado', '')}",
            f"Pendientes: {ocr.get('pendientes', 0)}",
            f"Validadas: {ocr.get('validadas', 0)}",
        ]
        self.lbl_summary.configure(text="\n".join(summary_lines))

        self.lb_procesos.delete(0, tk.END)
        for item in self._ctx.get("ultimos_procesos") or []:
            texto = f"{item.get('fecha', '')} · {item.get('estado', '')} · {item.get('descripcion', '')}"
            self.lb_procesos.insert(tk.END, texto)
        if self.lb_procesos.size() == 0:
            self.lb_procesos.insert(tk.END, "Sin procesos recientes.")

        self.lb_avisos.delete(0, tk.END)
        for aviso in self._ctx.get("avisos") or []:
            self.lb_avisos.insert(tk.END, aviso)

        can_write = bool(self._ctx.get("can_write"))
        self._nav_buttons["configuracion"].configure(state=("normal" if can_write else "disabled"))
        self._nav_buttons["plantillas"].configure(state=("normal" if can_write else "disabled"))
        self._nav_buttons["importaciones"].configure(state=("normal" if can_write else "disabled"))
