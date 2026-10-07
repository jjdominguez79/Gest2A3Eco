"""Archivo documental del cliente, separado del procesamiento OCR."""
from __future__ import annotations

import os
import re
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from services.facturas_recibidas_manual_service import (
    FacturasRecibidasManualService,
)
from services.gestion_documental_service import GestionDocumentalService
from services.estado_facturas_recibidas import etiqueta_estado
from services.firma.firma_service import FirmaService
from services.firma.provider import build_firma_provider
from services.impresion_facturas_recibidas_service import (
    ImpresionFacturasRecibidasService,
)
from utils.utilidades import load_app_config
from views.ui_firma_dialog import UIFirmaDialog
from views.ui_previsualizacion_impresion import seleccionar_paginas_impresion


class _MultipleImportDialog(tk.Toplevel):
    """Prepara un lote de documentos mediante seleccion o arrastre."""

    def __init__(self, parent, categories: list[dict], on_import):
        super().__init__(parent)
        self.title("Incorporar documentos")
        self.geometry("860x540")
        self.minsize(700, 440)
        self.transient(parent.winfo_toplevel())
        self._app_root = parent.winfo_toplevel()
        self._categories = {item["nombre"]: item for item in categories}
        self._on_import = on_import
        self._paths: dict[str, Path] = {}
        self._path_keys: set[str] = set()
        self._next_id = 1
        self._busy = False
        self._build()
        self._setup_drag_and_drop()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self):
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text="Incorporar varios documentos",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            frame,
            text=(
                "Todos los archivos del lote se guardaran en la categoria "
                "seleccionada. Puedes revisar la lista antes de incorporarlos."
            ),
            wraplength=810,
        ).pack(anchor="w", pady=(2, 10))

        self._drop_zone = ttk.Label(
            frame,
            text=(
                "Arrastra aqui uno o varios documentos\n"
                "o haz clic para seleccionarlos"
            ),
            anchor="center",
            justify="center",
            relief="groove",
            padding=22,
            cursor="hand2",
        )
        self._drop_zone.pack(fill="x", pady=(0, 10))
        self._drop_zone.bind("<Button-1>", lambda _event: self._select_files())

        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True)
        self._tree = ttk.Treeview(
            table,
            columns=("archivo", "carpeta", "tamano"),
            show="headings",
            selectmode="extended",
        )
        for key, title, width, anchor in (
            ("archivo", "Documento", 330, "w"),
            ("carpeta", "Carpeta de origen", 360, "w"),
            ("tamano", "Tamano", 90, "e"),
        ):
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, anchor=anchor)
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        list_actions = ttk.Frame(frame)
        list_actions.pack(fill="x", pady=(8, 0))
        self._add_button = ttk.Button(
            list_actions, text="Anadir archivos...", command=self._select_files,
        )
        self._add_button.pack(side="left")
        self._remove_button = ttk.Button(
            list_actions, text="Quitar seleccionados", command=self._remove_selected,
        )
        self._remove_button.pack(side="left", padx=6)
        self._clear_button = ttk.Button(
            list_actions, text="Vaciar lista", command=self._clear,
        )
        self._clear_button.pack(side="left")
        self._summary = ttk.Label(list_actions, text="0 documentos")
        self._summary.pack(side="right")

        bottom = ttk.Frame(frame)
        bottom.pack(fill="x", pady=(12, 0))
        ttk.Label(bottom, text="Categoria").pack(side="left")
        first = next(iter(self._categories), "")
        self._category = tk.StringVar(value=first)
        self._category_combo = ttk.Combobox(
            bottom,
            textvariable=self._category,
            values=list(self._categories),
            state="readonly",
            width=30,
        )
        self._category_combo.pack(side="left", padx=(6, 12))
        self._status = ttk.Label(bottom, text="")
        self._status.pack(side="left", fill="x", expand=True)
        ttk.Button(bottom, text="Cancelar", command=self._close).pack(side="right")
        self._import_button = ttk.Button(
            bottom, text="Incorporar documentos", command=self._start_import,
        )
        self._import_button.pack(side="right", padx=(0, 7))

    @staticmethod
    def _path_key(path: Path) -> str:
        return os.path.normcase(os.path.abspath(str(path)))

    def _select_files(self):
        paths = filedialog.askopenfilenames(
            parent=self,
            title="Seleccionar documentos",
            filetypes=(("Todos los archivos", "*.*"),),
        )
        if paths:
            self._add_paths(paths)

    def _add_paths(self, paths) -> int:
        added = 0
        ignored = 0
        for raw in paths:
            path = Path(str(raw)).expanduser()
            if not path.is_file():
                ignored += 1
                continue
            key = self._path_key(path)
            if key in self._path_keys:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                ignored += 1
                continue
            iid = f"archivo-{self._next_id}"
            self._next_id += 1
            self._paths[iid] = path
            self._path_keys.add(key)
            self._tree.insert("", "end", iid=iid, values=(
                path.name, str(path.parent), self._format_size(size),
            ))
            added += 1
        self._update_summary()
        if ignored:
            self._status.configure(
                text=f"Se ignoraron {ignored} elementos que no eran archivos.",
            )
        elif added:
            self._status.configure(text="")
        return added

    @staticmethod
    def _format_size(size: int) -> str:
        if size >= 1_048_576:
            return f"{size / 1_048_576:.1f} MB"
        if size >= 1_024:
            return f"{size / 1_024:.1f} KB"
        return f"{size} B"

    def _remove_selected(self):
        for iid in self._tree.selection():
            path = self._paths.pop(iid, None)
            if path is not None:
                self._path_keys.discard(self._path_key(path))
            self._tree.delete(iid)
        self._update_summary()

    def _clear(self):
        self._tree.delete(*self._tree.get_children())
        self._paths.clear()
        self._path_keys.clear()
        self._update_summary()

    def _update_summary(self):
        total = sum(
            path.stat().st_size for path in self._paths.values()
            if path.is_file()
        )
        self._summary.configure(
            text=f"{len(self._paths)} documentos · {self._format_size(total)}",
        )

    def _setup_drag_and_drop(self):
        if getattr(self._app_root, "_dnd_available", True) is False:
            self._drop_zone.configure(
                text="Haz clic aqui para seleccionar uno o varios documentos",
            )
            return
        try:
            from tkinterdnd2 import DND_FILES

            registered = 0
            last_error = None
            for target in (self._drop_zone, self._tree, self):
                try:
                    target.drop_target_register(DND_FILES)
                    target.dnd_bind("<<Drop>>", self._on_drop)
                    target.dnd_bind("<<DragEnter>>", self._on_drag_enter)
                    target.dnd_bind("<<DragLeave>>", self._on_drag_leave)
                    registered += 1
                except Exception as exc:
                    last_error = exc
            if not registered:
                raise RuntimeError(str(last_error or "Arrastre no disponible"))
        except Exception:
            self._drop_zone.configure(
                text="Haz clic aqui para seleccionar uno o varios documentos",
            )

    def _on_drag_enter(self, event):
        self._drop_zone.configure(text="Suelta los documentos para anadirlos")
        return getattr(event, "action", "copy")

    def _on_drag_leave(self, event):
        self._restore_drop_text()
        return getattr(event, "action", "copy")

    def _on_drop(self, event):
        self._restore_drop_text()
        try:
            paths = list(self.tk.splitlist(event.data))
        except (tk.TclError, TypeError):
            paths = [
                match.group(1) or match.group(2)
                for match in re.finditer(r"\{([^}]+)\}|(\S+)", str(event.data or ""))
            ]
        if not self._add_paths(paths):
            self._status.configure(
                text="No se anadio ningun archivo nuevo.",
            )
        return getattr(event, "action", "copy")

    def _restore_drop_text(self):
        self._drop_zone.configure(
            text=(
                "Arrastra aqui uno o varios documentos\n"
                "o haz clic para seleccionarlos"
            ),
        )

    def _start_import(self):
        category = self._categories.get(self._category.get())
        if not self._paths:
            messagebox.showwarning(
                "Incorporar documentos", "Anade al menos un archivo.", parent=self,
            )
            return
        if not category:
            messagebox.showwarning(
                "Incorporar documentos", "Selecciona una categoria.", parent=self,
            )
            return
        self.set_busy(True)
        self._on_import(list(self._paths.values()), category["id"], self)

    def set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for button in (
            self._add_button, self._remove_button,
            self._clear_button, self._import_button,
        ):
            button.configure(state=state)
        self._category_combo.configure(state="disabled" if busy else "readonly")
        self._status.configure(
            text="Incorporando documentos..." if busy else "",
        )

    def _close(self):
        if self._busy:
            messagebox.showinfo(
                "Incorporar documentos",
                "Espera a que termine la incorporacion en curso.",
                parent=self,
            )
            return
        self.destroy()


class UIGestionDocumental(ttk.Frame):
    def __init__(
        self, parent, gestor, codigo, ejercicio, nombre, session=None,
        open_messaging_incoming=False,
    ):
        super().__init__(parent, padding=12)
        self._gestor = gestor
        self._codigo = codigo
        self._ejercicio = int(ejercicio)
        self._nombre = nombre
        self._session = session
        self._service = GestionDocumentalService(gestor)
        self._impresion_facturas = ImpresionFacturasRecibidasService(gestor)
        self._facturas_manuales = FacturasRecibidasManualService(gestor)
        self._rows = {}
        self._categories = self._service.categorias()
        self._build()
        self._refresh()
        if open_messaging_incoming:
            self.after_idle(self._open_messaging_incoming)

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(
            top, text=f"Gestion documental — {self._nombre} ({self._codigo})",
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left")
        ttk.Button(
            top, text="Incorporar documentos", command=self._add_file,
        ).pack(side="right")
        self._messaging_button = ttk.Button(
            top, text="Entradas pendientes", command=self._open_messaging_incoming,
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
            self,
            columns=(
                "fecha", "categoria", "nombre", "origen", "remitente",
                "estado", "asiento", "impresiones",
            ),
            show="headings", selectmode="extended",
        )
        for key, title, width in (
            ("fecha", "Fecha", 165), ("categoria", "Categoria", 175),
            ("nombre", "Documento", 360), ("origen", "Origen", 100),
            ("remitente", "Remitente", 220), ("estado", "Estado", 230),
            ("asiento", "Asiento", 95),
            ("impresiones", "Impresas", 72),
        ):
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, anchor="w")
        self._tree.pack(fill="both", expand=True)
        self._tree.bind("<Double-1>", lambda _event: self._open())
        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Abrir", command=self._open).pack(side="left")
        ttk.Button(
            actions, text="Cambiar categoria", command=self._change_category,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            actions, text="Imprimir facturas",
            command=self._print_received_invoices,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            actions, text="Comprobar asiento en A3",
            command=self._capture_received_invoice,
        ).pack(side="left", padx=6)
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
                "buzon_origen", "origen",
            )).lower()
            if query and query not in searchable:
                continue
            self._rows[row["id"]] = row
            self._tree.insert("", "end", iid=row["id"], values=(
                row.get("created_at") or "", row.get("categoria_nombre") or "",
                row.get("nombre_original") or "", self._origen_label(row),
                row.get("correo_remitente") or "",
                self._estado_documental_label(row),
                (
                    row.get("numero_asiento") or ""
                    if row.get("categoria_id") == "facturas_recibidas"
                    else ""
                ),
                (
                    int(row.get("veces_impresa") or 0)
                    if row.get("categoria_id") == "facturas_recibidas"
                    else ""
                ),
            ))
        self._summary.configure(text=f"Documentos: {len(self._rows)}")
        pending = self._pending_messaging_rows()
        self._messaging_button.configure(text=f"Entradas pendientes ({len(pending)})")

    @staticmethod
    def _origen_label(row: dict) -> str:
        origen = str(row.get("origen") or "").strip().lower()
        mailbox = str(row.get("buzon_origen") or "").strip().lower()
        if origen == "correo":
            if mailbox.startswith("documentacion@"):
                return "Correo · Documentacion"
            if mailbox.startswith("oficina@"):
                return "Correo · Oficina"
            return "Correo"
        if origen == "chat":
            return "Mensajeria"
        if origen == "manual":
            return "Carga manual"
        return origen.replace("_", " ").title() or "Archivo"

    @staticmethod
    def _estado_documental_label(row: dict) -> str:
        """Describe el circuito contable sin mostrar codigos internos."""
        estado_contable = str(row.get("estado_contable") or "").strip().lower()
        metodo = str(row.get("metodo_contabilizacion") or "").strip().lower()
        estado_ocr = str(row.get("estado_documento_ocr") or "").strip().lower()
        estado_contable_ocr = str(row.get("estado_contable_ocr") or "").strip().lower()
        if estado_contable == "contabilizada_manual" or metodo == "manual_a3_papel":
            return etiqueta_estado(estado_contable, metodo=metodo)
        if estado_contable == "contabilizada":
            if metodo == "ocr_suenlace" or row.get("ocr_documento_id"):
                return etiqueta_estado(estado_contable, metodo="ocr_suenlace")
            return "Contabilizada en A3"
        if estado_contable == "exportada_a3":
            return etiqueta_estado(estado_contable, metodo=metodo)
        if estado_ocr == "contabilizada" or estado_contable_ocr == "contabilizada":
            return "OCR/SUENLACE · pendiente de asiento A3"
        if row.get("ocr_documento_id"):
            return "En OCR"
        return str(row.get("estado") or "Archivado").replace("_", " ").capitalize()

    def _pending_messaging_rows(self):
        if hasattr(self._gestor, "listar_entradas_documentales"):
            return self._gestor.listar_entradas_documentales(
                self._codigo, solo_pendientes=True,
            )
        return [
            {**row, "canal": "mensajeria", "entrada_id": row.get("id")}
            for row in self._gestor.listar_adjuntos_mensajeria_entrada()
            if str(row.get("codigo_empresa") or "") == str(self._codigo)
        ]

    def _open_messaging_incoming(self):
        rows = self._pending_messaging_rows()
        if not rows:
            messagebox.showinfo(
                "Entradas pendientes", "No hay documentos pendientes para este cliente.", parent=self,
            )
            return
        dialog = tk.Toplevel(self)
        dialog.title("Bandeja de entrada documental")
        dialog.geometry("980x440")
        dialog.transient(self.winfo_toplevel())
        tree = ttk.Treeview(
            dialog, columns=("fecha", "canal", "archivo", "remitente"), show="headings",
        )
        for key, title, width in (
            ("fecha", "Recibido", 165), ("canal", "Origen", 145),
            ("archivo", "Documento", 390), ("remitente", "Enviado por", 210),
        ):
            tree.heading(key, text=title)
            tree.column(key, width=width, anchor="w")
        tree.pack(fill="both", expand=True, padx=10, pady=10)
        current = {row["id"]: row for row in rows}
        for row in rows:
            tree.insert("", "end", iid=row["id"], values=(
                row.get("fecha") or row.get("created_at") or "",
                row.get("origen_label") or "Mensajeria",
                row.get("nombre_original") or "",
                row.get("remitente") or "Cliente",
            ))

        def selected():
            selection = tree.selection()
            return current.get(selection[0]) if selection else None

        def open_file():
            item = selected()
            if item and item.get("canal") == "correo":
                messagebox.showinfo(
                    "Correo recibido",
                    "Clasifica la entrada para seleccionar y archivar sus adjuntos.",
                    parent=dialog,
                )
            elif item and Path(str(item.get("ruta_entrada") or "")).is_file():
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
            attachment_ids = None
            if item.get("canal") == "correo":
                try:
                    attachments = self._service.listar_adjuntos_entrada_correo(item)
                except Exception as exc:
                    messagebox.showerror(
                        "Bandeja de entrada",
                        f"No se pudieron consultar los adjuntos:\n{exc}",
                        parent=dialog,
                    )
                    return
                from views.ui_comunicaciones_global import AttachmentSelectionDialog
                selector = AttachmentSelectionDialog(dialog, attachments)
                dialog.wait_window(selector)
                attachment_ids = selector.result
                if not attachment_ids:
                    return
            try:
                user = getattr(self._session, "user", None)
                username = str(getattr(user, "nombre", "") or "sistema")
                self._service.clasificar_entrada_documental(
                    item, ejercicio=self._ejercicio,
                    categoria_id=category["id"], usuario=username,
                    usuario_id=int(getattr(user, "id", 0)),
                    attachment_ids=attachment_ids,
                )
                tree.delete(item["id"])
                current.pop(item["id"], None)
                self._refresh()
            except Exception as exc:
                messagebox.showerror("Bandeja de entrada", str(exc), parent=dialog)

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

    def _selected_received_invoice_ids(self) -> list[str]:
        return [
            str(document_id)
            for document_id in self._tree.selection()
            if self._rows.get(document_id, {}).get("categoria_id")
            == "facturas_recibidas"
        ]

    def _print_received_invoices(self):
        selected = self._selected_received_invoice_ids()
        if not selected:
            messagebox.showwarning(
                "Imprimir facturas",
                "Selecciona al menos un documento de Facturas recibidas.",
                parent=self,
            )
            return
        try:
            paginas = seleccionar_paginas_impresion(
                self, [self._rows[document_id] for document_id in selected],
            )
        except Exception as exc:
            messagebox.showerror(
                "Previsualizar facturas", str(exc), parent=self,
            )
            return
        if paginas is None:
            return
        self.winfo_toplevel().configure(cursor="watch")

        def worker():
            try:
                resultado = self._impresion_facturas.imprimir(
                    selected, usuario=self._username(),
                    paginas_por_documento=paginas,
                )
                error = None
            except Exception as exc:
                resultado, error = None, exc
            self.after(0, self._finish_print_received_invoices, resultado, error)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_print_received_invoices(self, resultado, error):
        self.winfo_toplevel().configure(cursor="")
        if error is not None:
            messagebox.showerror("Imprimir facturas", str(error), parent=self)
            return
        self._refresh()
        partes = []
        if resultado.impresas:
            partes.append(f"Enviadas a imprimir: {len(resultado.impresas)}")
        if resultado.omitidas:
            partes.append("Omitidas:\n- " + "\n- ".join(resultado.omitidas[:8]))
        if resultado.errores:
            partes.append("Errores:\n- " + "\n- ".join(resultado.errores[:8]))
        texto = "\n\n".join(partes) or "No se imprimio ninguna factura."
        if resultado.impresas and not resultado.omitidas and not resultado.errores:
            messagebox.showinfo("Imprimir facturas", texto, parent=self)
        else:
            messagebox.showwarning("Imprimir facturas", texto, parent=self)

    def _change_category(self):
        selected = list(self._tree.selection())
        if not selected:
            messagebox.showwarning(
                "Cambiar categoria", "Selecciona al menos un documento.", parent=self,
            )
            return
        dialog = _CategoryDialog(self, [row["nombre"] for row in self._categories])
        self.wait_window(dialog)
        if not dialog.result:
            return
        category = next(
            row for row in self._categories if row["nombre"] == dialog.result
        )
        cambia_desde_facturas = any(
            self._rows[document_id].get("categoria_id") == "facturas_recibidas"
            for document_id in selected
        ) and category["id"] != "facturas_recibidas"
        detalle = (
            "\n\nLos documentos que salgan de Facturas recibidas se retiraran "
            "del circuito OCR. Si ya fueron exportados o contabilizados, el "
            "cambio se bloqueara."
            if cambia_desde_facturas else ""
        )
        if not messagebox.askyesno(
            "Cambiar categoria",
            f"Mover {len(selected)} documento(s) a {category['nombre']}?{detalle}",
            parent=self,
        ):
            return
        self.winfo_toplevel().configure(cursor="watch")

        def worker():
            cambiados = 0
            errores = []
            for document_id in selected:
                try:
                    if self._service.reclasificar_documento(
                        document_id, category["id"], usuario=self._username(),
                    ):
                        cambiados += 1
                except Exception as exc:
                    nombre = self._rows.get(document_id, {}).get(
                        "nombre_original", document_id,
                    )
                    errores.append(f"{nombre}: {exc}")
            self.after(0, self._finish_change_category, cambiados, errores)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_change_category(self, cambiados: int, errores: list[str]):
        self.winfo_toplevel().configure(cursor="")
        self._refresh()
        texto = f"Documentos reclasificados: {cambiados}"
        if errores:
            texto += "\n\nNo se pudieron reclasificar:\n- " + "\n- ".join(errores[:8])
            messagebox.showwarning("Cambiar categoria", texto, parent=self)
        else:
            messagebox.showinfo("Cambiar categoria", texto, parent=self)

    def _capture_received_invoice(self):
        selected = self._selected_received_invoice_ids()
        if len(selected) != 1:
            messagebox.showwarning(
                "Comprobar asiento en A3",
                "Selecciona una unica factura recibida.",
                parent=self,
            )
            return
        try:
            datos = self._facturas_manuales.datos_captura(selected[0])
        except Exception as exc:
            messagebox.showerror("Comprobar asiento en A3", str(exc), parent=self)
            return
        if not datos:
            messagebox.showerror(
                "Comprobar asiento en A3",
                "No se pudo cargar la factura archivada.",
                parent=self,
            )
            return
        dialog = _DatosCapturaA3Dialog(self, datos)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.winfo_toplevel().configure(cursor="watch")

        def worker():
            try:
                resultado = self._facturas_manuales.capturar_asiento(
                    selected[0], usuario=self._username(), **dialog.result,
                )
                error = None
            except Exception as exc:
                resultado, error = None, exc
            self.after(0, self._finish_capture_received_invoice, resultado, error)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_capture_received_invoice(self, resultado, error):
        self.winfo_toplevel().configure(cursor="")
        if error is not None:
            messagebox.showerror("Comprobar asiento en A3", str(error), parent=self)
            return
        self._refresh()
        if resultado.encontrado:
            messagebox.showinfo(
                "Comprobar asiento en A3",
                f"Factura {resultado.numero_factura}: asiento "
                f"{resultado.numero_asiento} confirmado.",
                parent=self,
            )
        else:
            messagebox.showwarning(
                "Comprobar asiento en A3",
                f"No se encontro en A3ECO la factura {resultado.numero_factura}.",
                parent=self,
            )

    def _username(self) -> str:
        return str(
            getattr(getattr(self._session, "user", None), "nombre", "") or ""
        )

    def _add_file(self):
        _MultipleImportDialog(self, self._categories, self._import_files)

    def _import_files(self, paths: list[Path], category_id: str, dialog) -> None:
        self.winfo_toplevel().configure(cursor="watch")

        def worker():
            try:
                summary = self._service.importar_archivos(
                    codigo_empresa=self._codigo,
                    ejercicio=self._ejercicio,
                    categoria_id=category_id,
                    sources=paths,
                    usuario=getattr(
                        getattr(self._session, "user", None), "nombre", "",
                    ),
                )
                error = None
            except Exception as exc:
                summary, error = None, exc
            try:
                self.after(0, self._finish_import_files, dialog, summary, error)
            except (RuntimeError, tk.TclError):
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _finish_import_files(self, dialog, summary, error=None):
        self.winfo_toplevel().configure(cursor="")
        if error is not None:
            if dialog.winfo_exists():
                dialog.set_busy(False)
            messagebox.showerror(
                "Gestion documental",
                f"No se pudo incorporar el lote:\n{error}",
                parent=dialog if dialog.winfo_exists() else self,
            )
            return
        self._refresh()
        if dialog.winfo_exists():
            dialog.destroy()
        text = f"Documentos incorporados: {len(summary.saved)}"
        if summary.errors:
            text += "\n\nNo se pudieron incorporar:\n- " + "\n- ".join(
                summary.errors[:8]
            )
            if len(summary.errors) > 8:
                text += f"\n- ... y {len(summary.errors) - 8} mas"
            messagebox.showwarning("Gestion documental", text, parent=self)
        else:
            messagebox.showinfo("Gestion documental", text, parent=self)

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


class _DatosCapturaA3Dialog(tk.Toplevel):
    """Solicita las claves de busqueda que una recibida sin OCR no posee."""

    def __init__(self, parent, documento: dict):
        super().__init__(parent)
        self.title("Localizar factura recibida en A3ECO")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.resizable(False, False)
        self.result = None
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text="Datos para localizar el asiento en A3ECO",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        ttk.Label(
            frame,
            text=(
                "No es necesario validar el OCR. Indica el numero utilizado "
                "al contabilizar la factura."
            ),
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self._numero = tk.StringVar(
            value=str(documento.get("numero_factura_captura") or ""),
        )
        self._fecha = tk.StringVar(
            value=str(documento.get("fecha_captura") or "")[:10],
        )
        self._descripcion = tk.StringVar(
            value=str(documento.get("descripcion_captura") or ""),
        )
        for row, (label, variable) in enumerate((
            ("Numero de factura", self._numero),
            ("Fecha para la busqueda", self._fecha),
            ("Concepto en A3 (opcional)", self._descripcion),
        ), start=2):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(frame, textvariable=variable, width=45).grid(
                row=row, column=1, sticky="ew", padx=(8, 0), pady=4,
            )
        ttk.Label(
            frame, text="Formatos de fecha: AAAA-MM-DD o DD/MM/AAAA",
            foreground="#64748b",
        ).grid(row=5, column=1, sticky="w")
        actions = ttk.Frame(frame)
        actions.grid(row=6, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Cancelar", command=self.destroy).pack(side="left")
        ttk.Button(actions, text="Buscar en A3", command=self._accept).pack(
            side="left", padx=(6, 0),
        )

    def _accept(self):
        numero = self._numero.get().strip()
        fecha = self._fecha.get().strip()
        if not numero:
            messagebox.showwarning(
                "Comprobar asiento en A3",
                "Indica el numero de factura.",
                parent=self,
            )
            return
        if fecha and not any(
            self._valid_date(fecha, fmt)
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")
        ):
            messagebox.showwarning(
                "Comprobar asiento en A3",
                "La fecha debe tener formato AAAA-MM-DD o DD/MM/AAAA.",
                parent=self,
            )
            return
        self.result = {
            "numero_factura": numero,
            "fecha_factura": fecha,
            "descripcion": self._descripcion.get().strip(),
        }
        self.destroy()

    @staticmethod
    def _valid_date(value: str, fmt: str) -> bool:
        try:
            datetime.strptime(value, fmt)
            return True
        except ValueError:
            return False
