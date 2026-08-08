"""Administracion de modelos Word y organizacion de la carpeta compartida."""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from services.firma.plantillas_service import (
    CAMPOS_POR_ORIGEN,
    ORIGENES_CAMPO,
    ORIGENES_FIRMANTE,
    TIPOS_CAMPO,
    PlantillasFirmaService,
)


class UIPlantillasFirmaManager(tk.Toplevel):
    def __init__(self, parent, gestor, usuario: str = ""):
        super().__init__(parent)
        self.title("Plantillas de firma")
        self.geometry("940x540")
        self.transient(parent)
        self.grab_set()
        self._service = PlantillasFirmaService(gestor)
        self._usuario = usuario
        self._rows = {}
        self._build()
        self._refresh()

    def _build(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="Modelos Word para firma", font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Button(top, text="Organizar carpeta compartida", command=self._organize).pack(side="right")
        tree = ttk.Treeview(
            self, columns=("nombre", "archivo", "alcance", "version", "estado"),
            show="headings", selectmode="browse",
        )
        for col, title, width in (
            ("nombre", "Nombre", 230), ("archivo", "Word", 260), ("alcance", "Alcance", 110),
            ("version", "Version", 70), ("estado", "Estado", 150),
        ):
            tree.heading(col, text=title)
            tree.column(col, width=width, anchor="w")
        tree.pack(fill="both", expand=True, padx=10)
        tree.bind("<Double-1>", lambda _e: self._edit())
        self._tree = tree
        actions = ttk.Frame(self, padding=10)
        actions.pack(fill="x")
        ttk.Button(actions, text="Nueva desde Word", command=self._new).pack(side="left")
        ttk.Button(actions, text="Editar configuracion", command=self._edit).pack(side="left", padx=6)
        ttk.Button(actions, text="Abrir Word", command=self._open_word).pack(side="left")
        ttk.Button(actions, text="Desactivar / eliminar", command=self._delete).pack(side="left", padx=6)
        ttk.Button(actions, text="Cerrar", command=self.destroy).pack(side="right")

    def _refresh(self):
        rows = self._service.gestor.listar_plantillas_firma(incluir_inactivas=True)
        self._rows = {str(row["id"]): row for row in rows}
        self._tree.delete(*self._tree.get_children())
        for row in rows:
            try:
                modificada = self._service.sha256(self._service.ruta_plantilla(row)) != str(row.get("hash_docx") or "")
            except Exception:
                modificada = True
            estado = "Modificada: revisar" if modificada else ("Activa" if row.get("activa") else "Pendiente / inactiva")
            self._tree.insert("", "end", iid=str(row["id"]), values=(
                row.get("nombre"), row.get("archivo_relativo"), row.get("alcance"),
                row.get("version"), estado,
            ))

    def _selected(self):
        selected = self._tree.selection()
        return self._rows.get(selected[0]) if selected else None

    def _new(self):
        source = filedialog.askopenfilename(
            parent=self, title="Seleccionar modelo Word", filetypes=(("Word", "*.docx"),)
        )
        if not source:
            return
        try:
            dialog = _PlantillaEditor(self, self._service, source=source, usuario=self._usuario)
            self.wait_window(dialog)
            self._refresh()
        except Exception as exc:
            messagebox.showerror("Plantillas", str(exc), parent=self)

    def _edit(self):
        selected = self._selected()
        if not selected:
            return
        try:
            plantilla = self._service.gestor.get_plantilla_firma(selected["id"])
            dialog = _PlantillaEditor(self, self._service, plantilla=plantilla, usuario=self._usuario)
            self.wait_window(dialog)
            self._refresh()
        except Exception as exc:
            messagebox.showerror("Plantillas", str(exc), parent=self)

    def _open_word(self):
        selected = self._selected()
        if not selected:
            return
        try:
            os.startfile(str(self._service.ruta_plantilla(selected)))
        except Exception as exc:
            messagebox.showerror("Plantillas", str(exc), parent=self)

    def _delete(self):
        selected = self._selected()
        if not selected or not messagebox.askyesno(
            "Plantillas", "La plantilla dejara de estar disponible. El Word compartido se conservara.", parent=self
        ):
            return
        self._service.gestor.eliminar_plantilla_firma(selected["id"])
        self._refresh()

    def _organize(self):
        dialog = _OrganizadorPlantillas(self, self._service)
        self.wait_window(dialog)


class _PlantillaEditor(tk.Toplevel):
    def __init__(self, parent, service, *, source: str = "", plantilla: dict | None = None, usuario: str = ""):
        super().__init__(parent)
        self.title("Configurar plantilla de firma")
        self.geometry("1020x680")
        self.transient(parent)
        self.grab_set()
        self._service = service
        self._source = source
        self._usuario = usuario
        self._plantilla = dict(plantilla or {})
        self._campos = {}
        self._build()
        self._load()

    def _build(self):
        form = ttk.Frame(self, padding=10)
        form.pack(fill="x")
        self._nombre = tk.StringVar()
        self._descripcion = tk.StringVar()
        self._archivo = tk.StringVar()
        self._alcance = tk.StringVar(value="global")
        self._empresas = tk.StringVar()
        self._activa = tk.BooleanVar(value=False)
        self._asunto = tk.StringVar()
        for row, (label, var) in enumerate((
            ("Nombre", self._nombre), ("Descripcion", self._descripcion), ("Archivo", self._archivo),
            ("Asunto predeterminado", self._asunto),
        )):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(form, textvariable=var, width=76, state="readonly" if label == "Archivo" else "normal").grid(
                row=row, column=1, columnspan=3, sticky="ew", padx=6, pady=3
            )
        ttk.Label(form, text="Alcance").grid(row=4, column=0, sticky="w")
        ttk.Combobox(form, textvariable=self._alcance, values=("global", "empresas"), state="readonly", width=14).grid(row=4, column=1, sticky="w", padx=6)
        ttk.Label(form, text="Codigos empresa (separados por coma)").grid(row=4, column=2, sticky="e")
        ttk.Entry(form, textvariable=self._empresas, width=30).grid(row=4, column=3, sticky="ew", padx=6)
        ttk.Checkbutton(form, text="Plantilla activa", variable=self._activa).grid(row=5, column=1, sticky="w", padx=6)
        form.columnconfigure(3, weight=1)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=6)
        fields = ttk.LabelFrame(body, text="Campos detectados", padding=6)
        defaults = ttk.LabelFrame(body, text="Envio predeterminado", padding=6)
        body.add(fields, weight=3)
        body.add(defaults, weight=2)
        self._tree = ttk.Treeview(fields, columns=("clave", "etiqueta", "origen", "campo", "tipo", "obligatorio"), show="headings")
        for col, title, width in (
            ("clave", "Etiqueta Word", 125), ("etiqueta", "Titulo", 130), ("origen", "Origen", 75),
            ("campo", "Campo origen", 105), ("tipo", "Tipo", 80), ("obligatorio", "Obl.", 45),
        ):
            self._tree.heading(col, text=title)
            self._tree.column(col, width=width, anchor="w")
        self._tree.pack(fill="both", expand=True)
        self._tree.bind("<Double-1>", lambda _e: self._edit_field())
        ttk.Button(fields, text="Configurar campo seleccionado", command=self._edit_field).pack(anchor="w", pady=(6, 0))

        ttk.Label(defaults, text="Mensaje").pack(anchor="w")
        self._mensaje = tk.Text(defaults, height=6, width=36)
        self._mensaje.pack(fill="x", pady=(2, 8))
        ttk.Label(defaults, text="Firmantes: un Rol|origen|sms por linea").pack(anchor="w")
        ttk.Label(defaults, text="Origen: empresa, tercero, gestor o manual. SMS es opcional.", foreground="#555").pack(anchor="w")
        self._firmantes = tk.Text(defaults, height=8, width=36)
        self._firmantes.pack(fill="both", expand=True, pady=(4, 0))

        buttons = ttk.Frame(self, padding=10)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Guardar", command=self._save).pack(side="right")
        ttk.Button(buttons, text="Cancelar", command=self.destroy).pack(side="right", padx=6)

    def _load(self):
        if self._plantilla:
            data = self._plantilla
            try:
                current_hash = self._service.sha256(self._service.ruta_plantilla(data))
            except Exception:
                current_hash = ""
            if current_hash and current_hash != str(data.get("hash_docx") or ""):
                data = dict(data)
                data["activa"] = False
                data["zonas"] = []
                data["zonas_revisadas"] = False
                actuales = self._service.detectar_campos(self._service.ruta_plantilla(data))
                anteriores = {str(c.get("clave")): dict(c) for c in data.get("campos") or []}
                data["campos"] = [anteriores.get(key, {
                    "clave": key, "etiqueta": key.replace("_", " ").title(),
                    "origen": "manual", "campo_origen": "", "tipo": "texto",
                    "obligatorio": 0, "valor_defecto": "", "orden": pos,
                }) for pos, key in enumerate(actuales)]
                for pos, field in enumerate(data["campos"]):
                    field["orden"] = pos
                messagebox.showwarning(
                    "Plantilla modificada",
                    "El Word ha cambiado. Revise los campos; las zonas anteriores se descartaran y la plantilla quedara inactiva hasta guardarla.",
                    parent=self,
                )
                self._plantilla = data
            campos = data.get("campos") or []
        else:
            path = Path(self._source)
            claves = self._service.detectar_campos(path)
            data = {"nombre": path.stem, "archivo_relativo": path.name, "alcance": "global"}
            campos = [{
                "clave": key, "etiqueta": key.replace("_", " ").title(), "origen": "manual",
                "campo_origen": "", "tipo": "texto", "obligatorio": 0, "valor_defecto": "", "orden": pos,
            } for pos, key in enumerate(claves)]
        self._nombre.set(str(data.get("nombre") or ""))
        self._descripcion.set(str(data.get("descripcion") or ""))
        self._archivo.set(str(data.get("archivo_relativo") or Path(self._source).name))
        self._alcance.set(str(data.get("alcance") or "global"))
        self._empresas.set(", ".join(data.get("empresas") or []))
        self._activa.set(bool(data.get("activa")))
        self._asunto.set(str(data.get("asunto") or ""))
        self._mensaje.insert("1.0", str(data.get("mensaje") or ""))
        firmantes = data.get("firmantes") or [{"rol": "Cliente", "origen": "empresa", "orden": 1}]
        self._firmantes.insert("1.0", "\n".join(
            f"{f.get('rol')}|{f.get('origen')}" + ("|sms" if f.get("usar_sms") else "")
            for f in firmantes
        ))
        self._campos = {str(c["clave"]): dict(c) for c in campos}
        self._refresh_fields()

    def _refresh_fields(self):
        self._tree.delete(*self._tree.get_children())
        for campo in sorted(self._campos.values(), key=lambda c: int(c.get("orden") or 0)):
            self._tree.insert("", "end", iid=campo["clave"], values=(
                "{{" + campo["clave"] + "}}", campo.get("etiqueta"), campo.get("origen"),
                campo.get("campo_origen"), campo.get("tipo"), "Si" if campo.get("obligatorio") else "No",
            ))

    def _edit_field(self):
        selected = self._tree.selection()
        if not selected:
            return
        key = selected[0]
        dialog = _CampoEditor(self, self._campos[key])
        self.wait_window(dialog)
        if dialog.result:
            self._campos[key] = dialog.result
            self._refresh_fields()

    def _save(self):
        try:
            empresas = [p.strip() for p in self._empresas.get().split(",") if p.strip()]
            firmantes = []
            for pos, line in enumerate(self._firmantes.get("1.0", "end").splitlines()):
                if not line.strip():
                    continue
                parts = [part.strip() for part in line.split("|")]
                rol = parts[0]
                origen = parts[1] if len(parts) > 1 and parts[1] else "manual"
                if origen not in ORIGENES_FIRMANTE:
                    raise ValueError(f"Origen de firmante no valido: {origen}")
                firmantes.append({
                    "rol": rol.strip() or f"Firmante {pos + 1}", "origen": origen,
                    "orden": len(firmantes) + 1,
                    "usar_sms": len(parts) > 2 and parts[2].lower() == "sms",
                })
            data = {
                **self._plantilla,
                "nombre": self._nombre.get().strip(), "descripcion": self._descripcion.get().strip(),
                "archivo_relativo": self._archivo.get().strip(), "alcance": self._alcance.get(),
                "empresas": empresas, "activa": self._activa.get(), "asunto": self._asunto.get().strip(),
                "mensaje": self._mensaje.get("1.0", "end").strip(), "campos": list(self._campos.values()),
                "firmantes": firmantes, "zonas": self._plantilla.get("zonas") or [],
                "zonas_revisadas": bool(self._plantilla.get("zonas_revisadas") or not self._plantilla.get("zonas")),
            }
            if self._plantilla:
                self._service.guardar_configuracion(data, self._usuario)
            else:
                self._service.importar_plantilla(self._source, data, self._usuario)
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Plantillas", str(exc), parent=self)


class _CampoEditor(tk.Toplevel):
    def __init__(self, parent, campo):
        super().__init__(parent)
        self.title(f"Campo {campo.get('clave')}")
        self.transient(parent)
        self.grab_set()
        self.result = None
        self._campo = dict(campo)
        self._label = tk.StringVar(value=str(campo.get("etiqueta") or ""))
        self._origin = tk.StringVar(value=str(campo.get("origen") or "manual"))
        self._source = tk.StringVar(value=str(campo.get("campo_origen") or ""))
        self._type = tk.StringVar(value=str(campo.get("tipo") or "texto"))
        self._required = tk.BooleanVar(value=bool(campo.get("obligatorio")))
        self._default = tk.StringVar(value=str(campo.get("valor_defecto") or ""))
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        for row, (label, var, values) in enumerate((
            ("Titulo visible", self._label, None), ("Origen", self._origin, ORIGENES_CAMPO),
            ("Campo de origen", self._source, None), ("Tipo", self._type, TIPOS_CAMPO),
            ("Valor predeterminado", self._default, None),
        )):
            ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", pady=4)
            if values:
                widget = ttk.Combobox(frm, textvariable=var, values=values, state="readonly", width=32)
            elif label == "Campo de origen":
                sugerencias = sorted({key for campos in CAMPOS_POR_ORIGEN.values() for key in campos})
                widget = ttk.Combobox(frm, textvariable=var, values=sugerencias, state="normal", width=32)
            else:
                widget = ttk.Entry(frm, textvariable=var, width=35)
            widget.grid(row=row, column=1, padx=6, pady=4)
        ttk.Checkbutton(frm, text="Obligatorio", variable=self._required).grid(row=5, column=1, sticky="w")
        ttk.Button(frm, text="Aceptar", command=self._accept).grid(row=6, column=1, sticky="e", pady=(10, 0))

    def _accept(self):
        self.result = {**self._campo, "etiqueta": self._label.get().strip(), "origen": self._origin.get(),
                       "campo_origen": self._source.get().strip(), "tipo": self._type.get(),
                       "obligatorio": self._required.get(), "valor_defecto": self._default.get()}
        self.destroy()


class _OrganizadorPlantillas(tk.Toplevel):
    def __init__(self, parent, service):
        super().__init__(parent)
        self.title("Organizar plantillas compartidas")
        self.geometry("700x480")
        self.transient(parent)
        self.grab_set()
        self._service = service
        self._vars = {}
        service.asegurar_subcarpetas()
        ttk.Label(self, text="Los originales se conservaran en la raiz.", padding=10).pack(anchor="w")
        canvas = ttk.Frame(self, padding=10)
        canvas.pack(fill="both", expand=True)
        for row, path in enumerate(service.listar_raiz_para_organizar()):
            ttk.Label(canvas, text=path.name, width=55).grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar(value="ignorar")
            ttk.Combobox(canvas, textvariable=var, values=("facturas", "albaranes", "firmas", "ignorar"), state="readonly", width=16).grid(row=row, column=1)
            self._vars[path.name] = var
        buttons = ttk.Frame(self, padding=10)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Copiar seleccionadas", command=self._copy).pack(side="right")
        ttk.Button(buttons, text="Cerrar", command=self.destroy).pack(side="right", padx=6)

    def _copy(self):
        result = self._service.copiar_clasificadas({name: var.get() for name, var in self._vars.items()})
        messagebox.showinfo(
            "Organizacion completada",
            f"Copiadas: {len(result['copiados'])}\nIdenticas: {len(result['identicos'])}\n"
            f"Conflictos sin copiar: {len(result['conflictos'])}\nIgnoradas: {len(result['ignorados'])}",
            parent=self,
        )
