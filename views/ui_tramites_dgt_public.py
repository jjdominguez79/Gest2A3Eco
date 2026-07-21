from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from services.tramites_dgt_service import TramitesDgtService


class UITramitesDgtPublicForm(tk.Toplevel):
    def __init__(self, parent, service: TramitesDgtService, *, referencia: str, rol: str, token: str):
        super().__init__(parent)
        self._service = service
        self._referencia = referencia
        self._rol = rol
        self._token = token
        self._expediente = None
        self._vars = {
            "nombre": tk.StringVar(),
            "nif": tk.StringVar(),
            "email": tk.StringVar(),
            "telefono": tk.StringVar(),
            "direccion": tk.StringVar(),
            "cp": tk.StringVar(),
            "poblacion": tk.StringVar(),
            "provincia": tk.StringVar(),
            "representante": tk.StringVar(),
            "observaciones": tk.StringVar(),
            "vehiculo_matricula": tk.StringVar(),
            "vehiculo_bastidor": tk.StringVar(),
            "precio_venta": tk.StringVar(),
            "fecha_operacion": tk.StringVar(),
        }
        self.title(f"Tramites DGT - {rol}")
        self.geometry("760x640")
        self.transient(parent)
        self._build()
        self._load()

    def _build(self):
        header = ttk.Frame(self)
        header.pack(fill="x", padx=14, pady=(12, 8))
        ttk.Label(header, text=f"Formulario {self._rol}", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        self.lbl_ref = ttk.Label(header, text="")
        self.lbl_ref.pack(anchor="w", pady=(2, 0))

        form = ttk.LabelFrame(self, text="Datos para el tramite")
        form.pack(fill="x", padx=14, pady=(0, 10))
        fields = [
            ("Nombre/Razon social", "nombre"),
            ("NIF/NIE/CIF", "nif"),
            ("Email", "email"),
            ("Telefono", "telefono"),
            ("Direccion", "direccion"),
            ("CP", "cp"),
            ("Poblacion", "poblacion"),
            ("Provincia", "provincia"),
            ("Representante", "representante"),
            ("Observaciones", "observaciones"),
        ]
        if self._rol == "vendedor":
            fields.extend(
                [
                    ("Matricula", "vehiculo_matricula"),
                    ("Bastidor", "vehiculo_bastidor"),
                    ("Precio venta", "precio_venta"),
                    ("Fecha operacion", "fecha_operacion"),
                ]
            )
        for row, (label, key) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=3)
            ttk.Entry(form, textvariable=self._vars[key], width=54).grid(row=row, column=1, sticky="ew", padx=8, pady=3)
        form.columnconfigure(1, weight=1)

        docs = ttk.LabelFrame(self, text="Documentacion")
        docs.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self.docs_tv = ttk.Treeview(docs, columns=("tipo", "archivo", "hash"), show="headings", height=6)
        for col, text, width in (
            ("tipo", "Tipo", 150),
            ("archivo", "Archivo", 360),
            ("hash", "SHA256", 170),
        ):
            self.docs_tv.heading(col, text=text)
            self.docs_tv.column(col, width=width, anchor="w")
        self.docs_tv.pack(fill="both", expand=True, padx=8, pady=8)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=14, pady=(0, 12))
        ttk.Button(buttons, text="Guardar datos", style="Primary.TButton", command=self._guardar).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Adjuntar documento", command=self._adjuntar).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Cerrar", command=self.destroy).pack(side=tk.RIGHT)

    def _load(self):
        try:
            self._expediente = self._service.verificar_token(self._referencia, self._rol, self._token)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self)
            self.destroy()
            return
        self.lbl_ref.configure(text=f"Referencia: {self._expediente.get('referencia', '')}")
        payload = dict(self._expediente.get(f"{self._rol}_payload") or {})
        self._vars["nombre"].set(payload.get("nombre") or self._expediente.get(f"{self._rol}_nombre") or "")
        self._vars["email"].set(payload.get("email") or self._expediente.get(f"{self._rol}_email") or "")
        self._vars["telefono"].set(payload.get("telefono") or self._expediente.get(f"{self._rol}_telefono") or "")
        for key in ("nif", "direccion", "cp", "poblacion", "provincia", "representante", "observaciones"):
            self._vars[key].set(payload.get(key) or "")
        if self._rol == "vendedor":
            self._vars["vehiculo_matricula"].set(payload.get("vehiculo_matricula") or self._expediente.get("vehiculo_matricula") or "")
            self._vars["vehiculo_bastidor"].set(payload.get("vehiculo_bastidor") or self._expediente.get("vehiculo_bastidor") or "")
            self._vars["precio_venta"].set(payload.get("precio_venta") or self._expediente.get("precio_venta") or "")
            self._vars["fecha_operacion"].set(payload.get("fecha_operacion") or self._expediente.get("fecha_operacion") or "")
        self._load_docs()

    def _load_docs(self):
        self.docs_tv.delete(*self.docs_tv.get_children())
        if not self._expediente:
            return
        for doc in self._expediente.get("documentos") or []:
            if doc.get("rol") != self._rol:
                continue
            self.docs_tv.insert(
                "",
                "end",
                values=(doc.get("tipo", ""), doc.get("nombre_archivo") or doc.get("ruta") or "", str(doc.get("sha256") or "")[:16]),
            )

    def _guardar(self):
        try:
            payload = {key: var.get() for key, var in self._vars.items()}
            self._service.completar_desde_link(self._referencia, self._rol, self._token, payload)
            self._expediente = self._service.verificar_token(self._referencia, self._rol, self._token)
            messagebox.showinfo("Gest2A3Eco", "Datos guardados.", parent=self)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self)

    def _adjuntar(self):
        if not self._expediente:
            return
        tipo = simpledialog.askstring("Tramites DGT", "Tipo de documento:", parent=self) or "documentacion"
        path = filedialog.askopenfilename(
            title="Seleccionar documento",
            filetypes=(("Documentos", "*.pdf *.jpg *.jpeg *.png *.doc *.docx"), ("Todos", "*.*")),
        )
        if not path:
            return
        try:
            self._service.adjuntar_documento(self._expediente["id"], self._rol, path, tipo=tipo)
            self._expediente = self._service.verificar_token(self._referencia, self._rol, self._token)
            self._load_docs()
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self)
