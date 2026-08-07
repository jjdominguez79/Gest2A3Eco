"""Bandeja global de solicitudes de firma, con cliente opcional."""
from __future__ import annotations

import os
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from services.firma.firma_service import FirmaService
from services.firma.provider import build_firma_provider
from services.gestion_documental_service import GestionDocumentalService
from utils.utilidades import get_document_repository_dir, load_app_config
from views.ui_firma_dialog import UIFirmaDialog

GLOBAL_CODE = "__GLOBAL__"


class UIFirmasGlobal(ttk.Frame):
    def __init__(self, parent, gestor, session=None):
        super().__init__(parent, padding=12)
        self._gestor = gestor
        self._session = session
        self._rows = {}
        self._build()
        self._refresh()

    def _build(self):
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="Firmas", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(header, text="Nueva solicitud desde disco", command=self._new_request).pack(side="right")
        filters = ttk.Frame(self)
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="Estado").pack(side="left")
        self._status = tk.StringVar(value="Todos")
        ttk.Combobox(
            filters, textvariable=self._status, state="readonly", width=18,
            values=("Todos", "Pendientes", "Enviados", "Firmados", "Finalizados"),
        ).pack(side="left", padx=5)
        ttk.Label(filters, text="Buscar").pack(side="left", padx=(14, 0))
        self._search = tk.StringVar()
        ttk.Entry(filters, textvariable=self._search, width=32).pack(side="left", padx=5)
        ttk.Button(filters, text="Actualizar", command=self._refresh).pack(side="left", padx=6)
        self._search.trace_add("write", lambda *_: self._refresh())
        self._status.trace_add("write", lambda *_: self._refresh())

        self._tree = ttk.Treeview(
            self, columns=("estado", "cliente", "documento", "fecha", "resultado"),
            show="headings", selectmode="browse",
        )
        for key, title, width in (
            ("estado", "Estado", 130), ("cliente", "Cliente", 180),
            ("documento", "Documento", 360), ("fecha", "Creada", 160),
            ("resultado", "Documento firmado", 300),
        ):
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, anchor="w")
        self._tree.pack(fill="both", expand=True)
        self._tree.bind("<Double-1>", lambda _event: self._open_selected())
        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Actualizar estado", command=self._update_selected).pack(side="left")
        ttk.Button(actions, text="Abrir documento", command=self._open_selected).pack(side="left", padx=6)
        ttk.Button(actions, text="Reenviar", command=self._resend_selected).pack(side="left")
        ttk.Button(actions, text="Cancelar", command=self._cancel_selected).pack(side="left", padx=6)
        ttk.Button(actions, text="Marcar pendiente", command=self._mark_pending).pack(side="left", padx=6)
        ttk.Button(actions, text="Dar por finalizado", command=self._finish_selected).pack(side="left")
        self._summary = ttk.Label(actions, text="")
        self._summary.pack(side="right")

    def _refresh(self):
        estado = self._status.get()
        rows = self._gestor.listar_todas_firma_solicitudes("", self._search.get().strip())
        grupos = {
            "Pendientes": {"borrador", "incidencia", "rechazado"},
            "Enviados": {"enviado", "parcialmente_firmado"},
            "Firmados": {"firmado"},
            "Finalizados": {"finalizado"},
        }
        if estado in grupos:
            rows = [row for row in rows if str(row.get("estado") or "") in grupos[estado]]
        self._rows = {str(row["id"]): row for row in rows}
        self._tree.delete(*self._tree.get_children())
        for row in rows:
            codigo = str(row.get("codigo_empresa") or "")
            cliente = "Sin cliente" if codigo == GLOBAL_CODE else codigo
            estado_visible = self._estado_visible(row.get("estado"))
            resultado = row.get("ruta_firmado") or "Pendiente de descarga"
            self._tree.insert("", "end", iid=str(row["id"]), values=(
                estado_visible, cliente, row.get("nombre_documento") or "",
                row.get("created_at") or "", resultado,
            ))
        self._summary.configure(text=f"Solicitudes: {len(rows)}")

    @staticmethod
    def _estado_visible(estado):
        estado = str(estado or "")
        if estado == "firmado":
            return "Firmado"
        if estado == "finalizado":
            return "Finalizado"
        if estado in {"enviado", "parcialmente_firmado"}:
            return "Enviado"
        return "Pendiente"

    def _selected(self):
        selected = self._tree.selection()
        return self._rows.get(selected[0]) if selected else None

    def _new_request(self):
        ruta = filedialog.askopenfilename(parent=self, title="Seleccionar PDF", filetypes=(("PDF", "*.pdf"),))
        if not ruta:
            return
        empresas = self._gestor.listar_empresas()
        setup = _FirmaGlobalSetup(self, empresas)
        self.wait_window(setup)
        if setup.result is None:
            return
        codigo = setup.result.get("codigo") or GLOBAL_CODE
        ejercicio = int(setup.result.get("ejercicio") or datetime.now().year)
        terceros = self._gestor.listar_terceros_por_empresa(codigo, ejercicio) if codigo != GLOBAL_CODE else []
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
        self.configure(cursor="watch")

        def worker():
            try:
                provider = build_firma_provider(cfg)
                archived_id = ""
                envio = ruta
                if codigo != GLOBAL_CODE:
                    category = next(c for c in self._gestor.listar_categorias_documentales() if c["id"] == "firmas")
                    archived_id = GestionDocumentalService(self._gestor).importar_archivo(
                        codigo_empresa=codigo, ejercicio=ejercicio, categoria_id=category["id"],
                        source=ruta, usuario=self._user_name(),
                    )
                    envio = self._gestor.get_documento_archivo(archived_id)["ruta"]
                service = FirmaService(self._gestor, provider=provider, max_mb=cfg.get("firma_max_mb", 15))
                solicitud = service.crear_solicitud(
                    codigo, ejercicio, envio, dialog.result["firmantes"], origen="disco",
                    documento_archivo_id=archived_id, asunto=dialog.result["asunto"],
                    mensaje=dialog.result["mensaje"], zonas=dialog.result["zonas"],
                    creado_por=self._user_name(),
                )
                service.enviar(solicitud)
                self.after(0, self._done, "Solicitud enviada.", "")
            except Exception as exc:
                self.after(0, self._done, "", str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _update_selected(self):
        row = self._selected()
        if not row:
            return
        cfg = load_app_config()
        self.configure(cursor="watch")

        def worker():
            try:
                provider = build_firma_provider(cfg)
                service = FirmaService(self._gestor, provider=provider, max_mb=cfg.get("firma_max_mb", 15))
                destination = self._evidence_dir(row)
                result = service.actualizar_estado(row["id"], str(destination))
                if result.get("estado") == "firmado":
                    service.archivar_evidencias(row["id"])
                self.after(0, self._done, f"Estado: {self._estado_visible(result.get('estado'))}.", "")
            except Exception as exc:
                self.after(0, self._done, "", str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _resend_selected(self):
        self._simple_action("reenviar", "Solicitud reenviada.")

    def _cancel_selected(self):
        self._simple_action("cancelar", "Solicitud cancelada.")

    def _mark_pending(self):
        self._simple_action("marcar_pendiente", "Solicitud preparada para un nuevo envio.")

    def _finish_selected(self):
        self._simple_action("finalizar", "Expediente marcado como finalizado.")

    def _simple_action(self, action, success):
        row = self._selected()
        if not row:
            return
        cfg = load_app_config()
        self.configure(cursor="watch")

        def worker():
            try:
                service = FirmaService(self._gestor, provider=build_firma_provider(cfg))
                getattr(service, action)(row["id"])
                self.after(0, self._done, success, "")
            except Exception as exc:
                self.after(0, self._done, "", str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _open_selected(self):
        row = self._selected()
        if not row:
            return
        ruta = row.get("ruta_firmado") or row.get("ruta_origen")
        if not ruta or not Path(ruta).is_file():
            messagebox.showinfo("Firmas", "El documento firmado aun no esta descargado.", parent=self)
            return
        try:
            os.startfile(str(ruta))
        except Exception as exc:
            messagebox.showerror("Firmas", str(exc), parent=self)

    def _evidence_dir(self, row):
        codigo = str(row.get("codigo_empresa") or "")
        if codigo == GLOBAL_CODE:
            path = get_document_repository_dir() / "Firmas"
        else:
            path = GestionDocumentalService(self._gestor)._category_directory(
                codigo, int(row.get("ejercicio") or datetime.now().year), "FIRMAS"
            )
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _user_name(self):
        return str(getattr(getattr(self._session, "user", None), "nombre", "") or "")

    def _done(self, success, error):
        self.configure(cursor="")
        if error:
            messagebox.showerror("Firmas", error, parent=self)
        else:
            self._refresh()
            messagebox.showinfo("Firmas", success, parent=self)


class _FirmaGlobalSetup(tk.Toplevel):
    def __init__(self, parent, empresas):
        super().__init__(parent)
        self.title("Destino del documento")
        self.transient(parent)
        self.grab_set()
        self.result = None
        self._empresas = list(empresas or [])
        ttk.Label(self, text="Cliente (opcional)").pack(anchor="w", padx=12, pady=(12, 3))
        self._client = tk.StringVar(value="Sin cliente")
        values = ["Sin cliente"] + [f"{e.get('codigo')} - {e.get('nombre')}" for e in self._empresas]
        ttk.Combobox(self, textvariable=self._client, values=values, state="readonly", width=48).pack(padx=12)
        ttk.Label(self, text="Si eliges cliente, el original y las evidencias iran a la categoria Firmas.", wraplength=380).pack(padx=12, pady=10)
        ttk.Button(self, text="Continuar", command=self._accept).pack(side="right", padx=12, pady=(0, 12))
        ttk.Button(self, text="Cancelar", command=self.destroy).pack(side="right", pady=(0, 12))

    def _accept(self):
        value = self._client.get()
        codigo = ""
        if value != "Sin cliente":
            codigo = value.split(" - ", 1)[0]
        self.result = {"codigo": codigo, "ejercicio": datetime.now().year}
        self.destroy()
