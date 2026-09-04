from __future__ import annotations

import json
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, simpledialog, ttk

from services.profile_change_request_service import ProfileChangeRequestService


class UISolicitudesEmpresa(ttk.Frame):
    def __init__(self, parent, gestor, on_back):
        super().__init__(parent)
        self._service = ProfileChangeRequestService(gestor)
        self._on_back = on_back
        self._items = []
        self._build()
        self.refresh()

    def _build(self):
        header = ttk.Frame(self)
        header.pack(fill="x", padx=12, pady=10)
        ttk.Label(
            header, text="Solicitudes de datos de empresa",
            font=("Segoe UI", 14, "bold"),
        ).pack(side=tk.LEFT)
        ttk.Button(header, text="Volver", command=self._on_back).pack(side=tk.RIGHT)

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Button(actions, text="Actualizar", command=self.refresh).pack(side=tk.LEFT)
        ttk.Button(
            actions, text="Aplicar solicitud", style="Primary.TButton",
            command=self._apply_selected,
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            actions, text="Rechazar", command=self._reject_selected,
        ).pack(side=tk.LEFT)

        pane = ttk.Panedwindow(self, orient=tk.VERTICAL)
        pane.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        table_frame = ttk.Frame(pane)
        detail_frame = ttk.Frame(pane)
        pane.add(table_frame, weight=3)
        pane.add(detail_frame, weight=2)

        self.tv = ttk.Treeview(
            table_frame,
            columns=("fecha", "codigo", "empresa", "cambios", "logo"),
            show="headings",
            selectmode="browse",
        )
        for column, title, width in (
            ("fecha", "Fecha", 135),
            ("codigo", "Codigo", 90),
            ("empresa", "Empresa", 280),
            ("cambios", "Datos solicitados", 280),
            ("logo", "Logotipo", 90),
        ):
            self.tv.heading(column, text=title)
            self.tv.column(column, width=width, anchor="w")
        self.tv.pack(side=tk.LEFT, fill="both", expand=True)
        scrollbar = ttk.Scrollbar(table_frame, command=self.tv.yview)
        scrollbar.pack(side=tk.RIGHT, fill="y")
        self.tv.configure(yscrollcommand=scrollbar.set)
        self.tv.bind("<<TreeviewSelect>>", lambda _event: self._show_detail())

        self.detail = tk.Text(detail_frame, height=10, wrap="word", state="disabled")
        self.detail.pack(fill="both", expand=True)

    def refresh(self):
        try:
            self._items = self._service.list_pending()
        except Exception as exc:
            messagebox.showerror(
                "Solicitudes", f"No se pudieron cargar las solicitudes:\n{exc}",
                parent=self.winfo_toplevel(),
            )
            return
        self.tv.delete(*self.tv.get_children())
        for item in self._items:
            changes = dict(item.get("changes") or {})
            self.tv.insert("", "end", iid=str(item["id"]), values=(
                self._format_date(item.get("created_at")),
                item.get("company_code", ""),
                item.get("company_name", ""),
                ", ".join(changes) or "Solo logotipo",
                "Si" if item.get("has_logo") else "No",
            ))
        children = self.tv.get_children()
        if children:
            self.tv.selection_set(children[0])
            self._show_detail()
        else:
            self._set_detail("No hay solicitudes pendientes.")

    def _selected(self):
        selection = self.tv.selection()
        if not selection:
            return None
        request_id = str(selection[0])
        return next((item for item in self._items if item.get("id") == request_id), None)

    def _show_detail(self):
        item = self._selected()
        if not item:
            return
        lines = [
            f"Empresa: {item.get('company_name', '')} ({item.get('company_code', '')})",
            f"Logotipo adjunto: {'Si' if item.get('has_logo') else 'No'}",
            "",
            "Cambios solicitados:",
            json.dumps(item.get("changes") or {}, ensure_ascii=False, indent=2),
        ]
        if item.get("notes"):
            lines.extend(("", "Observaciones:", str(item["notes"])))
        self._set_detail("\n".join(lines))

    def _set_detail(self, value: str):
        self.detail.configure(state="normal")
        self.detail.delete("1.0", tk.END)
        self.detail.insert("1.0", value)
        self.detail.configure(state="disabled")

    def _apply_selected(self):
        item = self._selected()
        if not item:
            return
        if not messagebox.askyesno(
            "Aplicar solicitud",
            "Se actualizaran los datos de todos los ejercicios de la empresa. "
            "Si incluye logotipo, se guardara en el repositorio documental y "
            "sera el utilizado en las facturas.\n\nContinuar?",
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            self._service.apply(item)
        except Exception as exc:
            messagebox.showerror("Solicitudes", str(exc), parent=self.winfo_toplevel())
            return
        messagebox.showinfo(
            "Solicitudes", "Solicitud aplicada correctamente.",
            parent=self.winfo_toplevel(),
        )
        self.refresh()

    def _reject_selected(self):
        item = self._selected()
        if not item:
            return
        note = simpledialog.askstring(
            "Rechazar solicitud", "Motivo del rechazo:",
            parent=self.winfo_toplevel(),
        )
        if note is None:
            return
        try:
            self._service.reject(item, note.strip())
        except Exception as exc:
            messagebox.showerror("Solicitudes", str(exc), parent=self.winfo_toplevel())
            return
        self.refresh()

    @staticmethod
    def _format_date(value) -> str:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime(
                "%d/%m/%Y %H:%M"
            )
        except (TypeError, ValueError):
            return str(value or "")
