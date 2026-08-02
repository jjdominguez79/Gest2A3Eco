"""Archivo documental del cliente, separado del procesamiento OCR."""
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from services.gestion_documental_service import GestionDocumentalService


class UIGestionDocumental(ttk.Frame):
    def __init__(self, parent, gestor, codigo, ejercicio, nombre, session=None):
        super().__init__(parent, padding=12)
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = int(ejercicio)
        self._nombre = nombre
        self._session = session
        self._service = GestionDocumentalService(gestor)
        self._rows = {}
        self._categories = self._service.categorias()
        self._build()
        self._refresh()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(
            top, text=f"Gestion documental — {self._nombre} ({self._codigo})",
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left")
        ttk.Button(top, text="Incorporar archivo", command=self._add_file).pack(side="right")
        filters = ttk.Frame(self)
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="Categoria").pack(side="left")
        self._category = tk.StringVar(value="Todas")
        self._category_combo = ttk.Combobox(
            filters, textvariable=self._category, state="readonly", width=28,
            values=["Todas", *[item["nombre"] for item in self._categories]],
        )
        self._category_combo.pack(side="left", padx=(5, 12))
        self._category_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh())
        ttk.Label(filters, text="Buscar").pack(side="left")
        self._search = tk.StringVar()
        entry = ttk.Entry(filters, textvariable=self._search, width=40)
        entry.pack(side="left", padx=5)
        self._search.trace_add("write", lambda *_: self._refresh())
        self._tree = ttk.Treeview(
            self, columns=("fecha", "categoria", "nombre", "origen", "remitente", "estado"),
            show="headings", selectmode="extended",
        )
        for key, title, width in (
            ("fecha", "Fecha", 165), ("categoria", "Categoria", 175),
            ("nombre", "Documento", 360), ("origen", "Origen", 100),
            ("remitente", "Remitente", 220), ("estado", "Estado", 120),
        ):
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, anchor="w")
        self._tree.pack(fill="both", expand=True)
        self._tree.bind("<Double-1>", lambda _event: self._open())
        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Abrir", command=self._open).pack(side="left")
        ttk.Button(actions, text="Enviar a OCR de facturas", command=self._send_ocr).pack(side="left", padx=6)
        ttk.Button(actions, text="Eliminar", command=self._delete).pack(side="left")
        self._summary = ttk.Label(actions, text="")
        self._summary.pack(side="right")

    def _selected_category_id(self):
        name = self._category.get()
        return next((item["id"] for item in self._categories if item["nombre"] == name), "")

    def _refresh(self):
        rows = self._gestor.listar_documentos_archivo(
            self._codigo, self._ejercicio, self._selected_category_id(),
        )
        query = self._search.get().strip().lower()
        self._tree.delete(*self._tree.get_children())
        self._rows = {}
        for row in rows:
            searchable = " ".join(str(row.get(key) or "") for key in (
                "nombre_original", "categoria_nombre", "correo_remitente", "correo_asunto",
            )).lower()
            if query and query not in searchable:
                continue
            self._rows[row["id"]] = row
            self._tree.insert("", "end", iid=row["id"], values=(
                row.get("created_at") or "", row.get("categoria_nombre") or "",
                row.get("nombre_original") or "", row.get("origen") or "",
                row.get("correo_remitente") or "", row.get("estado") or "",
            ))
        self._summary.configure(text=f"Documentos: {len(self._rows)}")

    def _open(self):
        selected = self._tree.selection()
        if not selected:
            return
        try:
            os.startfile(str(self._rows[selected[0]]["ruta"]))
        except Exception as exc:
            messagebox.showerror("Gestion documental", str(exc), parent=self)

    def _add_file(self):
        path = filedialog.askopenfilename(parent=self, title="Incorporar documento")
        if not path:
            return
        choices = [item["nombre"] for item in self._categories]
        dialog = _CategoryDialog(self, choices)
        self.wait_window(dialog)
        if not dialog.result:
            return
        category = next(item for item in self._categories if item["nombre"] == dialog.result)
        try:
            self._service.importar_archivo(
                codigo_empresa=self._codigo, ejercicio=self._ejercicio,
                categoria_id=category["id"], source=path,
                usuario=getattr(getattr(self._session, "user", None), "nombre", ""),
            )
            self._refresh()
        except Exception as exc:
            messagebox.showerror("Gestion documental", str(exc), parent=self)

    def _send_ocr(self):
        selected = list(self._tree.selection())
        if not selected:
            messagebox.showwarning("Gestion documental", "Selecciona documentos.", parent=self)
            return
        self.winfo_toplevel().configure(cursor="watch")

        def worker():
            errors = []
            sent = 0
            for document_id in selected:
                try:
                    self._service.enviar_a_ocr(
                        document_id,
                        getattr(getattr(self._session, "user", None), "nombre", ""),
                    )
                    sent += 1
                except Exception as exc:
                    errors.append(f"{self._rows[document_id]['nombre_original']}: {exc}")
            self.after(0, self._finish_ocr, sent, errors)

        threading.Thread(target=worker, daemon=True).start()

    def _delete(self):
        selected = list(self._tree.selection())
        if not selected:
            messagebox.showwarning("Gestion documental", "Selecciona documentos.", parent=self)
            return
        names = [self._rows[item]["nombre_original"] for item in selected]
        preview = "\n".join(f"- {name}" for name in names[:8])
        if len(names) > 8:
            preview += f"\n- ... y {len(names) - 8} mas"
        if not messagebox.askyesno(
            "Eliminar documentos",
            "Se eliminaran el registro y el archivo de la carpeta compartida:\n\n"
            + preview + "\n\nEsta operacion no se puede deshacer.",
            parent=self,
        ):
            return
        errors = []
        deleted = 0
        for document_id in selected:
            try:
                self._service.eliminar_documento(document_id)
                deleted += 1
            except Exception as exc:
                errors.append(f"{self._rows[document_id]['nombre_original']}: {exc}")
        self._refresh()
        if errors:
            messagebox.showerror(
                "Gestion documental",
                f"Eliminados: {deleted}\n\n" + "\n".join(errors[:8]), parent=self,
            )
        else:
            messagebox.showinfo(
                "Gestion documental", f"Documentos eliminados: {deleted}", parent=self,
            )

    def _finish_ocr(self, sent, errors):
        self.winfo_toplevel().configure(cursor="")
        self._refresh()
        text = f"Enviados a OCR: {sent}"
        if errors:
            text += "\n\n" + "\n".join(errors[:6])
        messagebox.showinfo("Gestion documental", text, parent=self)


class _CategoryDialog(tk.Toplevel):
    def __init__(self, parent, choices):
        super().__init__(parent)
        self.title("Categoria documental")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.result = None
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Categoria").pack(anchor="w")
        self._value = tk.StringVar(value=choices[0] if choices else "")
        ttk.Combobox(frame, textvariable=self._value, values=choices, state="readonly", width=34).pack(pady=8)
        ttk.Button(frame, text="Aceptar", command=self._accept).pack(anchor="e")

    def _accept(self):
        self.result = self._value.get()
        self.destroy()
