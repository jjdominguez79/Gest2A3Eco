"""Asistente para rellenar un documento desde una plantilla de firma."""
from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from services.firma.datos_firma_service import listar_terceros_para_firma


class UIDocumentoFirmaPlantillaDialog(tk.Toplevel):
    def __init__(self, parent, service, gestor, usuario: str = ""):
        super().__init__(parent)
        self.title("Nuevo documento desde plantilla")
        self.geometry("820x700")
        self.transient(parent)
        self.grab_set()
        self.result = None
        self._service = service
        self._gestor = gestor
        self._usuario = usuario
        self._empresas = self._latest_companies(gestor.listar_empresas())
        self._templates = []
        self._terceros = []
        self._field_vars = {}
        self._build()
        self._on_company()

    @staticmethod
    def _latest_companies(rows):
        by_code = {}
        for row in rows or []:
            code = str(row.get("codigo") or "")
            if code and int(row.get("ejercicio") or 0) >= int(by_code.get(code, {}).get("ejercicio") or 0):
                by_code[code] = dict(row)
        return sorted(by_code.values(), key=lambda row: str(row.get("nombre") or "").lower())

    def _build(self):
        header = ttk.Frame(self, padding=10)
        header.pack(fill="x")
        ttk.Label(header, text="Datos de origen", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(header, text="Cliente (empresa asesorada)").grid(row=1, column=0, sticky="w", pady=4)
        self._company = tk.StringVar(value="Sin empresa (datos manuales)")
        self._company_values = ["Sin empresa (datos manuales)"] + [self._company_label(e) for e in self._empresas]
        self._company_cb = ttk.Combobox(
            header, textvariable=self._company, values=self._company_values, state="normal", width=58,
        )
        self._company_cb.grid(row=1, column=1, sticky="ew", padx=6)
        self._company_cb.bind("<KeyRelease>", self._filter_companies)
        self._company_cb.bind("<<ComboboxSelected>>", lambda _e: self._on_company())
        self._company_cb.bind("<Return>", lambda _e: self._select_company_match())
        ttk.Label(header, text="Plantilla").grid(row=2, column=0, sticky="w", pady=4)
        self._template = tk.StringVar()
        self._template_cb = ttk.Combobox(header, textvariable=self._template, state="readonly", width=58)
        self._template_cb.grid(row=2, column=1, sticky="ew", padx=6)
        self._template_cb.bind("<<ComboboxSelected>>", lambda _e: self._load_fields())
        ttk.Label(header, text="Tercero del cliente (opcional)").grid(row=3, column=0, sticky="w", pady=4)
        self._third = tk.StringVar(value="Sin tercero")
        self._third_cb = ttk.Combobox(header, textvariable=self._third, state="normal", width=58)
        self._third_cb.grid(row=3, column=1, sticky="ew", padx=6)
        self._third_cb.bind("<KeyRelease>", self._filter_thirds)
        self._third_cb.bind("<<ComboboxSelected>>", lambda _e: self._load_fields())
        self._third_cb.bind("<Return>", lambda _e: self._select_third_match())
        ttk.Label(
            header,
            text="Tercero significa una persona o entidad del maestro (cliente, proveedor o contacto del cliente).",
            foreground="#555", wraplength=620,
        ).grid(row=4, column=1, sticky="w", padx=6, pady=(0, 5))
        ttk.Label(
            header,
            text="Al cambiar cliente o tercero se actualizan los campos vinculados; los configurados como manuales se conservan para introducirlos aqui.",
            foreground="#555", wraplength=620,
        ).grid(row=5, column=1, sticky="w", padx=6, pady=(0, 5))
        header.columnconfigure(1, weight=1)

        wrapper = ttk.LabelFrame(self, text="Campos del documento", padding=8)
        wrapper.pack(fill="both", expand=True, padx=10, pady=5)
        canvas = tk.Canvas(wrapper, highlightthickness=0)
        scroll = ttk.Scrollbar(wrapper, orient="vertical", command=canvas.yview)
        self._fields = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=self._fields, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        self._fields.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        buttons = ttk.Frame(self, padding=10)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Generar Word y PDF", command=self._accept).pack(side="right")
        ttk.Button(buttons, text="Cancelar", command=self.destroy).pack(side="right", padx=6)

    @staticmethod
    def _company_label(row):
        return f"{row.get('codigo')} - {row.get('nombre')} ({row.get('ejercicio')})"

    @staticmethod
    def _third_label(row):
        nombre = row.get("nombre_legal") or row.get("nombre") or "Sin nombre"
        nif = str(row.get("nif") or "").strip()
        email = str(row.get("email") or row.get("correo") or "").strip()
        detalles = " | ".join(value for value in (nif, email) if value)
        return f"{nombre} <{detalles}>" if detalles else str(nombre)

    def _selected_company(self):
        label = self._company.get()
        return next((row for row in self._empresas if self._company_label(row) == label), None)

    def _selected_template(self):
        label = self._template.get()
        return next((row for row in self._templates if str(row.get("nombre")) == label), None)

    def _selected_third(self):
        label = self._third.get()
        return next((row for row in self._terceros if self._third_label(row) == label), None)

    @staticmethod
    def _matches(values, text):
        needle = str(text or "").strip().lower()
        return [value for value in values if not needle or needle in value.lower()]

    def _filter_companies(self, event=None):
        if event and event.keysym in ("Return", "Tab", "Down", "Up", "Escape"):
            return
        self._company_cb["values"] = self._matches(self._company_values, self._company.get())

    def _select_company_match(self):
        matches = self._matches(self._company_values, self._company.get())
        if len(matches) == 1:
            self._company.set(matches[0])
            self._on_company()

    def _filter_thirds(self, event=None):
        if event and event.keysym in ("Return", "Tab", "Down", "Up", "Escape"):
            return
        self._third_cb["values"] = self._matches(self._third_values, self._third.get())

    def _select_third_match(self):
        matches = self._matches(self._third_values, self._third.get())
        if len(matches) == 1:
            self._third.set(matches[0])
            self._load_fields()

    def _on_company(self):
        empresa = self._selected_company()
        codigo = str((empresa or {}).get("codigo") or "")
        self._templates = []
        for summary in self._gestor.listar_plantillas_firma(codigo):
            full = self._gestor.get_plantilla_firma(summary["id"])
            try:
                self._service.comprobar_plantilla(full)
            except Exception:
                continue
            self._templates.append(summary)
        names = [str(row.get("nombre") or "") for row in self._templates]
        self._template_cb["values"] = names
        self._template.set(names[0] if names else "")
        self._company_cb["values"] = self._company_values
        self._terceros = listar_terceros_para_firma(
            self._gestor, codigo, int((empresa or {}).get("ejercicio") or datetime.now().year),
        )
        self._third_values = ["Sin tercero"] + [self._third_label(row) for row in self._terceros]
        self._third_cb["values"] = self._third_values
        self._third.set("Sin tercero")
        self._load_fields()

    def _load_fields(self):
        for child in self._fields.winfo_children():
            child.destroy()
        self._field_vars = {}
        template_summary = self._selected_template()
        if not template_summary:
            ttk.Label(self._fields, text="No hay plantillas activas para esta seleccion.").pack(anchor="w")
            return
        plantilla = self._gestor.get_plantilla_firma(template_summary["id"])
        self._current_template = plantilla
        values = self._service.valores_iniciales(
            plantilla, self._selected_company(), self._selected_third(), self._usuario
        )
        for row, campo in enumerate(plantilla.get("campos") or []):
            label = str(campo.get("etiqueta") or campo.get("clave"))
            if campo.get("obligatorio"):
                label += " *"
            ttk.Label(self._fields, text=label, width=28).grid(row=row, column=0, sticky="nw", pady=4)
            var = tk.StringVar(value=str(values.get(campo["clave"]) or ""))
            if campo.get("tipo") == "booleano":
                widget = ttk.Combobox(self._fields, textvariable=var, values=("Si", "No"), state="readonly")
            else:
                widget = ttk.Entry(self._fields, textvariable=var, width=58)
            widget.grid(row=row, column=1, sticky="ew", padx=6, pady=4)
            self._field_vars[str(campo["clave"])] = var
        self._fields.columnconfigure(1, weight=1)

    def _accept(self):
        if self._company.get() != "Sin empresa (datos manuales)" and not self._selected_company():
            messagebox.showwarning(
                "Documento", "Selecciona un cliente de las coincidencias del desplegable.", parent=self,
            )
            return
        if self._third.get() != "Sin tercero" and not self._selected_third():
            messagebox.showwarning(
                "Documento", "Selecciona un tercero de las coincidencias del desplegable.", parent=self,
            )
            return
        plantilla = getattr(self, "_current_template", None)
        if not plantilla:
            messagebox.showwarning("Documento", "Selecciona una plantilla.", parent=self)
            return
        values = {key: var.get().strip() for key, var in self._field_vars.items()}
        try:
            self._service.validar_valores(plantilla, values)
        except Exception as exc:
            messagebox.showerror("Documento", str(exc), parent=self)
            return
        self.result = {
            "plantilla": plantilla, "empresa": self._selected_company(),
            "tercero": self._selected_third(), "valores": values,
        }
        self.destroy()
