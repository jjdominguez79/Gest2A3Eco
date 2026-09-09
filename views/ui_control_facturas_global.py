from __future__ import annotations

import csv
import tkinter as tk
import unicodedata
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
        self.var_responsable = tk.StringVar(value="Todos")
        self.var_ejercicio = tk.StringVar(value="Todos")
        self.var_tipo = tk.StringVar(value="Todos")
        self.var_estado = tk.StringVar(value="Todas")
        self.var_buscar = tk.StringVar()
        self._build()
        self.refresh()

    def _build(self):
        self._configure_styles()

        top = ttk.Frame(self)
        top.pack(fill="x", padx=16, pady=(14, 4))
        heading = ttk.Frame(top)
        heading.pack(side=tk.LEFT, fill="x", expand=True)
        ttk.Label(
            heading,
            text="Control global de facturas",
            style="Header.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            heading,
            text=(
                "Supervisa el circuito contable de todas las empresas "
                "desde una unica bandeja."
            ),
            style="SubHeader.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        actions = ttk.Frame(top)
        actions.pack(side=tk.RIGHT, anchor="ne", padx=(16, 0))
        ttk.Button(
            actions,
            text="Exportar CSV",
            style="Secondary.TButton",
            command=self.export_csv,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            actions,
            text="Actualizar datos",
            style="Primary.TButton",
            command=self.refresh,
        ).pack(side=tk.LEFT)

        self.cards = ttk.Frame(self)
        self.cards.pack(fill="x", padx=16, pady=(12, 10))
        self._card_buttons = {}
        for label, filtro in (
            ("Total", "Todas"),
            ("Sin enlace", "Sin enlace"),
            ("En contabilidad", "En contabilidad"),
            ("Sin asiento", "Sin asiento"),
        ):
            button = ttk.Button(
                self.cards,
                text=f"{label}\n0",
                width=19,
                style="Metric.TButton",
                command=lambda f=filtro: self.var_estado.set(f),
            )
            button.pack(side=tk.LEFT, padx=(0, 10), fill="x", expand=True)
            self._card_buttons[filtro] = (label, button)

        filters = ttk.LabelFrame(
            self,
            text="Filtros de consulta",
            style="Section.TLabelframe",
            padding=(12, 8),
        )
        filters.pack(fill="x", padx=16, pady=(0, 10))
        for column in (1, 3, 5, 7):
            filters.columnconfigure(column, weight=1)

        ttk.Label(filters, text="Empresa").grid(row=0, column=0, sticky="w")
        self.cb_empresa = ttk.Combobox(
            filters,
            textvariable=self.var_empresa,
            state="readonly",
            width=28,
        )
        self.cb_empresa.grid(row=0, column=1, sticky="ew", padx=(6, 16), pady=3)

        ttk.Label(filters, text="Responsable").grid(row=0, column=2, sticky="w")
        self.cb_responsable = ttk.Combobox(
            filters,
            textvariable=self.var_responsable,
            state="readonly",
            width=20,
        )
        self.cb_responsable.grid(row=0, column=3, sticky="ew", padx=(6, 16), pady=3)

        ttk.Label(filters, text="Ejercicio").grid(row=0, column=4, sticky="w")
        self.cb_ejercicio = ttk.Combobox(
            filters,
            textvariable=self.var_ejercicio,
            state="readonly",
            width=10,
        )
        self.cb_ejercicio.grid(row=0, column=5, sticky="ew", padx=(6, 16), pady=3)

        ttk.Label(filters, text="Tipo").grid(row=0, column=6, sticky="w")
        ttk.Combobox(
            filters,
            textvariable=self.var_tipo,
            state="readonly",
            width=12,
            values=("Todos", "Emitidas", "Recibidas"),
        ).grid(row=0, column=7, sticky="ew", padx=(6, 0), pady=3)

        ttk.Label(filters, text="Situacion").grid(row=1, column=0, sticky="w")
        ttk.Combobox(
            filters,
            textvariable=self.var_estado,
            state="readonly",
            width=28,
            values=tuple(self.FILTROS),
        ).grid(row=1, column=1, sticky="ew", padx=(6, 16), pady=3)

        ttk.Label(filters, text="Buscar").grid(row=1, column=2, sticky="w")
        search = ttk.Entry(filters, textvariable=self.var_buscar, width=36)
        search.grid(
            row=1,
            column=3,
            columnspan=3,
            sticky="ew",
            padx=(6, 16),
            pady=3,
        )
        ttk.Button(
            filters,
            text="Limpiar filtros",
            command=self.clear_filters,
        ).grid(row=1, column=6, columnspan=2, sticky="e", pady=3)

        for var in (
            self.var_empresa,
            self.var_responsable,
            self.var_ejercicio,
            self.var_tipo,
            self.var_estado,
            self.var_buscar,
        ):
            var.trace_add("write", lambda *_: self.apply_filters())

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        columns = (
            "empresa",
            "responsable",
            "ejercicio",
            "tipo",
            "factura",
            "fecha",
            "tercero",
            "total",
            "estado",
            "enlace",
            "asiento",
        )
        self.tv = ttk.Treeview(wrap, columns=columns, show="headings")
        headers = (
            ("empresa", "Empresa", 180, "w"),
            ("responsable", "Responsable", 135, "w"),
            ("ejercicio", "Ejercicio", 72, "center"),
            ("tipo", "Tipo", 76, "center"),
            ("factura", "Factura", 105, "w"),
            ("fecha", "Fecha", 90, "center"),
            ("tercero", "Tercero", 210, "w"),
            ("total", "Total", 100, "e"),
            ("estado", "Situacion", 150, "w"),
            ("enlace", "Enlace", 100, "center"),
            ("asiento", "Nº asiento", 90, "center"),
        )
        for key, title, width, anchor in headers:
            self.tv.heading(key, text=title)
            self.tv.column(key, width=width, anchor=anchor)
        self.tv.pack(side=tk.LEFT, fill="both", expand=True)
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.tv.yview)
        scroll.pack(side=tk.RIGHT, fill="y")
        self.tv.configure(yscrollcommand=scroll.set)
        self.tv.bind("<Double-1>", lambda _e: self.open_selected())
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=16, pady=(0, 12))
        self.lbl_summary = ttk.Label(bottom)
        self.lbl_summary.pack(side=tk.LEFT)
        ttk.Button(
            bottom,
            text="Abrir modulo de la factura",
            style="Primary.TButton",
            command=self.open_selected,
        ).pack(side=tk.RIGHT)

    def _configure_styles(self):
        style = ttk.Style(self)
        style.configure(
            "Metric.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=(14, 10),
        )
        style.configure(
            "MetricActive.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=(14, 10),
            foreground="#ffffff",
            background="#002C57",
        )
        style.map(
            "MetricActive.TButton",
            foreground=[("active", "#ffffff"), ("pressed", "#ffffff")],
            background=[("active", "#002C57"), ("pressed", "#002C57")],
        )

    def refresh(self):
        self._rows, nombres = self._controller.cargar()
        values = ("Todas", *[
            f"{codigo} - {nombre}" for codigo, nombre in sorted(nombres.items(), key=lambda item: item[1].lower())
        ])
        self.cb_empresa.configure(values=values)
        if self.var_empresa.get() not in self.cb_empresa.cget("values"):
            self.var_empresa.set("Todas")

        responsables = sorted(
            {
                str(row.get("responsable") or "").strip()
                for row in self._rows
                if str(row.get("responsable") or "").strip()
            },
            key=str.casefold,
        )
        self.cb_responsable.configure(
            values=("Todos", "Sin asignar", *responsables),
        )
        if self.var_responsable.get() not in self.cb_responsable.cget("values"):
            self.var_responsable.set("Todos")

        ejercicios = sorted(
            {
                int(row["ejercicio"])
                for row in self._rows
                if str(row.get("ejercicio") or "").isdigit()
            },
            reverse=True,
        )
        self.cb_ejercicio.configure(values=("Todos", *map(str, ejercicios)))
        if self.var_ejercicio.get() not in self.cb_ejercicio.cget("values"):
            self.var_ejercicio.set("Todos")
        self.apply_filters()

    def apply_filters(self):
        estado = self.var_estado.get()
        for filtro, (label, button) in self._card_buttons.items():
            cantidad = sum(1 for row in self._rows if self.FILTROS[filtro](row))
            button.configure(
                text=f"{label}\n{cantidad}",
                style=(
                    "MetricActive.TButton"
                    if estado == filtro
                    else "Metric.TButton"
                ),
            )
        self._visible = self.filter_rows(
            self._rows,
            empresa=self.var_empresa.get(),
            responsable=self.var_responsable.get(),
            ejercicio=self.var_ejercicio.get(),
            tipo=self.var_tipo.get(),
            estado=estado,
            text=self.var_buscar.get(),
        )
        self.tv.delete(*self.tv.get_children())
        self._by_id.clear()
        for index, row in enumerate(self._visible):
            iid = str(index)
            self._by_id[iid] = row
            enlace = "Generado" if row["generada"] else "Pendiente"
            self.tv.insert(
                "",
                "end",
                iid=iid,
                values=(
                    row["empresa_nombre"],
                    row.get("responsable") or "Sin asignar",
                    row.get("ejercicio", ""),
                    row["tipo"].capitalize(),
                    row.get("numero_factura", ""),
                    row.get("fecha", ""),
                    row.get("tercero", ""),
                    self._format_amount(row["total_calculado"]),
                    row["estado_etiqueta"],
                    enlace,
                    row.get("numero_asiento", ""),
                ),
            )
        total_visible = sum(
            float(row.get("total_calculado") or 0) for row in self._visible
        )
        self.lbl_summary.configure(
            text=(
                f"{len(self._visible)} de {len(self._rows)} facturas"
                f"  |  Total visible: {self._format_amount(total_visible)}"
            ),
        )

    @classmethod
    def filter_rows(
        cls,
        rows,
        *,
        empresa="Todas",
        responsable="Todos",
        ejercicio="Todos",
        tipo="Todos",
        estado="Todas",
        text="",
    ):
        codigo_empresa = (
            str(empresa).split(" - ", 1)[0] if empresa != "Todas" else ""
        )
        query = cls._normalize_search(text)
        pred = cls.FILTROS.get(estado, cls.FILTROS["Todas"])
        visible = []
        for row in rows:
            if codigo_empresa and str(row.get("codigo_empresa") or "") != codigo_empresa:
                continue
            row_responsable = str(row.get("responsable") or "").strip()
            if responsable == "Sin asignar":
                if row_responsable:
                    continue
            elif responsable != "Todos" and row_responsable != responsable:
                continue
            if ejercicio != "Todos" and str(row.get("ejercicio") or "") != str(ejercicio):
                continue
            if tipo == "Emitidas" and row.get("tipo") != "emitida":
                continue
            if tipo == "Recibidas" and row.get("tipo") != "recibida":
                continue
            if not pred(row):
                continue
            haystack = " ".join(
                str(row.get(key) or "")
                for key in (
                    "empresa_nombre",
                    "responsable",
                    "numero_factura",
                    "tercero",
                    "nif",
                    "descripcion",
                )
            )
            haystack = cls._normalize_search(haystack)
            if query and query not in haystack:
                continue
            visible.append(row)
        return visible

    def clear_filters(self):
        self.var_empresa.set("Todas")
        self.var_responsable.set("Todos")
        self.var_ejercicio.set("Todos")
        self.var_tipo.set("Todos")
        self.var_estado.set("Todas")
        self.var_buscar.set("")

    @staticmethod
    def _format_amount(value):
        text = f"{float(value or 0):,.2f}"
        return text.replace(",", "_").replace(".", ",").replace("_", ".")

    @staticmethod
    def _normalize_search(value):
        normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
        return "".join(char for char in normalized if not unicodedata.combining(char))

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
            writer.writerow(["Empresa", "Responsable", "Ejercicio", "Tipo", "Factura", "Fecha", "Tercero", "NIF", "Total", "Situacion", "Enlace", "Fecha enlace", "Nº asiento"])
            for row in self._visible:
                writer.writerow([row["empresa_nombre"], row.get("responsable", ""), row.get("ejercicio", ""), row["tipo"], row.get("numero_factura", ""), row.get("fecha", ""), row.get("tercero", ""), row.get("nif", ""), f"{row['total_calculado']:.2f}", row["estado_etiqueta"], "Generado" if row["generada"] else "Pendiente", row.get("fecha_generacion", ""), row.get("numero_asiento", "")])
