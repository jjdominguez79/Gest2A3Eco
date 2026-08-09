"""Archivo documental del cliente, separado del procesamiento OCR."""
from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from services.gestion_documental_service import GestionDocumentalService
from services.firma.firma_service import FirmaService
from services.firma.provider import build_firma_provider
from utils.utilidades import load_app_config
from views.ui_firma_dialog import UIFirmaDialog


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
        self._messaging_button = ttk.Button(
            top, text="Adjuntos de mensajeria", command=self._open_messaging_incoming,
        )
        self._messaging_button.pack(side="right", padx=(0, 6))
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
        security = getattr(self._gestor, "security", None)
        if security is None or security.can_manage_firmas():
            ttk.Button(actions, text="Enviar a firma", command=self._send_firma).pack(side="left", padx=6)
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
        pending = self._pending_messaging_rows()
        self._messaging_button.configure(text=f"Adjuntos de mensajeria ({len(pending)})")

    def _pending_messaging_rows(self):
        return [
            row for row in self._gestor.listar_adjuntos_mensajeria_entrada()
            if str(row.get("codigo_empresa") or "") == str(self._codigo)
        ]

    def _open_messaging_incoming(self):
        rows = self._pending_messaging_rows()
        if not rows:
            messagebox.showinfo(
                "Adjuntos de mensajeria", "No hay documentos pendientes para este cliente.", parent=self,
            )
            return
        dialog = tk.Toplevel(self)
        dialog.title("Adjuntos de mensajeria pendientes")
        dialog.geometry("850x420")
        dialog.transient(self.winfo_toplevel())
        tree = ttk.Treeview(
            dialog, columns=("fecha", "archivo", "remitente"), show="headings",
        )
        for key, title, width in (
            ("fecha", "Recibido", 180), ("archivo", "Documento", 420),
            ("remitente", "Enviado por", 210),
        ):
            tree.heading(key, text=title)
            tree.column(key, width=width, anchor="w")
        tree.pack(fill="both", expand=True, padx=10, pady=10)
        current = {row["id"]: row for row in rows}
        for row in rows:
            tree.insert("", "end", iid=row["id"], values=(
                row.get("created_at") or "", row.get("nombre_original") or "",
                row.get("remitente") or "Cliente",
            ))

        def selected():
            selection = tree.selection()
            return current.get(selection[0]) if selection else None

        def open_file():
            item = selected()
            if item and Path(item["ruta_entrada"]).is_file():
                os.startfile(item["ruta_entrada"])

        def classify():
            item = selected()
            if not item:
                return
            category_dialog = _CategoryDialog(dialog, [row["nombre"] for row in self._categories])
            dialog.wait_window(category_dialog)
            if not category_dialog.result:
                return
            category = next(row for row in self._categories if row["nombre"] == category_dialog.result)
            try:
                document_id = self._service.archivar_adjunto_mensajeria(
                    item, ejercicio=self._ejercicio, categoria_id=category["id"],
                    usuario=getattr(getattr(self._session, "user", None), "nombre", ""),
                )
                self._gestor.actualizar_adjunto_mensajeria_entrada(
                    item["id"], "archivado", documento_id=document_id,
                )
                tree.delete(item["id"])
                current.pop(item["id"], None)
                self._refresh()
            except Exception as exc:
                messagebox.showerror("Adjuntos de mensajeria", str(exc), parent=dialog)

        actions = ttk.Frame(dialog)
        actions.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(actions, text="Abrir", command=open_file).pack(side="left")
        ttk.Button(actions, text="Clasificar", command=classify).pack(side="left", padx=6)
        ttk.Button(actions, text="Cerrar", command=dialog.destroy).pack(side="right")

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

    def _send_firma(self):
        security = getattr(self._gestor, "security", None)
        if security is not None:
            security.ensure_firmas()
        selected = list(self._tree.selection())
        if len(selected) != 1:
            messagebox.showwarning("Gestion documental", "Selecciona un unico PDF.", parent=self)
            return
        documento = self._rows[selected[0]]
        ruta = str(documento.get("ruta") or "")
        if not ruta.lower().endswith(".pdf"):
            messagebox.showwarning("Firma", "Solo se pueden enviar documentos PDF.", parent=self)
            return
        try:
            terceros = self._gestor.listar_terceros_por_empresa(self._codigo, self._ejercicio)
        except Exception:
            terceros = []
        cfg = load_app_config()
        remitente = {
            "nombre": cfg.get("signrequest_gestor_email") or cfg.get("signrequest_from_email") or "Remitente",
            "email": cfg.get("signrequest_gestor_email") or cfg.get("signrequest_from_email") or "",
            "telefono": cfg.get("signrequest_gestor_telefono") or "",
        }
        dialog = UIFirmaDialog(self, ruta, terceros=terceros, remitente=remitente)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.winfo_toplevel().configure(cursor="watch")

        def worker():
            try:
                provider = build_firma_provider(cfg)
                for firmante in dialog.result["firmantes"]:
                    if firmante.get("es_remitente") and not firmante.get("email"):
                        firmante["email"] = str(
                            getattr(provider, "gestor_email", "")
                            or getattr(provider, "from_email", "")
                            or ""
                        )
                service = FirmaService(self._gestor, provider=provider, max_mb=cfg.get("firma_max_mb", 15))
                solicitud_id = service.crear_solicitud(
                    self._codigo, self._ejercicio, ruta, dialog.result["firmantes"],
                    documento_archivo_id=str(documento["id"]), asunto=dialog.result["asunto"],
                    mensaje=dialog.result["mensaje"], usar_sms=dialog.result["usar_sms"],
                    zonas=dialog.result["zonas"], creado_por=getattr(getattr(self._session, "user", None), "nombre", ""),
                )
                service.enviar(solicitud_id)
                self.after(0, self._finish_firma, "Solicitud enviada correctamente.", "")
            except Exception as exc:
                self.after(0, self._finish_firma, "", str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_firma(self, ok, error):
        self.winfo_toplevel().configure(cursor="")
        if error:
            messagebox.showerror("Firma", error, parent=self)
        else:
            messagebox.showinfo("Firma", ok, parent=self)

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
