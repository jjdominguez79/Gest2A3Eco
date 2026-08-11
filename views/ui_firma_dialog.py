"""Dialogo para elegir firmantes y dibujar zonas de firma sobre un PDF."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk


class UIFirmaDialog(tk.Toplevel):
    def __init__(self, parent, ruta, terceros=None, remitente=None, initial=None):
        super().__init__(parent)
        self.title("Enviar documento a firma")
        self.geometry("1180x760")
        self.transient(parent)
        self.grab_set()
        self._ruta = str(ruta)
        self._terceros = list(terceros or [])
        self._remitente = dict(remitente or {})
        self._initial = dict(initial or {})
        self.result = None
        self._rows = []
        self._zonas = []
        self._pagina = 0
        self._doc = None
        self._photo = None
        self._drag_start = None
        self._build()
        self._render()

    def _build(self):
        form = ttk.Frame(self, padding=10)
        form.pack(fill="x")
        ttk.Label(form, text="Asunto").grid(row=0, column=0, sticky="w")
        self._asunto = tk.StringVar(
            value=str(self._initial.get("asunto") or self._ruta.rsplit("\\", 1)[-1])
        )
        ttk.Entry(form, textvariable=self._asunto, width=70).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Label(form, text="Mensaje").grid(row=1, column=0, sticky="nw", pady=(6, 0))
        self._mensaje = tk.Text(form, height=3, width=70)
        self._mensaje.grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 0))
        if self._initial.get("mensaje"):
            self._mensaje.insert("1.0", str(self._initial["mensaje"]))
        form.columnconfigure(1, weight=1)
        self._yo_firmo = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            form, text="Tambien tengo que firmar (enviar a mi email)",
            variable=self._yo_firmo, command=self._toggle_remitente,
        ).grid(row=2, column=1, sticky="w", pady=(6, 0))

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        left = ttk.Frame(body, padding=8)
        right = ttk.Frame(body, padding=8)
        body.add(left, weight=0)
        body.add(right, weight=1)

        ttk.Label(left, text="Firmantes", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(
            left,
            text="Busca una persona o entidad del maestro de terceros, o escribe cualquier email externo abajo.",
            wraplength=310,
        ).pack(anchor="w", pady=(2, 4))
        self._tercero_var = tk.StringVar()
        self._tercero_opciones = [self._etiqueta_tercero(t) for t in self._terceros]
        self._tercero_combo = ttk.Combobox(
            left, textvariable=self._tercero_var, values=self._tercero_opciones, width=38, state="normal",
        )
        self._tercero_combo.pack(fill="x")
        self._tercero_combo.bind("<KeyRelease>", self._filter_terceros)
        self._tercero_combo.bind("<Return>", lambda _e: self._add_tercero())
        ttk.Button(left, text="Usar tercero seleccionado", command=self._add_tercero).pack(fill="x", pady=(4, 8))
        columns = ttk.Frame(left)
        columns.pack(fill="x")
        ttk.Label(columns, text="Nombre", width=18).grid(row=0, column=0, padx=(0, 3), sticky="w")
        ttk.Label(columns, text="Email", width=26).grid(row=0, column=1, padx=(0, 3), sticky="w")
        ttk.Label(columns, text="Telefono SMS (opcional)", width=20).grid(row=0, column=2, sticky="w")
        self._firmantes_frame = ttk.Frame(left)
        self._firmantes_frame.pack(fill="both", expand=True)
        ttk.Button(left, text="Anadir email manual", command=self._add_manual).pack(fill="x", pady=(8, 0))

        toolbar = ttk.Frame(right)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(toolbar, text="Pagina anterior", command=lambda: self._change_page(-1)).pack(side="left")
        self._pagina_label = ttk.Label(toolbar, text="Pagina 1")
        self._pagina_label.pack(side="left", padx=8)
        ttk.Button(toolbar, text="Pagina siguiente", command=lambda: self._change_page(1)).pack(side="left")
        ttk.Label(toolbar, text="Selecciona un firmante y arrastra sobre el PDF para dibujar su zona.").pack(side="right")
        ttk.Button(toolbar, text="Deshacer ultima zona", command=self._undo_zone).pack(side="right", padx=6)
        self._zona_firmante = tk.StringVar(value="")
        ttk.Label(right, text="Firmante de la nueva zona").pack(anchor="w")
        self._zona_combo = ttk.Combobox(right, textvariable=self._zona_firmante, state="readonly")
        self._zona_combo.pack(anchor="w", pady=(0, 5))
        canvas_wrap = ttk.Frame(right)
        canvas_wrap.pack(fill="both", expand=True)
        canvas_wrap.columnconfigure(0, weight=1)
        canvas_wrap.rowconfigure(0, weight=1)
        self._canvas = tk.Canvas(
            canvas_wrap, background="#d1d5db", cursor="crosshair", highlightthickness=0,
        )
        scroll_y = ttk.Scrollbar(canvas_wrap, orient="vertical", command=self._canvas.yview)
        scroll_x = ttk.Scrollbar(canvas_wrap, orient="horizontal", command=self._canvas.xview)
        self._canvas.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        self._canvas.bind("<ButtonPress-1>", self._start_zone)
        self._canvas.bind("<B1-Motion>", self._move_zone)
        self._canvas.bind("<ButtonRelease-1>", self._finish_zone)
        self._canvas.bind("<Button-3>", self._delete_zone_at)
        self._canvas.bind("<MouseWheel>", self._scroll_vertical)
        self._canvas.bind("<Shift-MouseWheel>", self._scroll_horizontal)
        ttk.Label(
            right, text="Clic derecho sobre una zona para borrarla.",
            foreground="#6b7280",
        ).pack(anchor="w", pady=(3, 0))

        buttons = ttk.Frame(self, padding=(10, 0, 10, 10))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Continuar con el envio", command=self._accept).pack(side="right", padx=8)
        iniciales = list(self._initial.get("firmantes") or [])
        if iniciales:
            for firmante in iniciales:
                self._add_row(firmante)
            self._yo_firmo.set(any(row.get("es_remitente") for row in iniciales))
            self._zonas = [dict(zona) for zona in (self._initial.get("zonas") or [])]
        else:
            self._add_manual()

    @staticmethod
    def _etiqueta_tercero(tercero):
        nombre = tercero.get("nombre_legal") or tercero.get("nombre") or "Sin nombre"
        email = tercero.get("email") or tercero.get("correo") or ""
        nif = tercero.get("nif") or ""
        detalles = " | ".join(str(value).strip() for value in (nif, email) if str(value).strip())
        return f"{nombre} <{detalles}>" if detalles else str(nombre)

    def _filter_terceros(self, event=None):
        if event and event.keysym in ("Return", "Tab", "Down", "Up", "Escape"):
            return
        texto = self._tercero_var.get().strip().lower()
        filtradas = [value for value in self._tercero_opciones if texto in value.lower()]
        self._tercero_combo["values"] = filtradas if texto else self._tercero_opciones
        # Abrir el desplegable automaticamente para mostrar los resultados filtrados.
        # Se usa after(1) para que Tkinter haya procesado el cambio de valores antes.
        if texto and filtradas:
            self._tercero_combo.after(1, self._abrir_dropdown_tercero)

    def _abrir_dropdown_tercero(self):
        """Abre el desplegable del combo de terceros si no esta ya visible."""
        try:
            popdown = self._tercero_combo.tk.call(
                "ttk::combobox::PopdownWindow", str(self._tercero_combo)
            )
            if not self._tercero_combo.tk.call("winfo", "ismapped", popdown):
                self._tercero_combo.tk.call(
                    "ttk::combobox::Post", str(self._tercero_combo)
                )
        except Exception:
            pass

    def _add_tercero(self):
        seleccionado = self._tercero_var.get()
        tercero = next((t for t in self._terceros if self._etiqueta_tercero(t) == seleccionado), None)
        if not tercero:
            coincidencias = [
                t for t in self._terceros
                if seleccionado.strip().lower() in self._etiqueta_tercero(t).lower()
            ]
            tercero = coincidencias[0] if len(coincidencias) == 1 else None
        if tercero:
            self._tercero_var.set(self._etiqueta_tercero(tercero))
            self._add_row(tercero)
            return
        messagebox.showwarning(
            "Firmantes", "Selecciona un tercero concreto de las coincidencias.", parent=self,
        )

    def _add_manual(self):
        self._add_row({})

    def _add_row(self, datos):
        row = ttk.Frame(self._firmantes_frame)
        row.pack(fill="x", pady=2)
        nombre = tk.StringVar(value=str(datos.get("nombre_legal") or datos.get("nombre") or ""))
        email = tk.StringVar(value=str(datos.get("email") or datos.get("correo") or ""))
        telefono = tk.StringVar(value=str(datos.get("telefono") or ""))
        ttk.Entry(row, textvariable=nombre, width=18).grid(row=0, column=0, padx=(0, 3))
        ttk.Entry(row, textvariable=email, width=26).grid(row=0, column=1, padx=(0, 3))
        ttk.Entry(row, textvariable=telefono, width=15).grid(row=0, column=2, padx=(0, 3))
        ttk.Button(row, text="Quitar", command=lambda: self._remove_row(item)).grid(row=0, column=3)
        item = {"frame": row, "nombre": nombre, "email": email, "telefono": telefono,
                "tercero_id": datos.get("tercero_id") or datos.get("id"),
                "es_remitente": bool(datos.get("es_remitente"))}
        self._rows.append(item)
        self._refresh_zone_combo()

    def _remove_row(self, item):
        if item in self._rows:
            self._rows.remove(item)
            item["frame"].destroy()
            self._refresh_zone_combo()
            self._render()

    def _toggle_remitente(self):
        existing = next((row for row in self._rows if row.get("es_remitente")), None)
        if self._yo_firmo.get() and not existing:
            datos = dict(self._remitente)
            self._add_row(datos)
            item = self._rows.pop()
            item["es_remitente"] = True
            self._rows.insert(0, item)
            self._firmantes_frame.pack_forget()
            self._firmantes_frame.pack(fill="both", expand=True)
        elif not self._yo_firmo.get() and existing:
            self._remove_row(existing)
        self._refresh_zone_combo()

    def _refresh_zone_combo(self):
        values = []
        for idx, row in enumerate(self._rows):
            label = row["email"].get().strip() or f"Firmante {idx + 1}"
            if row.get("es_remitente"):
                label = f"Yo: {label}"
            values.append(f"{idx}: {label}")
        self._zona_combo["values"] = values
        if values and not self._zona_firmante.get():
            self._zona_combo.current(0)

    def _load_doc(self):
        if self._doc is None:
            try:
                import fitz
                self._doc = fitz.open(self._ruta)
            except Exception as exc:
                messagebox.showerror("Firma", f"No se pudo abrir el PDF: {exc}", parent=self)
                return False
        return True

    def _render(self):
        if not self._load_doc() or not self._doc:
            return
        page = self._doc[self._pagina]
        try:
            import fitz
            from PIL import Image, ImageTk
            pix = page.get_pixmap(matrix=fitz.Matrix(1.15, 1.15), alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            self._photo = ImageTk.PhotoImage(image)
            self._canvas.delete("all")
            self._canvas.create_image(0, 0, anchor="nw", image=self._photo)
            self._canvas.configure(scrollregion=(0, 0, pix.width, pix.height))
            self._draw_zones()
            self._pagina_label.configure(text=f"Pagina {self._pagina + 1} de {len(self._doc)}")
        except Exception as exc:
            self._canvas.delete("all")
            self._canvas.create_text(20, 20, anchor="nw", text=str(exc), fill="red")

    def _draw_zones(self):
        width = max(1, self._canvas.winfo_width())
        height = max(1, self._canvas.winfo_height())
        if self._doc:
            rect = self._doc[self._pagina].rect
            width = rect.width * 1.15
            height = rect.height * 1.15
        for zone in self._zonas:
            if zone["pagina"] != self._pagina:
                continue
            x, y = zone["x"] * width, zone["y"] * height
            x2, y2 = x + zone["ancho"] * width, y + zone["alto"] * height
            self._canvas.create_rectangle(x, y, x2, y2, outline="#16a34a", width=2, tags=("zona",))
            self._canvas.create_text(x + 3, y + 3, anchor="nw", text=f"Firmante {zone['firmante'] + 1}", fill="#166534", tags=("zona",))

    def _scroll_vertical(self, event):
        self._canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _scroll_horizontal(self, event):
        self._canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")

    def _change_page(self, delta):
        if not self._doc:
            return
        self._pagina = max(0, min(len(self._doc) - 1, self._pagina + delta))
        self._render()

    def _start_zone(self, event):
        if not self._zona_firmante.get():
            return
        self._drag_start = (self._canvas.canvasx(event.x), self._canvas.canvasy(event.y))
        self._canvas.delete("drag")
        self._canvas.create_rectangle(*self._drag_start, *self._drag_start, outline="#2563eb", width=2, tags=("drag",))

    def _move_zone(self, event):
        if self._drag_start:
            self._canvas.coords("drag", *self._drag_start, self._canvas.canvasx(event.x), self._canvas.canvasy(event.y))

    def _finish_zone(self, event):
        if not self._drag_start or not self._doc:
            return
        x1, y1 = self._drag_start
        x2, y2 = self._canvas.canvasx(event.x), self._canvas.canvasy(event.y)
        self._drag_start = None
        self._canvas.delete("drag")
        left, top, right, bottom = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
        page = self._doc[self._pagina].rect
        scale = 1.15
        if right - left < 25 or bottom - top < 15:
            return
        self._zonas.append({
            "pagina": self._pagina, "x": left / (page.width * scale), "y": top / (page.height * scale),
            "ancho": (right - left) / (page.width * scale), "alto": (bottom - top) / (page.height * scale),
            "firmante": int(self._zona_firmante.get().split(":", 1)[0]),
        })
        self._render()

    def _undo_zone(self):
        if self._zonas:
            self._zonas.pop()
            self._render()

    def _delete_zone_at(self, event):
        if not self._doc:
            return
        page = self._doc[self._pagina].rect
        scale = 1.15
        x = self._canvas.canvasx(event.x) / (page.width * scale)
        y = self._canvas.canvasy(event.y) / (page.height * scale)
        for indice in range(len(self._zonas) - 1, -1, -1):
            zona = self._zonas[indice]
            if zona["pagina"] != self._pagina:
                continue
            if (zona["x"] <= x <= zona["x"] + zona["ancho"]
                    and zona["y"] <= y <= zona["y"] + zona["alto"]):
                self._zonas.pop(indice)
                self._render()
                return

    def _accept(self):
        firmantes = []
        for index, row in enumerate(self._rows):
            email = row["email"].get().strip()
            firmantes.append({
                "orden": index + 1, "nombre": row["nombre"].get().strip(), "email": email,
                "telefono": row["telefono"].get().strip(), "tercero_id": row.get("tercero_id"),
                "es_remitente": bool(row.get("es_remitente")),
            })
        if not firmantes:
            messagebox.showwarning("Firma", "Anade al menos un firmante.", parent=self)
            return
        self.result = {
            "asunto": self._asunto.get().strip(), "mensaje": self._mensaje.get("1.0", "end").strip(),
            "firmantes": firmantes, "zonas": list(self._zonas), "usar_sms": False,
        }
        if self._doc:
            self._doc.close()
        self.destroy()
