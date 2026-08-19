"""Bandeja global de adjuntos recibidos por mensajeria.

Muestra los archivos que los clientes han enviado al despacho a traves de
la aplicacion Flutter. Los datos proceden de la tabla local
mensajeria_adjuntos_entrada, que el worker del NAS mantiene actualizada.
"""

from __future__ import annotations

import os
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk

_LABEL_ESTADO = {
    "pendiente_clasificar": "Pendiente",
    "revisado": "Revisado",
    "no_guardar": "No guardar",
    "error": "Error",
}

_COL_ANCHO = {
    "fecha": 135,
    "empresa": 90,
    "remitente": 120,
    "nombre_original": 200,
    "estado": 90,
    "tamano": 70,
}

_AVISO_TITLE = "Gest2A3Eco \u2014 Documentos recibidos"


def _fmt_tamano(bytes_: int | None) -> str:
    if not bytes_:
        return ""
    for unidad, umbral in [("MB", 1_048_576), ("KB", 1_024)]:
        if bytes_ >= umbral:
            return f"{bytes_ / umbral:.1f}\u00a0{unidad}"
    return f"{bytes_}\u00a0B"


def _fmt_fecha(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return iso[:16].replace("T", " ")
    except Exception:
        return str(iso)


class UIAdjuntosMensajeria(ttk.Frame):
    """Panel embebible: bandeja global de adjuntos de mensajeria."""

    def __init__(
        self,
        parent,
        gestor,
        on_ir_gestion_documental=None,
        usuario_activo: str = "",
        codigo_empresa_filtro: str | None = None,
    ):
        super().__init__(parent)
        self._gestor = gestor
        self._on_ir_gestion = on_ir_gestion_documental
        self._usuario = usuario_activo
        self._filtro_empresa = codigo_empresa_filtro
        self._cache: list[dict] = []
        self._selected_id: str | None = None
        self._aviso_ids: set[str] = set()
        self._build_ui()
        self.recargar()

    # ── Construccion de la interfaz ───────────────────────────────────────────

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Toolbar
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
        ttk.Button(bar, text="Actualizar", command=self.recargar).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(bar, text="Abrir archivo", command=self._abrir_archivo).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Ir a Gestion documental", command=self._ir_gestion).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(bar, text="Marcar revisado", command=self._marcar_revisado).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="No guardar", command=self._no_guardar).pack(side=tk.LEFT, padx=2)
        self._lbl_contador = ttk.Label(bar, text="")
        self._lbl_contador.pack(side=tk.RIGHT, padx=6)

        # Tabla
        cols = ("fecha", "empresa", "remitente", "nombre_original", "estado", "tamano")
        headers = ("Fecha", "Empresa", "Remitente", "Nombre del archivo", "Estado", "Tama\u00f1o")
        self._tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        for col, header in zip(cols, headers):
            self._tree.heading(col, text=header)
            self._tree.column(col, width=_COL_ANCHO.get(col, 100), minwidth=50, stretch=(col == "nombre_original"))
        ysb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=ysb.set)
        self._tree.grid(row=1, column=0, sticky="nsew", padx=(4, 0), pady=4)
        ysb.grid(row=1, column=1, sticky="ns", pady=4)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", lambda _e: self._abrir_archivo())
        self._tree.tag_configure("pendiente", foreground="#c05000")

    # ── Logica de refresco ────────────────────────────────────────────────────

    def recargar(self) -> None:
        """Recarga la lista desde PostgreSQL y lanza avisos de Windows si procede."""
        def _bg():
            try:
                filtro = {"codigo_empresa": self._filtro_empresa} if self._filtro_empresa else None
                datos = self._gestor.listar_adjuntos_mensajeria(filtro)
                pendientes = sum(1 for d in datos if not d.get("revisado"))
                nuevos = [d for d in datos if not d.get("aviso_mostrado") and not d.get("revisado")]
            except Exception:
                datos, pendientes, nuevos = [], 0, []
            self.after(0, lambda: self._actualizar_ui(datos, pendientes, nuevos))
        threading.Thread(target=_bg, daemon=True).start()

    def _actualizar_ui(self, datos: list[dict], pendientes: int, nuevos: list[dict]) -> None:
        prev = self._selected_id
        self._cache = datos
        for item in self._tree.get_children():
            self._tree.delete(item)
        for d in datos:
            tags = ("pendiente",) if not d.get("revisado") else ()
            self._tree.insert("", "end", iid=d["id"], tags=tags, values=(
                _fmt_fecha(d.get("created_at")),
                d.get("codigo_empresa", ""),
                d.get("remitente", ""),
                d.get("nombre_original", ""),
                _LABEL_ESTADO.get(d.get("estado", ""), d.get("estado", "")),
                _fmt_tamano(d.get("tamano")),
            ))
        if prev and self._tree.exists(prev):
            self._tree.selection_set(prev)
            self._selected_id = prev
        else:
            self._selected_id = None
        txt = f"Pendientes: {pendientes}" if pendientes else "Sin pendientes"
        self._lbl_contador.configure(text=txt)
        self._lanzar_avisos(nuevos)

    def _lanzar_avisos(self, nuevos: list[dict]) -> None:
        """Muestra aviso de Windows una sola vez por adjunto nuevo."""
        for d in nuevos:
            aid = d["id"]
            if aid in self._aviso_ids:
                continue
            self._aviso_ids.add(aid)
            try:
                from win10toast_click import ToastNotifier  # type: ignore
                ToastNotifier().show_toast(
                    _AVISO_TITLE,
                    f"Nuevo adjunto de {d.get('remitente', 'cliente')}: {d.get('nombre_original', '')}",
                    duration=6, threaded=True,
                )
            except Exception:
                pass
            try:
                self._gestor.marcar_aviso_adjunto_mensajeria(aid)
            except Exception:
                pass

    # ── Seleccion ─────────────────────────────────────────────────────────────

    def _on_select(self, _event=None) -> None:
        sel = self._tree.selection()
        self._selected_id = sel[0] if sel else None

    def _item_seleccionado(self) -> dict | None:
        if not self._selected_id:
            return None
        return next((d for d in self._cache if d["id"] == self._selected_id), None)

    # ── Acciones ──────────────────────────────────────────────────────────────

    def _abrir_archivo(self) -> None:
        item = self._item_seleccionado()
        if not item:
            messagebox.showinfo("Sin seleccion", "Selecciona un adjunto de la lista.")
            return
        ruta = item.get("ruta_entrada", "")
        if not ruta or not os.path.exists(ruta):
            messagebox.showwarning("Archivo no disponible", f"El archivo no se encuentra en:\n{ruta}")
            return
        try:
            os.startfile(ruta)
        except Exception:
            try:
                subprocess.Popen(["explorer", "/select,", ruta])
            except Exception as exc:
                messagebox.showerror("Error", f"No se pudo abrir el archivo:\n{exc}")

    def _ir_gestion(self) -> None:
        item = self._item_seleccionado()
        if not item:
            messagebox.showinfo("Sin seleccion", "Selecciona un adjunto de la lista.")
            return
        if self._on_ir_gestion:
            self._on_ir_gestion(item["codigo_empresa"])
        else:
            messagebox.showinfo(
                "Gestion documental",
                f"Empresa: {item.get('codigo_empresa', '')}\n"
                f"Abre el modulo de Gestion documental para esta empresa.",
            )

    def _marcar_revisado(self) -> None:
        item = self._item_seleccionado()
        if not item:
            messagebox.showinfo("Sin seleccion", "Selecciona un adjunto de la lista.")
            return
        if item.get("revisado"):
            messagebox.showinfo("Ya revisado", "Este adjunto ya ha sido marcado como revisado.")
            return
        if not messagebox.askyesno("Confirmar", "Marcar este adjunto como revisado?"):
            return
        try:
            self._gestor.marcar_adjunto_mensajeria_revisado(
                item["id"], revisado_por=self._usuario or "sistema",
            )
            self.recargar()
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo marcar como revisado:\n{exc}")

    def _no_guardar(self) -> None:
        item = self._item_seleccionado()
        if not item:
            messagebox.showinfo("Sin seleccion", "Selecciona un adjunto de la lista.")
            return
        if item.get("revisado"):
            messagebox.showinfo("Ya procesado", "Este adjunto ya fue procesado.")
            return
        if not messagebox.askyesno(
            "No guardar",
            "Registrar que se ha decidido NO guardar este adjunto?\n"
            "La trazabilidad se conserva aunque no se archive el documento.",
        ):
            return
        try:
            self._gestor.no_guardar_adjunto_mensajeria(
                item["id"], revisado_por=self._usuario or "sistema",
            )
            self.recargar()
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo registrar la decision:\n{exc}")

    def obtener_contador_pendientes(self) -> int:
        """Devuelve el numero de adjuntos no revisados (para mostrar en la navegacion)."""
        try:
            return self._gestor.contar_adjuntos_mensajeria_pendientes(self._filtro_empresa)
        except Exception:
            return 0
