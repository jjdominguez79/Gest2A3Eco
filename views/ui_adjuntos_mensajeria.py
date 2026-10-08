"""Bandeja global de entradas documentales pendientes.

Reune los correos con adjuntos de los buzones compartidos y los archivos
enviados por clientes desde Flutter. Ambos canales se clasifican hacia el
mismo archivo documental y el mismo circuito OCR.
"""

from __future__ import annotations

import os
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from services.gestion_documental_service import GestionDocumentalService

_LABEL_ESTADO = {
    "pendiente_clasificar": "Pendiente",
    "archivado": "Archivado",
    "revisado": "Revisado",
    "no_guardar": "No guardar",
    "error": "Error",
}

_COL_ANCHO = {
    "fecha": 135,
    "empresa": 78,
    "empresa_nombre": 180,
    "responsable": 125,
    "canal": 145,
    "remitente": 120,
    "nombre_original": 200,
    "estado": 90,
    "tamano": 70,
}

_ORIGENES_FILTRO = (
    "Correo Oficina",
    "Correo Documentacion",
    "Mensajeria",
)

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


def _etiqueta_origen(item: dict) -> str:
    return str(
        item.get("origen_label") or item.get("canal") or "Mensajeria"
    )


def _origen_para_filtro(item: dict) -> str:
    etiqueta = _etiqueta_origen(item)
    canal = str(item.get("canal") or "").strip().casefold()
    if etiqueta.casefold().startswith("mensajeria") or canal in {
        "mensajeria", "chat",
    }:
        return "Mensajeria"
    return etiqueta


def _opciones_origen(datos: list[dict]) -> tuple[str, ...]:
    disponibles = {_origen_para_filtro(item) for item in datos}
    extras = sorted(disponibles.difference(_ORIGENES_FILTRO))
    return ("Todos", *_ORIGENES_FILTRO, *extras)


def _resumen_pendientes_por_origen(datos: list[dict]) -> dict[str, int]:
    """Cuenta la cola documental pendiente con las mismas reglas del filtro."""
    resumen = {origen: 0 for origen in _ORIGENES_FILTRO}
    for item in datos:
        origen = _origen_para_filtro(item)
        resumen[origen] = resumen.get(origen, 0) + 1
    return resumen


def _consultar_bandeja_documental(
    gestor, codigo_empresa: str | None, *,
    solo_pendientes: bool, solo_archivadas: bool,
) -> tuple[list[dict], int, dict[str, int]]:
    """Lee la bandeja en una conexion nueva para evitar datos obsoletos."""
    lector = gestor
    crear_lector = getattr(gestor, "crear_sesion_lectura", None)
    if callable(crear_lector):
        lector = crear_lector()
    try:
        filtro = {
            "codigo_empresa": codigo_empresa,
            "solo_pendientes": solo_pendientes,
            "estado": "archivado" if solo_archivadas else "",
        }
        if hasattr(lector, "listar_entradas_documentales"):
            datos = lector.listar_entradas_documentales(
                codigo_empresa or "",
                solo_pendientes=solo_pendientes,
                solo_archivadas=solo_archivadas,
            )
            datos_pendientes = (
                datos if solo_pendientes else
                lector.listar_entradas_documentales(
                    codigo_empresa or "", solo_pendientes=True,
                )
            )
            pendientes = len(datos_pendientes)
        else:
            datos = lector.listar_adjuntos_mensajeria(filtro)
            pendientes = lector.contar_adjuntos_mensajeria_pendientes(
                codigo_empresa,
            )
            datos_pendientes = datos if solo_pendientes else []
        return (
            datos,
            pendientes,
            _resumen_pendientes_por_origen(datos_pendientes),
        )
    finally:
        if lector is not gestor:
            cerrar = getattr(lector, "cerrar", None)
            if callable(cerrar):
                cerrar()
            else:
                conn = getattr(lector, "conn", None)
                if conn is not None:
                    conn.close()


class UIAdjuntosMensajeria(ttk.Frame):
    """Panel compatible que unifica correo y mensajeria en una sola bandeja."""

    def __init__(
        self,
        parent,
        gestor,
        on_ir_gestion_documental=None,
        on_count_changed=None,
        usuario_activo: str = "",
        usuario_id: int = 0,
        codigo_empresa_filtro: str | None = None,
    ):
        super().__init__(parent)
        self._gestor = gestor
        self._on_ir_gestion = on_ir_gestion_documental
        self._on_count_changed = on_count_changed
        self._usuario = usuario_activo
        self._usuario_id = int(usuario_id or 0)
        self._filtro_empresa = codigo_empresa_filtro
        self._cache: list[dict] = []
        self._selected_id: str | None = None
        self._refresh_generation = 0
        self._service = GestionDocumentalService(gestor)
        self._build_ui()
        self.recargar()

    # ── Construccion de la interfaz ───────────────────────────────────────────

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Toolbar
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
        ttk.Label(bar, text="Mostrar").pack(side=tk.LEFT, padx=(2, 4))
        self._estado_filtro = tk.StringVar(value="Pendientes")
        estado = ttk.Combobox(
            bar, textvariable=self._estado_filtro, state="readonly", width=13,
            values=("Pendientes", "Archivadas", "Todos"),
        )
        estado.pack(side=tk.LEFT, padx=(0, 8))
        estado.bind("<<ComboboxSelected>>", lambda _event: self.recargar())
        ttk.Label(bar, text="Origen").pack(side=tk.LEFT, padx=(2, 4))
        self._origen_filtro = tk.StringVar(value="Todos")
        self._origen_combo = ttk.Combobox(
            bar, textvariable=self._origen_filtro, state="readonly", width=22,
            values=("Todos", *_ORIGENES_FILTRO),
        )
        self._origen_combo.pack(side=tk.LEFT, padx=(0, 8))
        self._origen_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._aplicar_filtro_origen(),
        )
        ttk.Button(bar, text="Actualizar", command=self.recargar).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(
            bar, text="Revisar adjuntos", command=self._abrir_archivo,
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Ir a Gestion documental", command=self._ir_gestion).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Button(bar, text="Clasificar", command=self._clasificar).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="No guardar", command=self._no_guardar).pack(side=tk.LEFT, padx=2)
        self._lbl_contador = ttk.Label(bar, text="")
        self._lbl_contador.pack(side=tk.RIGHT, padx=6)

        # Tabla
        cols = (
            "fecha", "empresa", "empresa_nombre", "responsable", "canal",
            "remitente", "nombre_original", "estado", "tamano",
        )
        headers = (
            "Fecha", "Codigo", "Cliente", "Responsable", "Origen",
            "Remitente", "Documento", "Estado", "Tama\u00f1o",
        )
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
        """Recarga la lista desde PostgreSQL."""
        self._refresh_generation += 1
        generation = self._refresh_generation
        estado_filtro = self._estado_filtro.get()
        solo_pendientes = estado_filtro == "Pendientes"
        solo_archivadas = estado_filtro == "Archivadas"
        def _bg():
            try:
                datos, pendientes, resumen = _consultar_bandeja_documental(
                    self._gestor,
                    self._filtro_empresa,
                    solo_pendientes=solo_pendientes,
                    solo_archivadas=solo_archivadas,
                )
                error = None
            except Exception as exc:
                datos, pendientes, resumen, error = [], 0, {}, exc
            self.after(
                0,
                lambda: self._actualizar_ui(
                    datos, pendientes, resumen, error, generation,
                ),
            )
        threading.Thread(target=_bg, daemon=True).start()

    def _actualizar_ui(
        self, datos: list[dict], pendientes: int,
        resumen: dict[str, int] | None = None, error=None,
        generation: int | None = None,
    ) -> None:
        if generation is not None and generation != self._refresh_generation:
            return
        self._cache = datos
        valores_origen = _opciones_origen(datos)
        self._origen_combo["values"] = valores_origen
        if self._origen_filtro.get() not in valores_origen:
            self._origen_filtro.set("Todos")
        self._aplicar_filtro_origen()
        resumen = resumen or {}
        txt = (
            f"Pendientes: {pendientes}  |  "
            f"Oficina: {resumen.get('Correo Oficina', 0)}  |  "
            f"Documentacion: {resumen.get('Correo Documentacion', 0)}  |  "
            f"Mensajeria: {resumen.get('Mensajeria', 0)}"
        )
        self._lbl_contador.configure(text=txt)
        if self._on_count_changed:
            self._on_count_changed(pendientes)
        if error is not None:
            messagebox.showerror(
                "Documentos recibidos",
                f"No se pudo actualizar la bandeja:\n{error}",
                parent=self,
            )

    @staticmethod
    def _filtrar_por_origen(datos: list[dict], origen: str) -> list[dict]:
        if not origen or origen == "Todos":
            return list(datos)
        return [item for item in datos if _origen_para_filtro(item) == origen]

    def _aplicar_filtro_origen(self) -> None:
        prev = self._selected_id
        datos = self._filtrar_por_origen(
            self._cache, self._origen_filtro.get(),
        )
        for item in self._tree.get_children():
            self._tree.delete(item)
        for d in datos:
            tags = ("pendiente",) if not d.get("revisado") else ()
            self._tree.insert("", "end", iid=d["id"], tags=tags, values=(
                _fmt_fecha(d.get("fecha") or d.get("created_at")),
                d.get("codigo_empresa", ""),
                d.get("empresa_nombre", ""),
                d.get("responsable", ""),
                _etiqueta_origen(d),
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
            messagebox.showinfo("Sin seleccion", "Selecciona una entrada de la lista.")
            return
        ruta = item.get("ruta_entrada", "")
        if item.get("canal") == "correo":
            self._revisar_adjuntos_correo(item)
            return
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

    def _revisar_adjuntos_correo(self, item: dict) -> None:
        """Consulta los adjuntos sin archivarlos y muestra la lista de revision."""
        self.winfo_toplevel().configure(cursor="watch")

        def _bg():
            try:
                attachments = self._service.listar_adjuntos_entrada_correo(item)
                error = None
            except Exception as exc:
                attachments, error = [], exc
            try:
                self.after(
                    0, self._mostrar_adjuntos_correo,
                    item, attachments, error,
                )
            except (RuntimeError, tk.TclError):
                pass

        threading.Thread(target=_bg, daemon=True).start()

    def _mostrar_adjuntos_correo(
        self, item: dict, attachments: list[dict], error=None,
    ) -> None:
        self.winfo_toplevel().configure(cursor="")
        if error is not None:
            messagebox.showerror(
                "Revisar adjuntos",
                f"No se pudieron consultar los adjuntos:\n{error}",
                parent=self,
            )
            return
        if not attachments:
            messagebox.showinfo(
                "Revisar adjuntos",
                "El correo no tiene adjuntos descargables.",
                parent=self,
            )
            return

        # Se reutiliza el visor seguro del buzon: solo descarga una copia
        # temporal cuando el usuario abre un adjunto y no archiva nada.
        from views.ui_comunicaciones_global import AttachmentPreviewDialog

        AttachmentPreviewDialog(
            self,
            attachments,
            on_open=lambda attachment_id: self._abrir_adjunto_correo(
                item, attachment_id,
            ),
        )

    def _abrir_adjunto_correo(self, item: dict, attachment_id: str) -> None:
        self.winfo_toplevel().configure(cursor="watch")

        def _bg():
            try:
                from services.documentos_correo_service import DocumentosCorreoService

                path = DocumentosCorreoService(
                    self._gestor,
                ).descargar_adjunto_temporal(
                    mailbox=str(item.get("mailbox") or ""),
                    graph_message_id=str(
                        item.get("graph_message_id")
                        or item.get("entrada_id")
                        or ""
                    ),
                    attachment_id=attachment_id,
                )
                error = None
            except Exception as exc:
                path, error = None, exc
            try:
                self.after(0, self._finalizar_apertura_adjunto, path, error)
            except (RuntimeError, tk.TclError):
                pass

        threading.Thread(target=_bg, daemon=True).start()

    def _finalizar_apertura_adjunto(self, path, error=None) -> None:
        self.winfo_toplevel().configure(cursor="")
        if error is not None:
            messagebox.showerror(
                "Revisar adjuntos",
                f"No se pudo abrir el adjunto:\n{error}",
                parent=self,
            )
            return
        try:
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror(
                "Revisar adjuntos",
                f"Windows no pudo abrir el archivo:\n{exc}",
                parent=self,
            )

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

    def _clasificar(self) -> None:
        item = self._item_seleccionado()
        if not item:
            messagebox.showinfo("Sin seleccion", "Selecciona un adjunto de la lista.")
            return
        if item.get("revisado"):
            messagebox.showinfo("Ya procesado", "Este adjunto ya fue procesado.")
            return
        from views.ui_gestion_documental import _CategoryDialog

        categorias = self._service.categorias()
        dialog = _CategoryDialog(self, [row["nombre"] for row in categorias])
        self.wait_window(dialog)
        if not dialog.result:
            return
        categoria = next(row for row in categorias if row["nombre"] == dialog.result)
        empresas = [
            row for row in self._gestor.listar_empresas()
            if str(row.get("codigo") or "") == str(item.get("codigo_empresa") or "")
        ]
        ejercicio = max((int(row.get("ejercicio") or 0) for row in empresas), default=0)
        if not ejercicio:
            messagebox.showerror(
                "Clasificar", "No se encontro un ejercicio para este cliente.", parent=self,
            )
            return
        selecciones_adjuntos = None
        if item.get("canal") == "correo":
            try:
                opciones = self._service.listar_opciones_clasificacion_correo(item)
            except Exception as exc:
                messagebox.showerror(
                    "Clasificar", f"No se pudieron consultar los adjuntos:\n{exc}",
                    parent=self,
                )
                return
            from views.ui_comunicaciones_global import AttachmentContentSelectionDialog
            selector = AttachmentContentSelectionDialog(self, opciones)
            self.wait_window(selector)
            selecciones_adjuntos = selector.result
            if not selecciones_adjuntos:
                return
        try:
            summary = self._service.clasificar_entrada_documental(
                item, ejercicio=ejercicio, categoria_id=categoria["id"],
                usuario=self._usuario or "sistema", usuario_id=self._usuario_id,
                selecciones_adjuntos=selecciones_adjuntos,
            )
            self.recargar()
            if summary.warnings:
                messagebox.showwarning(
                    "Clasificar",
                    "Documento incorporado a Gestion documental.\n\n"
                    + "\n".join(summary.warnings),
                    parent=self,
                )
            else:
                messagebox.showinfo(
                    "Clasificar", "Documento incorporado a Gestion documental.", parent=self,
                )
        except Exception as exc:
            messagebox.showerror("Clasificar", str(exc), parent=self)

    def _no_guardar(self) -> None:
        item = self._item_seleccionado()
        if not item:
            messagebox.showinfo("Sin seleccion", "Selecciona un adjunto de la lista.")
            return
        if item.get("revisado"):
            messagebox.showinfo("Ya procesado", "Este adjunto ya fue procesado.")
            return
        if item.get("canal") == "correo":
            if not messagebox.askyesno(
                "No guardar",
                "Registrar que no se guardara ningun adjunto de este correo?\n"
                "El correo se marcara como gestionado y leido en Outlook.",
                parent=self,
            ):
                return
            try:
                summary = self._service.no_guardar_entrada_correo(
                    item, usuario=self._usuario or "sistema",
                    usuario_id=self._usuario_id,
                )
                self.recargar()
                if summary.warnings:
                    messagebox.showwarning(
                        "No guardar", "\n".join(summary.warnings), parent=self,
                    )
            except Exception as exc:
                messagebox.showerror(
                    "No guardar", f"No se pudo cerrar el correo:\n{exc}",
                    parent=self,
                )
            return
        if not messagebox.askyesno(
            "No guardar",
            "Registrar que se ha decidido NO guardar este adjunto?\n"
            "La trazabilidad se conserva aunque no se archive el documento.",
        ):
            return
        try:
            self._gestor.no_guardar_adjunto_mensajeria(
                str(item.get("entrada_id") or item["id"]),
                revisado_por=self._usuario or "sistema",
            )
            ruta = Path(str(item.get("ruta_entrada") or ""))
            if ruta.is_file():
                try:
                    ruta.unlink()
                except OSError as exc:
                    messagebox.showwarning(
                        "No guardar",
                        "La decision se ha registrado, pero no se pudo eliminar "
                        f"la copia temporal:\n{exc}",
                        parent=self,
                    )
            self.recargar()
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo registrar la decision:\n{exc}")

    def obtener_contador_pendientes(self) -> int:
        """Devuelve el numero total de entradas documentales pendientes."""
        try:
            if hasattr(self._gestor, "listar_entradas_documentales"):
                return len(self._gestor.listar_entradas_documentales(
                    self._filtro_empresa or "", solo_pendientes=True,
                ))
            return self._gestor.contar_adjuntos_mensajeria_pendientes(self._filtro_empresa)
        except Exception:
            return 0
