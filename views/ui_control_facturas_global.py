from __future__ import annotations

import csv
import tkinter as tk
from tkinter import filedialog, ttk

from controllers.ui_control_facturas_global_controller import ControlFacturasGlobalController


class UIControlFacturasGlobal(ttk.Frame):
    """Bandeja transversal para seguir el ciclo contable de las facturas."""

    FILTROS = {
        "Todas": lambda r: True,
        "Sin enlace": lambda r: not r["generada"],
        "Sin asiento": lambda r: not str(r.get("numero_asiento") or "").strip(),
        "Enlazadas sin asiento": lambda r: r["generada"] and not str(r.get("numero_asiento") or "").strip(),
        "En contabilidad": lambda r: r.get("estado_contable") in {"pendiente", "pendiente_contabilizar"},
        "Contabilizadas sin asiento": lambda r: r.get("estado_contable") == "contabilizada" and not str(r.get("numero_asiento") or "").strip(),
        "Incidencias OCR": lambda r: r.get("tipo") == "recibida" and (r.get("estado_ocr") in {"error", "pendiente", "procesando"} or r.get("estado_validacion") == "pendiente"),
    }

    def __init__(self, parent, gestor, empresa_service, on_open_empresa):
        super().__init__(parent)
        self._controller = ControlFacturasGlobalController(gestor, empresa_service)
        self._on_open_empresa = on_open_empresa
        self._rows: list[dict] = []
        self._visible: list[dict] = []
        self._by_id: dict[str, dict] = {}
        self.var_empresa = tk.StringVar(value="Todas")
        self.var_tipo = tk.StringVar(value="Todos")
        self.var_estado = tk.StringVar(value="Todas")
        self.var_buscar = tk.StringVar()
        self._build()
        self.refresh()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(top, text="Control global de facturas", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(top, text="Seguimiento de enlace, contabilizacion y captura del asiento A3 para todas las empresas accesibles.").pack(anchor="w")

        self.cards = ttk.Frame(self)
        self.cards.pack(fill="x", padx=12, pady=8)
        self._card_buttons = {}
        for label, filtro in (
            ("Total", "Todas"),
            ("Sin enlace", "Sin enlace"),
            ("En contabilidad", "En contabilidad"),
            ("Sin asiento", "Sin asiento"),
        ):
            button = ttk.Button(
                self.cards, text=f"{label}\n0", width=19,
                command=lambda f=filtro: self.var_estado.set(f),
            )
            button.pack(side=tk.LEFT, padx=(0, 8))
            self._card_buttons[filtro] = (label, button)

        filters = ttk.Frame(self)
        filters.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(filters, text="Empresa").pack(side=tk.LEFT)
        self.cb_empresa = ttk.Combobox(filters, textvariable=self.var_empresa, state="readonly", width=30)
        self.cb_empresa.pack(side=tk.LEFT, padx=(5, 12))
        ttk.Label(filters, text="Tipo").pack(side=tk.LEFT)
        ttk.Combobox(filters, textvariable=self.var_tipo, state="readonly", width=11, values=("Todos", "Emitidas", "Recibidas")).pack(side=tk.LEFT, padx=(5, 12))
        ttk.Label(filters, text="Situacion").pack(side=tk.LEFT)
        ttk.Combobox(filters, textvariable=self.var_estado, state="readonly", width=25, values=tuple(self.FILTROS)).pack(side=tk.LEFT, padx=(5, 12))
        ttk.Label(filters, text="Buscar").pack(side=tk.LEFT)
        ttk.Entry(filters, textvariable=self.var_buscar, width=28).pack(side=tk.LEFT, padx=5, fill="x", expand=True)
        ttk.Button(filters, text="Actualizar", command=self.refresh).pack(side=tk.LEFT, padx=5)
        ttk.Button(filters, text="Exportar CSV", command=self.export_csv).pack(side=tk.LEFT)
        for var in (self.var_empresa, self.var_tipo, self.var_estado, self.var_buscar):
            var.trace_add("write", lambda *_: self.apply_filters())

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        columns = ("empresa", "ejercicio", "tipo", "factura", "fecha", "tercero", "total", "estado", "enlace", "asiento")
        self.tv = ttk.Treeview(wrap, columns=columns, show="headings")
        headers = (("empresa", "Empresa", 190), ("ejercicio", "Ejercicio", 75), ("tipo", "Tipo", 76), ("factura", "Factura", 105), ("fecha", "Fecha", 90), ("tercero", "Tercero", 220), ("total", "Total", 100), ("estado", "Situacion", 150), ("enlace", "Enlace", 110), ("asiento", "Nº asiento", 90))
        for key, title, width in headers:
            self.tv.heading(key, text=title)
            self.tv.column(key, width=width, anchor="e" if key == "total" else "w")
        self.tv.pack(side=tk.LEFT, fill="both", expand=True)
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.tv.yview)
        scroll.pack(side=tk.RIGHT, fill="y")
        self.tv.configure(yscrollcommand=scroll.set)
        self.tv.bind("<Double-1>", lambda _e: self.open_selected())
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=12, pady=(0, 10))
        self.lbl_summary = ttk.Label(bottom)
        self.lbl_summary.pack(side=tk.LEFT)
        ttk.Button(bottom, text="Abrir empresa / modulo", style="Primary.TButton", command=self.open_selected).pack(side=tk.RIGHT)

    def refresh(self):
        self._rows, nombres = self._controller.cargar()
        values = ("Todas", *[
            f"{codigo} - {nombre}" for codigo, nombre in sorted(nombres.items(), key=lambda item: item[1].lower())
        ])
        self.cb_empresa.configure(values=values)
        if self.var_empresa.get() not in self.cb_empresa.cget("values"):
            self.var_empresa.set("Todas")
        self.apply_filters()

    def apply_filters(self):
        empresa, tipo, estado, text = self.var_empresa.get(), self.var_tipo.get(), self.var_estado.get(), self.var_buscar.get().strip().lower()
        pred = self.FILTROS.get(estado, self.FILTROS["Todas"])
        for filtro, (label, button) in self._card_buttons.items():
            cantidad = sum(1 for row in self._rows if self.FILTROS[filtro](row))
            button.configure(text=f"{label}\n{cantidad}")
        self._visible = []
        for row in self._rows:
            codigo_empresa = empresa.split(" - ", 1)[0] if empresa != "Todas" else ""
            if codigo_empresa and row.get("codigo_empresa") != codigo_empresa:
                continue
            if tipo == "Emitidas" and row.get("tipo") != "emitida":
                continue
            if tipo == "Recibidas" and row.get("tipo") != "recibida":
                continue
            if not pred(row):
                continue
            haystack = " ".join(str(row.get(k) or "") for k in ("empresa_nombre", "numero_factura", "tercero", "nif", "descripcion")).lower()
            if text and text not in haystack:
                continue
            self._visible.append(row)
        self.tv.delete(*self.tv.get_children())
        self._by_id.clear()
        for index, row in enumerate(self._visible):
            iid = str(index)
            self._by_id[iid] = row
            enlace = "Generado" if row["generada"] else "Pendiente"
            self.tv.insert("", "end", iid=iid, values=(row["empresa_nombre"], row.get("ejercicio", ""), row["tipo"].capitalize(), row.get("numero_factura", ""), row.get("fecha", ""), row.get("tercero", ""), f"{row['total_calculado']:,.2f}", row["estado_etiqueta"], enlace, row.get("numero_asiento", "")))
        self.lbl_summary.configure(text=f"Facturas mostradas: {len(self._visible)} de {len(self._rows)}")

    def open_selected(self):
        selected = self.tv.selection()
        if not selected:
            return
        row = self._by_id.get(str(selected[0]))
        if row:
            self._on_open_empresa(row["codigo_empresa"], int(row["ejercicio"]), "facturacion" if row["tipo"] == "emitida" else "contabilidad")

    def export_csv(self):
        path = filedialog.asksaveasfilename(title="Exportar control global", defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh, delimiter=";")
            writer.writerow(["Empresa", "Ejercicio", "Tipo", "Factura", "Fecha", "Tercero", "NIF", "Total", "Situacion", "Enlace", "Fecha enlace", "Nº asiento"])
            for row in self._visible:
                writer.writerow([row["empresa_nombre"], row.get("ejercicio", ""), row["tipo"], row.get("numero_factura", ""), row.get("fecha", ""), row.get("tercero", ""), row.get("nif", ""), f"{row['total_calculado']:.2f}", row["estado_etiqueta"], "Generado" if row["generada"] else "Pendiente", row.get("fecha_generacion", ""), row.get("numero_asiento", "")])
