"""
Vista unificada del modulo OCR de facturas recibidas.

Arquitectura: listado + zona de revision vertical
  Izquierda — listado de documentos por bandeja (Notebook con pestanas)
  Derecha   — vista previa amplia arriba y formulario desplazable debajo

Puntos de integracion:
  - services/ocr/OcrService       — procesamiento OCR tipado
  - services/ocr_recibidas_service — generacion suenlace.dat (flujo existente)
  - models/gestor_sqlite           — persistencia
  - controllers/ui_ocr_facturas_controller — logica existente de bandejas

Esta pantalla complementa (no reemplaza) ui_ocr_facturas.py + ui_ocr_detalle.py.
"""
from __future__ import annotations

import logging
import json
import queue
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from services.terceros_empresa_fiscal_service import PROVEEDOR_TIPOS_IVA
from services.terceros_ocr_service import TercerosOcrService
from utils.utilidades import load_app_config, save_app_config
from utils.validaciones import normalizar_nif_cif

logger = logging.getLogger(__name__)


def _normalizar_confianza(value) -> float:
    """Normaliza valores de confianza de SQLite/Azure para mostrarlos en UI."""
    try:
        raw = str(value or "").strip().replace(",", ".")
        is_percentage = raw.endswith("%")
        if is_percentage:
            raw = raw[:-1].strip()
        confidence = float(raw) if raw else 0.0
        if is_percentage or confidence > 1:
            confidence /= 100.0
        return max(0.0, min(confidence, 1.0))
    except (TypeError, ValueError):
        return 0.0


def _parse_importe(value) -> float:
    raw = str(value or "").strip().replace("€", "")
    if not raw:
        return 0.0
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    return float(raw)

# Bandejas de estado
BANDEJAS = [
    ("procesando",             "Procesando"),
    ("error",                  "Errores"),
    ("pendiente_revision",     "Pte. revision"),
    ("pendiente_contabilizar", "Pte. contabilizar"),
    ("contabilizada",          "Contabilizadas"),
]

COLS_LISTA = [
    ("nombre_archivo",   "Documento",   160, "w"),
    ("proveedor_nombre", "Proveedor",   160, "w"),
    ("nif_proveedor",    "NIF",          90, "w"),
    ("numero_factura",   "Factura",     100, "w"),
    ("fecha_factura",    "Fecha",        85, "w"),
    ("total_factura",    "Total",        80, "e"),
    ("numero_asiento",   "Asiento A3",   90, "w"),
    ("motor_ocr",        "Motor",        75, "w"),
    ("confianza_global", "Conf.",        55, "e"),
    ("estado",           "Estado",       90, "w"),
]
COL_IDS = [c[0] for c in COLS_LISTA]


class UIFacturasRecibidasOcr(ttk.Frame):
    """
    Vista principal del modulo OCR de facturas recibidas.

    Parametros:
      master        — widget padre (normalmente el area de contenido del dashboard)
      gestor        — instancia de GestorSQLite
      codigo_empresa
      ejercicio
      nombre_empresa
      session       — sesion de usuario (para registrar correcciones)
    """

    def __init__(
        self,
        master,
        gestor,
        codigo_empresa: str,
        ejercicio: int,
        nombre_empresa: str,
        session=None,
    ):
        super().__init__(master)
        self._gestor    = gestor
        self._codigo    = codigo_empresa
        # El listado OCR tipado trabaja por empresa_id; es el mismo codigo
        # interno de la empresa, pero debe conservarse como atributo propio.
        self._empresa_id = codigo_empresa
        self._ejercicio = ejercicio
        self._nombre    = nombre_empresa
        self._session   = session
        self._ocr_q: queue.Queue = queue.Queue()
        self._ocr_thread: threading.Thread | None = None
        self._doc_seleccionado: dict | None = None
        self._factura_seleccionada: dict | None = None
        self._terceros_svc = TercerosOcrService()
        self._terceros_por_etiqueta: dict[str, dict] = {}
        self._proveedor_id_seleccionado = ""
        self._cuentas_plan_por_etiqueta: dict[str, str] = {}
        self._revision_window: tk.Toplevel | None = None
        self._editor_activo = False
        self._entries: dict[str, tk.Variable] = {}
        self._campo_marcado_var = tk.StringVar(value="ProveedorNif")
        self._marcas_campos: dict[str, dict] = {}
        self._marca_inicio: tuple[float, float] | None = None
        self._marca_rect_id = None

        self._build()
        self.after_idle(self._refresh_all)

    # ── Construccion de la UI ─────────────────────────────────────────────────

    def _build(self):
        # Cabecera
        hdr = ttk.Frame(self)
        hdr.pack(fill="x", padx=10, pady=(8, 4))
        ttk.Label(
            hdr,
            text=f"Captura documental OCR  —  {self._nombre} ({self._codigo})",
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left")
        btn_frame = ttk.Frame(hdr)
        btn_frame.pack(side="right")
        ttk.Button(
            btn_frame, text="Importar PDF / imagen",
            style="Primary.TButton",
            command=self._importar,
        ).pack(side="left", padx=4)
        ttk.Button(
            btn_frame, text="Reprocesar seleccionado",
            command=self._reprocesar_seleccionado,
        ).pack(side="left", padx=4)
        ttk.Button(
            btn_frame, text="Aprendizaje",
            command=self._mostrar_estado_aprendizaje,
        ).pack(side="left", padx=4)

        # La pantalla inicial solo es el listado de estados. La revision se
        # abre en una ventana propia al seleccionar una factura.
        lista = ttk.Frame(self)
        lista.pack(fill="both", expand=True, padx=10, pady=4)
        self._build_bandejas(lista)

        # Barra de estado
        self._lbl_status = ttk.Label(self, text="", foreground="#555")
        self._lbl_status.pack(fill="x", padx=10, pady=(0, 6))

    def _crear_editor_desplazable(self, parent: ttk.Frame) -> ttk.Frame:
        """Crea un formulario vertical desplazable para no comprimir sus campos."""
        canvas = tk.Canvas(parent, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        contenido = ttk.Frame(canvas)
        ventana = canvas.create_window((0, 0), window=contenido, anchor="nw")

        def _actualizar_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _ajustar_ancho(event):
            canvas.itemconfigure(ventana, width=event.width)

        contenido.bind("<Configure>", _actualizar_region)
        canvas.bind("<Configure>", _ajustar_ancho)
        # La rueda actua solo mientras el cursor esta sobre el formulario.
        canvas.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))
        self._editor_canvas = canvas
        return contenido

    def _configurar_ocr(self):
        """Configura Azure Document Intelligence sin exponer la clave en la pantalla."""
        dialog = tk.Toplevel(self)
        dialog.title("Configuracion OCR")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill="both", expand=True)
        cfg = load_app_config()
        motor = tk.StringVar(value=str(cfg.get("ocr_motor_activo") or ""))
        endpoint = tk.StringVar(value=str(cfg.get("azure_doc_intelligence_endpoint") or ""))
        key = tk.StringVar(value=str(cfg.get("azure_doc_intelligence_key") or ""))
        model_id = tk.StringVar(value=str(cfg.get("azure_doc_intelligence_model_id") or ""))
        ttk.Label(frame, text="Motor OCR").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(frame, textvariable=motor, state="readonly", values=("", "azure"), width=42).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=3)
        ttk.Label(frame, text="Endpoint Azure").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=endpoint, width=55).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)
        ttk.Label(frame, text="Clave Azure").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=key, show="*", width=55).grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=3)
        ttk.Label(frame, text="ID modelo personalizado").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=model_id, width=55).grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=3)
        ttk.Label(
            frame,
            text=("Deja el ID vacio para usar prebuilt-invoice. Indica el ID de un "
                  "modelo personalizado entrenado con facturas etiquetadas para "
                  "usar sus campos. Los documentos se enviaran a Azure para su analisis."),
            wraplength=520, foreground="#555",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

        def save():
            selected = motor.get().strip().lower()
            if selected == "azure" and (not endpoint.get().strip() or not key.get().strip()):
                messagebox.showwarning("OCR", "Indica endpoint y clave de Azure.", parent=dialog)
                return
            cfg["ocr_motor_activo"] = selected
            cfg["azure_doc_intelligence_endpoint"] = endpoint.get().strip()
            cfg["azure_doc_intelligence_key"] = key.get().strip()
            cfg["azure_doc_intelligence_model_id"] = model_id.get().strip()
            save_app_config(cfg)
            dialog.destroy()
            self._lbl_status.configure(text="Configuracion OCR guardada. Los documentos nuevos usaran el motor seleccionado.")

        actions = ttk.Frame(frame)
        actions.grid(row=5, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Cancelar", command=dialog.destroy).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Guardar", command=save).pack(side="left")
        frame.columnconfigure(1, weight=1)

    def _build_bandejas(self, parent: ttk.Frame):
        self._nb = ttk.Notebook(parent)
        self._nb.pack(fill="both", expand=True)
        self._tvs: dict[str, ttk.Treeview] = {}

        for estado, titulo in BANDEJAS:
            frame = ttk.Frame(self._nb)
            self._nb.add(frame, text=titulo)

            # Toolbar de bandeja
            bar = ttk.Frame(frame)
            bar.pack(fill="x", padx=4, pady=(4, 2))
            self._build_bandeja_toolbar(bar, estado)

            # Treeview
            # En "Contabilizadas" se pueden seleccionar varias facturas para
            # capturar sus numeros de asiento desde A3 de una sola vez.
            tv = ttk.Treeview(frame, columns=COL_IDS, show="headings", selectmode="extended")
            for col_id, titulo_col, w, anchor in COLS_LISTA:
                tv.heading(col_id, text=titulo_col)
                tv.column(col_id, width=w, anchor=anchor, stretch=(col_id == "proveedor_nombre"))
            vsb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
            tv.configure(yscrollcommand=vsb.set)
            vsb.pack(side="right", fill="y")
            tv.pack(fill="both", expand=True, padx=4, pady=(0, 4))

            tv.tag_configure("row_error", foreground="#c0392b")
            tv.tag_configure("row_ok",    foreground="#27ae60")
            tv.bind("<<TreeviewSelect>>", lambda _e, est=estado: self._on_select(est))
            tv.bind("<Double-1>", lambda _e, est=estado: self._abrir_seleccionado(est))

            self._tvs[estado] = tv

        self._nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _build_bandeja_toolbar(self, bar: ttk.Frame, estado: str):
        if estado == "procesando":
            ttk.Label(bar, text="Procesamiento automatico al importar.").pack(side="left")
            return
        if estado == "error":
            ttk.Button(bar, text="Reprocesar",
                       command=self._reprocesar_seleccionado).pack(side="left", padx=2)
            ttk.Button(bar, text="Eliminar", style="Danger.TButton",
                       command=lambda: self._eliminar(estado)).pack(side="left", padx=2)
        elif estado == "pendiente_revision":
            ttk.Button(bar, text="Validar", style="Primary.TButton",
                       command=self._validar_seleccionado).pack(side="left", padx=2)
            ttk.Button(bar, text="Enviar a errores",
                       command=lambda: self._enviar_a_error(estado)).pack(side="left", padx=2)
            ttk.Button(bar, text="Eliminar", style="Danger.TButton",
                       command=lambda: self._eliminar(estado)).pack(side="left", padx=2)
        elif estado == "pendiente_contabilizar":
            ttk.Label(
                bar, text="Documento enviado a Contabilidad. Genera alli el suenlace.dat."
            ).pack(side="left", padx=2)
            ttk.Button(bar, text="Enviar a errores",
                       command=lambda: self._enviar_a_error(estado)).pack(side="left", padx=2)
        elif estado == "contabilizada":
            ttk.Label(
                bar, text="Exportada a suenlace.dat. Importala en A3 y captura el asiento para confirmarla."
            ).pack(side="left", padx=2)
            ttk.Button(
                bar, text="Capturar asiento de A3", style="Primary.TButton",
                command=self._capturar_asiento_a3,
            ).pack(side="left", padx=6)

    def _build_editor(self, parent: ttk.Frame):
        """Panel derecho: cabecera, IVA y retenciones del documento seleccionado."""
        ttk.Label(
            parent, text="Revision y edicion del documento",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=8, pady=(6, 2))

        # Seccion cabecera
        cab = ttk.LabelFrame(parent, text="Cabecera de factura")
        cab.pack(fill="x", padx=8, pady=4)
        self._entries: dict[str, tk.Variable] = {}
        campos = [
            ("nif_proveedor",    "NIF proveedor"),
            ("nombre_proveedor", "Nombre proveedor"),
            ("numero_factura",   "Numero factura"),
            ("fecha_factura",    "Fecha factura (YYYY-MM-DD)"),
            ("fecha_vencimiento","Vencimiento (YYYY-MM-DD)"),
            ("total_factura",    "Total factura"),
            ("base_total",       "Base total"),
            ("iva_total",        "IVA total"),
            ("retencion_total",  "Retencion total"),
        ]
        for row_idx, (campo, etiqueta) in enumerate(campos):
            ttk.Label(cab, text=etiqueta + ":").grid(row=row_idx, column=0, sticky="e", padx=4, pady=2)
            var = tk.StringVar()
            entry = ttk.Entry(cab, textvariable=var, width=28)
            entry.grid(row=row_idx, column=1, sticky="ew", padx=4, pady=2)
            self._entries[campo] = var
        cab.columnconfigure(1, weight=1)

        tercero_frame = ttk.LabelFrame(parent, text="Proveedor / acreedor (maestro)")
        tercero_frame.pack(fill="x", padx=8, pady=4)
        self._proveedor_var = tk.StringVar()
        self._cb_proveedor = ttk.Combobox(
            tercero_frame, textvariable=self._proveedor_var, state="normal", width=52,
        )
        self._cb_proveedor.grid(row=0, column=0, sticky="ew", padx=4, pady=3)
        self._cb_proveedor.bind("<<ComboboxSelected>>", self._seleccionar_proveedor_maestro)
        ttk.Button(tercero_frame, text="Buscar NIF", command=self._buscar_proveedor_maestro).grid(
            row=0, column=1, padx=3, pady=3
        )
        ttk.Button(tercero_frame, text="Alta proveedor / acreedor", command=self._alta_proveedor).grid(
            row=0, column=2, padx=(3, 4), pady=3
        )
        ttk.Label(tercero_frame, text="Tipo de operacion").grid(row=1, column=0, sticky="w", padx=4, pady=(2, 4))
        self._tipo_operacion_iva_var = tk.StringVar(value="INTERIOR_DEDUCIBLE")
        ttk.Combobox(
            tercero_frame, textvariable=self._tipo_operacion_iva_var,
            values=PROVEEDOR_TIPOS_IVA, state="readonly", width=30,
        ).grid(row=1, column=1, sticky="w", padx=3, pady=(2, 4))
        self._lbl_proveedor_maestro = ttk.Label(tercero_frame, text="", foreground="#555")
        self._lbl_proveedor_maestro.grid(row=1, column=2, sticky="w", padx=3, pady=(2, 4))
        ttk.Label(tercero_frame, text="Subcuenta del plan empresa").grid(
            row=2, column=0, sticky="w", padx=4, pady=(2, 4)
        )
        self._subcuenta_plan_var = tk.StringVar()
        self._cb_subcuenta_plan = ttk.Combobox(
            tercero_frame, textvariable=self._subcuenta_plan_var, state="readonly", width=42,
        )
        self._cb_subcuenta_plan.grid(row=2, column=1, columnspan=2, sticky="ew", padx=3, pady=(2, 4))
        ttk.Label(tercero_frame, text="Subcuenta de gastos del proveedor").grid(
            row=3, column=0, sticky="w", padx=4, pady=(2, 4)
        )
        self._subcuenta_gasto_var = tk.StringVar()
        self._cuentas_gasto_por_etiqueta = {}
        self._cb_subcuenta_gasto = ttk.Combobox(
            tercero_frame, textvariable=self._subcuenta_gasto_var, state="readonly", width=42,
        )
        self._cb_subcuenta_gasto.grid(row=3, column=1, columnspan=2, sticky="ew", padx=3, pady=(2, 4))
        tercero_frame.columnconfigure(0, weight=1)

        # Seccion lineas IVA
        iva_frame = ttk.LabelFrame(parent, text="Lineas de IVA")
        iva_frame.pack(fill="both", expand=True, padx=8, pady=4)
        iva_cols = ("tipo_iva", "base", "cuota_iva", "tipo_recargo", "cuota_recargo")
        self._tv_iva = ttk.Treeview(iva_frame, columns=iva_cols, show="headings", height=4)
        for c in iva_cols:
            self._tv_iva.heading(c, text=c.replace("_", " ").title())
            self._tv_iva.column(c, width=90, anchor="e")
        self._tv_iva.pack(fill="both", expand=True, padx=4, pady=4)
        self._tv_iva.bind("<<TreeviewSelect>>", self._cargar_linea_iva_en_editor)

        iva_editor = ttk.Frame(iva_frame)
        iva_editor.pack(fill="x", padx=4, pady=(0, 4))
        self._iva_vars = {
            "tipo_iva": tk.StringVar(value="21"),
            "base": tk.StringVar(),
            "cuota_iva": tk.StringVar(),
            "tipo_recargo": tk.StringVar(value="0"),
            "cuota_recargo": tk.StringVar(value="0"),
        }
        etiquetas = (
            ("tipo_iva", "Tipo IVA", 8), ("base", "Base", 10),
            ("cuota_iva", "Cuota IVA", 10), ("tipo_recargo", "Recargo", 8),
            ("cuota_recargo", "Cuota R.", 10),
        )
        for col, (campo, etiqueta, ancho) in enumerate(etiquetas):
            ttk.Label(iva_editor, text=etiqueta).grid(row=0, column=col, sticky="w", padx=2)
            if campo == "tipo_iva":
                widget = ttk.Combobox(
                    iva_editor, textvariable=self._iva_vars[campo],
                    values=("0", "4", "5", "10", "21"), width=ancho, state="normal",
                )
            else:
                widget = ttk.Entry(iva_editor, textvariable=self._iva_vars[campo], width=ancho)
            widget.grid(row=1, column=col, sticky="ew", padx=2)
        ttk.Button(iva_editor, text="Anadir / actualizar", command=self._guardar_linea_iva).grid(
            row=1, column=len(etiquetas), padx=(6, 2)
        )
        ttk.Button(iva_editor, text="Quitar", command=self._quitar_linea_iva).grid(
            row=1, column=len(etiquetas) + 1, padx=2
        )

        # Seccion retenciones
        ret_frame = ttk.LabelFrame(parent, text="Retenciones IRPF")
        ret_frame.pack(fill="x", padx=8, pady=4)
        ret_cols = ("base_retencion", "tipo_retencion", "importe_retencion", "clase_retencion")
        self._tv_ret = ttk.Treeview(ret_frame, columns=ret_cols, show="headings", height=2)
        for c in ret_cols:
            self._tv_ret.heading(c, text=c.replace("_", " ").title())
            self._tv_ret.column(c, width=100, anchor="e")
        self._tv_ret.pack(fill="both", expand=True, padx=4, pady=4)

        # Botones de accion
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill="x", padx=8, pady=6)
        ttk.Button(btn_frame, text="Guardar cambios",
                   style="Primary.TButton",
                   command=self._guardar).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Validar y pasar a contabilizar",
                   command=self._validar_seleccionado).pack(side="left", padx=4)

        # Errores OCR
        self._lbl_errores = ttk.Label(parent, text="", foreground="#c0392b",
                                       wraplength=400, justify="left")
        self._lbl_errores.pack(anchor="w", padx=8, pady=2)

    def _build_preview(self, parent: ttk.Frame):
        """Vista local de la primera pagina; no envia el documento a ningun servicio."""
        barra = ttk.Frame(parent)
        barra.pack(fill="x", padx=8, pady=(8, 4))
        self._lbl_preview = ttk.Label(barra, text="Selecciona una factura para verla.")
        self._lbl_preview.pack(side="left", fill="x", expand=True)
        ttk.Label(barra, text="Campo a marcar:").pack(side="left", padx=(12, 4))
        ttk.Combobox(
            barra, textvariable=self._campo_marcado_var, state="readonly", width=20,
            values=("ProveedorNif", "ProveedorNombre", "NumeroFactura", "FechaFactura",
                    "FechaVencimiento", "BaseTotal", "IvaTotal", "TotalFactura"),
        ).pack(side="left")
        ttk.Label(barra, text="Arrastra un rectangulo sobre el valor", foreground="#555").pack(
            side="left", padx=8,
        )
        ttk.Button(barra, text="-", width=3, command=lambda: self._cambiar_zoom_preview(-0.2)).pack(side="right", padx=(4, 0))
        ttk.Button(barra, text="+", width=3, command=lambda: self._cambiar_zoom_preview(0.2)).pack(side="right", padx=(4, 0))
        ttk.Button(barra, text="100 %", command=self._restablecer_zoom_preview).pack(side="right", padx=(4, 0))
        ttk.Button(barra, text="Abrir documento", command=self._abrir_documento).pack(side="right")
        marco = ttk.Frame(parent)
        marco.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        marco.rowconfigure(0, weight=1)
        marco.columnconfigure(0, weight=1)
        self._canvas_preview = tk.Canvas(marco, background="#e5e7eb", highlightthickness=0)
        vsb = ttk.Scrollbar(marco, orient="vertical", command=self._canvas_preview.yview)
        hsb = ttk.Scrollbar(marco, orient="horizontal", command=self._canvas_preview.xview)
        self._canvas_preview.configure(xscrollcommand=hsb.set, yscrollcommand=vsb.set)
        self._canvas_preview.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self._canvas_preview.bind("<MouseWheel>", lambda event: self._canvas_preview.yview_scroll(-int(event.delta / 120), "units"))
        self._canvas_preview.bind("<Control-MouseWheel>", lambda event: self._cambiar_zoom_preview(0.1 if event.delta > 0 else -0.1))
        self._preview_photo = None
        self._preview_imagen_original = None
        self._preview_zoom = 1.0
        self._preview_path = ""
        self._canvas_preview.bind("<ButtonPress-1>", self._iniciar_marca)
        self._canvas_preview.bind("<B1-Motion>", self._actualizar_marca)
        self._canvas_preview.bind("<ButtonRelease-1>", self._terminar_marca)

    def _mostrar_preview(self, doc: dict):
        ruta = Path(str(doc.get("ruta_original") or ""))
        self._preview_path = str(ruta)
        self._preview_photo = None
        self._preview_imagen_original = None
        self._canvas_preview.delete("all")
        self._marcas_campos = {}
        if not ruta.exists():
            self._lbl_preview.configure(text=f"No se encuentra el documento original: {ruta}")
            return
        try:
            imagen = self._cargar_primera_pagina(ruta)
            self._preview_imagen_original = imagen
            self._preview_zoom = 1.0
            self._aplicar_zoom_preview()
            self._lbl_preview.configure(text=f"{ruta.name} - primera pagina")
        except Exception as exc:
            self._lbl_preview.configure(text=f"No se pudo generar la vista previa: {exc}")
            self._canvas_preview.create_text(20, 20, anchor="nw", text="Usa 'Abrir documento' para verlo en el visor PDF.")

    def _cambiar_zoom_preview(self, incremento: float):
        if self._preview_imagen_original is None:
            return
        self._preview_zoom = max(0.3, min(3.0, self._preview_zoom + incremento))
        self._aplicar_zoom_preview()

    def _restablecer_zoom_preview(self):
        if self._preview_imagen_original is None:
            return
        self._preview_zoom = 1.0
        self._aplicar_zoom_preview()

    def _aplicar_zoom_preview(self):
        if self._preview_imagen_original is None:
            return
        from PIL import Image, ImageTk
        original = self._preview_imagen_original
        ancho = max(1, round(original.width * self._preview_zoom))
        alto = max(1, round(original.height * self._preview_zoom))
        imagen = original.resize((ancho, alto), Image.Resampling.LANCZOS)
        self._preview_photo = ImageTk.PhotoImage(imagen)
        self._canvas_preview.delete("all")
        self._canvas_preview.create_image(0, 0, anchor="nw", image=self._preview_photo, tags=("pagina",))
        self._dibujar_marcas()
        self._canvas_preview.configure(scrollregion=(0, 0, ancho, alto))

    def _iniciar_marca(self, event):
        if self._preview_imagen_original is None:
            return
        self._marca_inicio = (
            self._canvas_preview.canvasx(event.x), self._canvas_preview.canvasy(event.y),
        )
        self._marca_rect_id = self._canvas_preview.create_rectangle(
            *self._marca_inicio, *self._marca_inicio, outline="#e11d48", width=2,
        )

    def _actualizar_marca(self, event):
        if self._marca_inicio is None or self._marca_rect_id is None:
            return
        x = self._canvas_preview.canvasx(event.x)
        y = self._canvas_preview.canvasy(event.y)
        self._canvas_preview.coords(self._marca_rect_id, *self._marca_inicio, x, y)

    def _terminar_marca(self, event):
        if self._marca_inicio is None or self._preview_imagen_original is None:
            return
        x1, y1 = self._marca_inicio
        x2 = self._canvas_preview.canvasx(event.x)
        y2 = self._canvas_preview.canvasy(event.y)
        left, top = min(x1, x2), min(y1, y2)
        right, bottom = max(x1, x2), max(y1, y2)
        width, height = self._preview_imagen_original.size
        if right - left >= 4 and bottom - top >= 4:
            campo = self._campo_marcado_var.get().strip()
            marca = {
                "x": round(max(0, left) / self._preview_zoom, 2),
                "y": round(max(0, top) / self._preview_zoom, 2),
                "width": round(min(width, right / self._preview_zoom) - max(0, left) / self._preview_zoom, 2),
                "height": round(min(height, bottom / self._preview_zoom) - max(0, top) / self._preview_zoom, 2),
            }
            self._marcas_campos[campo] = marca
            texto = self._extraer_texto_marca(marca)
            if texto and campo in self._entries:
                self._entries[campo].set(texto)
        self._marca_inicio = None
        self._marca_rect_id = None
        self._dibujar_marcas()

    def _dibujar_marcas(self):
        if self._preview_imagen_original is None:
            return
        self._canvas_preview.delete("marca")
        for campo, marca in self._marcas_campos.items():
            try:
                x = float(marca["x"]) * self._preview_zoom
                y = float(marca["y"]) * self._preview_zoom
                w = float(marca["width"]) * self._preview_zoom
                h = float(marca["height"]) * self._preview_zoom
            except (TypeError, ValueError, KeyError):
                continue
            self._canvas_preview.create_rectangle(x, y, x + w, y + h, outline="#16a34a", width=2, tags=("marca",))
            self._canvas_preview.create_text(x + 3, y + 3, anchor="nw", text=campo, fill="#166534", tags=("marca",))

    def _extraer_texto_marca(self, marca: dict) -> str:
        """Extrae las palabras PDF que caen dentro de una marca visual."""
        if not self._preview_path.lower().endswith(".pdf"):
            return ""
        try:
            import fitz
            pdf = fitz.open(self._preview_path)
            try:
                page = pdf.load_page(0)
                palabras = page.get_text("words") or []
                escala_x = self._preview_imagen_original.width / page.rect.width
                escala_y = self._preview_imagen_original.height / page.rect.height
            finally:
                pdf.close()
            left = float(marca["x"])
            top = float(marca["y"])
            right = left + float(marca["width"])
            bottom = top + float(marca["height"])
            dentro = []
            for x0, y0, x1, y1, texto, *_ in palabras:
                px0, py0 = x0 * escala_x, y0 * escala_y
                px1, py1 = x1 * escala_x, y1 * escala_y
                cx, cy = (px0 + px1) / 2, (py0 + py1) / 2
                if left <= cx <= right and top <= cy <= bottom:
                    dentro.append((round(py0, 1), round(px0, 1), str(texto)))
            dentro.sort(key=lambda item: (item[0], item[1]))
            return " ".join(item[2] for item in dentro).strip()
        except Exception:
            return ""

    def _cargar_primera_pagina(self, ruta: Path):
        from PIL import Image
        if ruta.suffix.lower() != ".pdf":
            imagen = Image.open(ruta)
            imagen.thumbnail((1250, 1200))
            return imagen.copy()
        try:
            import fitz
            pdf = fitz.open(str(ruta))
            try:
                pagina = pdf.load_page(0)
                pix = pagina.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                imagen = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            finally:
                pdf.close()
        except Exception as fitz_error:
            ejecutable = shutil.which("pdftoppm")
            if not ejecutable:
                raise RuntimeError(
                    "No se pudo leer el PDF con PyMuPDF y no hay visor alternativo disponible."
                ) from fitz_error
            carpeta = Path(tempfile.mkdtemp(prefix="gest2a3eco_preview_"))
            prefijo = carpeta / "pagina"
            subprocess.run(
                [ejecutable, "-f", "1", "-l", "1", "-scale-to", "1400", "-png", str(ruta), str(prefijo)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            png = next(carpeta.glob("pagina-1.png"), None)
            if not png:
                raise RuntimeError("No se genero la imagen de la primera pagina.")
            imagen = Image.open(png).copy()
        return imagen

    def _abrir_documento(self):
        if not self._preview_path or not Path(self._preview_path).exists():
            messagebox.showwarning("OCR", "No hay documento original disponible.")
            return
        try:
            os.startfile(self._preview_path)
        except Exception as exc:
            messagebox.showerror("OCR", f"No se pudo abrir el documento:\n{exc}")

    def _cargar_maestro_proveedores(self, seleccionado_id: str = ""):
        """Carga maestro global y relaciones de la empresa en el selector."""
        relaciones = {
            str(t.get("id") or ""): t
            for t in self._gestor.listar_terceros_por_empresa(self._codigo, self._ejercicio)
        }
        terceros = {str(t.get("id") or ""): dict(t) for t in self._gestor.listar_terceros()}
        terceros.update(relaciones)
        self._terceros_por_etiqueta.clear()
        etiquetas = []
        etiqueta_seleccionada = ""
        for tercero_id, tercero in sorted(terceros.items(), key=lambda item: str(item[1].get("nombre") or "").lower()):
            if not tercero_id:
                continue
            nif = normalizar_nif_cif(tercero.get("nif"))
            nombre = str(tercero.get("nombre") or tercero.get("nombre_legal") or "").strip()
            if not (nif or nombre):
                continue
            cuenta = str(tercero.get("subcuenta_proveedor") or "").strip()
            etiqueta = f"{nombre} - {nif}".strip(" -")
            if cuenta:
                etiqueta += f" ({cuenta})"
            elif tercero_id not in relaciones:
                etiqueta += " (sin asignar)"
            self._terceros_por_etiqueta[etiqueta] = tercero
            etiquetas.append(etiqueta)
            if tercero_id == str(seleccionado_id or ""):
                etiqueta_seleccionada = etiqueta
        self._cb_proveedor.configure(values=etiquetas)
        self._proveedor_var.set(etiqueta_seleccionada)

    def _cargar_subcuentas_plan_empresa(self, seleccionada: str = ""):
        """Carga cuentas personales del maestro contable local de la empresa."""
        self._cuentas_plan_por_etiqueta.clear()
        etiquetas = []
        codigos_vistos: set[str] = set()
        try:
            # Fuente principal: maestro_subcuentas_empresa. Es el plan local
            # de la empresa enriquecido durante la importacion de A3.
            cuentas = self._gestor.listar_maestro_subcuentas_empresa(
                self._codigo, activo=None,
            ) or []
        except Exception:
            cuentas = []
        for cuenta in cuentas:
            codigo = str(cuenta.get("subcuenta") or cuenta.get("cuenta") or "").strip()
            if not (codigo.startswith("400") or codigo.startswith("410")):
                continue
            codigos_vistos.add(codigo)
            texto = f"{codigo} - {str(cuenta.get('nombre_subcuenta') or cuenta.get('descripcion') or '').strip()}".rstrip(" -")
            self._cuentas_plan_por_etiqueta[texto] = codigo
            etiquetas.append(texto)
        # Compatibilidad con instalaciones que solo tengan plan_cuentas.
        try:
            cur = self._gestor.conn.execute(
                "SELECT DISTINCT cuenta, descripcion FROM plan_cuentas "
                "WHERE codigo_empresa=? ORDER BY cuenta",
                (self._codigo,),
            )
            columnas = [c[0] for c in cur.description]
            for fila in cur.fetchall():
                cuenta = dict(zip(columnas, fila))
                codigo = str(cuenta.get("cuenta") or "").strip()
                if codigo in codigos_vistos or not (codigo.startswith("400") or codigo.startswith("410")):
                    continue
                texto = f"{codigo} - {str(cuenta.get('descripcion') or '').strip()}".rstrip(" -")
                self._cuentas_plan_por_etiqueta[texto] = codigo
                etiquetas.append(texto)
        except Exception:
            pass
        self._cb_subcuenta_plan.configure(values=etiquetas)
        etiqueta = next((e for e, c in self._cuentas_plan_por_etiqueta.items() if c == str(seleccionada or "")), "")
        self._subcuenta_plan_var.set(etiqueta)

    def _subcuenta_plan_seleccionada(self) -> str:
        return self._cuentas_plan_por_etiqueta.get(self._subcuenta_plan_var.get(), "")

    def _cargar_subcuentas_gasto(self, seleccionada: str = ""):
        """Carga cuentas de gasto del plan contable de la empresa."""
        self._cuentas_gasto_por_etiqueta.clear()
        cuentas = []
        try:
            cuentas = list(self._gestor.listar_maestro_subcuentas_empresa(self._codigo, activo=None) or [])
        except Exception:
            pass
        try:
            cur = self._gestor.conn.execute(
                "SELECT DISTINCT cuenta, descripcion FROM plan_cuentas WHERE codigo_empresa=? ORDER BY cuenta",
                (self._codigo,),
            )
            columnas = [c[0] for c in cur.description]
            cuentas.extend(dict(zip(columnas, fila)) for fila in cur.fetchall())
        except Exception:
            pass
        etiquetas, vistos = [], set()
        for cuenta in cuentas:
            codigo = str(cuenta.get("subcuenta") or cuenta.get("cuenta") or "").strip()
            if not codigo or codigo in vistos or codigo[0] not in "67":
                continue
            vistos.add(codigo)
            texto = f"{codigo} - {str(cuenta.get('nombre_subcuenta') or cuenta.get('descripcion') or '').strip()}".rstrip(" -")
            self._cuentas_gasto_por_etiqueta[texto] = codigo
            etiquetas.append(texto)
        self._cb_subcuenta_gasto.configure(values=etiquetas)
        self._subcuenta_gasto_var.set(next((e for e, c in self._cuentas_gasto_por_etiqueta.items() if c == str(seleccionada or "")), ""))

    def _subcuenta_gasto_seleccionada(self) -> str:
        return self._cuentas_gasto_por_etiqueta.get(self._subcuenta_gasto_var.get(), "")

    def _aplicar_proveedor_maestro(self, tercero: dict):
        tercero_id = str(tercero.get("id") or "").strip()
        if not tercero_id:
            return
        self._proveedor_id_seleccionado = tercero_id
        self._entries["nif_proveedor"].set(normalizar_nif_cif(tercero.get("nif")))
        self._entries["nombre_proveedor"].set(str(tercero.get("nombre") or tercero.get("nombre_legal") or ""))
        tipo = str(tercero.get("proveedor_tipo_operacion_iva") or "").strip()
        if tipo in PROVEEDOR_TIPOS_IVA:
            self._tipo_operacion_iva_var.set(tipo)
        cuenta = str(tercero.get("subcuenta_proveedor") or "").strip()
        self._cargar_subcuentas_plan_empresa(cuenta)
        self._cargar_subcuentas_gasto(str(tercero.get("subcuenta_gasto") or ""))
        texto = f"Vinculado al maestro{f' - cuenta {cuenta}' if cuenta else ''}."
        self._lbl_proveedor_maestro.configure(text=texto)

    def _seleccionar_proveedor_maestro(self, _event=None):
        tercero = self._terceros_por_etiqueta.get(self._proveedor_var.get())
        if tercero:
            self._aplicar_proveedor_maestro(tercero)

    def _buscar_proveedor_maestro(self):
        nif = normalizar_nif_cif(self._entries["nif_proveedor"].get())
        nombre = self._entries["nombre_proveedor"].get().strip()
        tercero = self._terceros_svc.resolver_tercero(
            self._gestor, nif, nombre, self._codigo, self._ejercicio,
        )
        if not tercero:
            self._lbl_proveedor_maestro.configure(text="No existe en el maestro. Usa Alta proveedor / acreedor.")
            return
        self._cargar_maestro_proveedores(str(tercero.get("id") or ""))
        self._aplicar_proveedor_maestro(tercero)

    def _asegurar_proveedor_en_empresa(self):
        """Asigna una cuenta existente del plan de la empresa al tercero seleccionado."""
        tercero_id = str(self._proveedor_id_seleccionado or "")
        if not tercero_id:
            return
        subcuenta = self._subcuenta_plan_seleccionada()
        relacion = self._gestor.get_tercero_empresa(self._codigo, tercero_id, self._ejercicio) or {
            "codigo_empresa": self._codigo, "tercero_id": tercero_id,
        }
        if not subcuenta:
            raise ValueError(
                "Selecciona una subcuenta 400 o 410 del plan contable de la empresa. "
                "Si no aparece, importa antes el plan desde A3."
            )
        relacion["subcuenta_proveedor"] = subcuenta
        relacion["subcuenta_gasto"] = self._subcuenta_gasto_seleccionada()
        self._gestor.upsert_tercero_empresa(relacion)

    def _alta_proveedor(self):
        dialog = tk.Toplevel(self)
        dialog.title("Alta de proveedor / acreedor")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        nif = tk.StringVar(value=normalizar_nif_cif(self._entries["nif_proveedor"].get()))
        nombre = tk.StringVar(value=self._entries["nombre_proveedor"].get().strip())
        clase = tk.StringVar(value="proveedor")
        for fila, (texto, var) in enumerate((("NIF", nif), ("Nombre", nombre))):
            ttk.Label(frame, text=texto).grid(row=fila, column=0, sticky="e", padx=(0, 6), pady=3)
            ttk.Entry(frame, textvariable=var, width=42).grid(row=fila, column=1, sticky="ew", pady=3)
        ttk.Label(frame, text="Clase").grid(row=2, column=0, sticky="e", padx=(0, 6), pady=3)
        ttk.Combobox(frame, textvariable=clase, values=("proveedor", "acreedor"), state="readonly", width=18).grid(row=2, column=1, sticky="w", pady=3)

        def guardar():
            nif_val = normalizar_nif_cif(nif.get())
            nombre_val = nombre.get().strip()
            if not nif_val or not nombre_val:
                messagebox.showwarning("OCR", "Indica NIF y nombre.", parent=dialog)
                return
            try:
                tercero_id = self._gestor.upsert_tercero({"nif": nif_val, "nombre": nombre_val})
                tercero = self._gestor.get_tercero(str(tercero_id)) or {"id": tercero_id, "nif": nif_val, "nombre": nombre_val}
            except Exception as exc:
                messagebox.showerror("OCR", f"No se pudo dar de alta: {exc}", parent=dialog)
                return
            dialog.destroy()
            self._cargar_maestro_proveedores(str(tercero.get("id") or ""))
            self._aplicar_proveedor_maestro(tercero)

        botones = ttk.Frame(frame)
        botones.grid(row=3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(botones, text="Cancelar", command=dialog.destroy).pack(side="left", padx=(0, 5))
        ttk.Button(botones, text="Dar de alta", style="Primary.TButton", command=guardar).pack(side="left")
        frame.columnconfigure(1, weight=1)

    def _mostrar_estado_aprendizaje(self):
        from services.ocr import AprendizajeOcrService
        cfg = load_app_config()
        resumen = AprendizajeOcrService(self._gestor, self._codigo).resumen()
        pendientes = int(resumen.get("pendientes") or 0)
        proveedores = resumen.get("por_proveedor") or {}
        lineas = [f"Ejemplos validados pendientes de entrenamiento: {pendientes}"]
        if proveedores:
            lineas.append("")
            lineas.append("Por proveedor (NIF):")
            lineas.extend(f"- {nif}: {total}" for nif, total in sorted(proveedores.items()))
        lineas.extend([
            "",
            "Cada factura validada se incorpora automaticamente a esta cola.",
            "La exportacion y el reentrenamiento se realizan despues de revisar una muestra suficiente.",
        ])
        dialog = tk.Toplevel(self.winfo_toplevel())
        dialog.title("Aprendizaje OCR")
        dialog.transient(self.winfo_toplevel())
        ttk.Label(dialog, text="\n".join(lineas), justify="left", wraplength=600).pack(padx=14, pady=14)
        actions = ttk.Frame(dialog); actions.pack(fill="x", padx=14, pady=(0, 14))
        def exportar():
            try:
                resultado = AprendizajeOcrService(self._gestor, self._codigo).exportar_a_blob(
                    connection_string=str(cfg.get("azure_storage_connection_string") or ""),
                    container=str(cfg.get("azure_ocr_training_container") or "facturas-entrenamiento"),
                )
                messagebox.showinfo("Aprendizaje OCR", f"Documentos subidos: {resultado['subidos']}\nOmitidos: {resultado['omitidos']}\n\nAhora revisa y etiqueta los PDF en Document Intelligence Studio.", parent=dialog)
                dialog.destroy()
            except Exception as exc:
                messagebox.showerror("Aprendizaje OCR", str(exc), parent=dialog)
        ttk.Button(actions, text="Exportar pendientes a Azure", command=exportar).pack(side="left")
        ttk.Button(actions, text="Cerrar", command=dialog.destroy).pack(side="right")

    def _cargar_linea_iva_en_editor(self, _event=None):
        seleccion = self._tv_iva.selection()
        if not seleccion:
            return
        valores = self._tv_iva.item(seleccion[0], "values")
        for campo, valor in zip(self._iva_vars, valores):
            self._iva_vars[campo].set(str(valor))

    def _guardar_linea_iva(self):
        try:
            valores = [_parse_importe(self._iva_vars[campo].get()) for campo in self._iva_vars]
        except ValueError:
            messagebox.showerror("OCR", "Los valores de la linea de IVA deben ser numericos.")
            return
        tipo, base, cuota, tipo_recargo, cuota_recargo = valores
        if not 0 <= tipo <= 100:
            messagebox.showerror("OCR", "El tipo de IVA debe estar entre 0 y 100.")
            return
        fila = tuple(f"{valor:.2f}" for valor in valores)
        seleccion = self._tv_iva.selection()
        if seleccion:
            self._tv_iva.item(seleccion[0], values=fila)
        else:
            self._tv_iva.insert("", "end", values=fila)
        self._recalcular_totales_iva()

    def _quitar_linea_iva(self):
        for item in self._tv_iva.selection():
            self._tv_iva.delete(item)
        for var in self._iva_vars.values():
            var.set("")
        self._iva_vars["tipo_iva"].set("21")
        self._iva_vars["tipo_recargo"].set("0")
        self._recalcular_totales_iva()

    def _lineas_iva_editor(self) -> list[dict]:
        lineas = []
        for item in self._tv_iva.get_children():
            valores = self._tv_iva.item(item, "values")
            try:
                tipo, base, cuota, tipo_recargo, cuota_recargo = [_parse_importe(v) for v in valores]
            except ValueError:
                raise ValueError("Hay una linea de IVA con importes invalidos.")
            lineas.append({
                "tipo_iva": tipo, "base": base, "cuota_iva": cuota,
                "tipo_recargo": tipo_recargo, "cuota_recargo": cuota_recargo,
            })
        return lineas

    def _recalcular_totales_iva(self):
        try:
            lineas = self._lineas_iva_editor()
        except ValueError:
            return
        if not lineas:
            return
        base = round(sum(linea["base"] for linea in lineas), 2)
        iva = round(sum(linea["cuota_iva"] for linea in lineas), 2)
        recargo = round(sum(linea["cuota_recargo"] for linea in lineas), 2)
        retencion = _parse_importe(self._entries["retencion_total"].get())
        self._entries["base_total"].set(f"{base:.2f}")
        self._entries["iva_total"].set(f"{iva:.2f}")
        self._entries["total_factura"].set(f"{base + iva + recargo - retencion:.2f}")

    # ── Refresco de bandejas ──────────────────────────────────────────────────

    def _refresh_all(self):
        for estado, _ in BANDEJAS:
            self._refresh_bandeja(estado)

    def _refresh_bandeja(self, estado: str):
        # Cargar documentos OCR por estado (via tabla documentos_ocr)
        try:
            docs = self._gestor.listar_documentos_ocr(self._empresa_id, estado)
        except Exception:
            # Compatibilidad: si metodo no existe, fallback
            docs = []

        # Enriquecer con datos de factura
        enriquecidos = []
        for doc in docs:
            factura = None
            try:
                cur = self._gestor.conn.execute(
                    "SELECT * FROM facturas_recibidas_ocr WHERE documento_id=?",
                    (doc["id"],),
                )
                row = cur.fetchone()
                if row:
                    cols = [c[0] for c in cur.description]
                    factura = dict(zip(cols, row))
            except Exception:
                pass
            merged = dict(doc)
            if factura:
                merged.update({k: v for k, v in factura.items() if k not in ("id", "estado")})
            # El asiento vive en la proyeccion contable; mostrarlo en OCR
            # evita tener que abrir Contabilidad para comprobarlo.
            try:
                contable = self._gestor.get_factura_recibida_doc(str(doc["id"])) or {}
                if contable:
                    merged["numero_asiento"] = contable.get("numero_asiento") or ""
            except Exception:
                merged["numero_asiento"] = ""
            enriquecidos.append(merged)

        tv = self._tvs.get(estado)
        if not tv:
            return
        tv.delete(*tv.get_children())
        for doc in enriquecidos:
            confianza = _normalizar_confianza(doc.get("confianza_global"))
            vals = (
                doc.get("nombre_archivo") or "",
                doc.get("nombre_proveedor") or "",
                doc.get("nif_proveedor") or "",
                doc.get("numero_factura") or "",
                doc.get("fecha_factura") or "",
                f"{float(doc.get('total_factura') or 0.0):.2f}",
                doc.get("numero_asiento") or "",
                doc.get("motor_ocr") or "",
                f"{confianza:.0%}" if confianza else "",
                doc.get("estado") or "",
            )
            tag = "row_error" if estado == "error" else (
                "row_ok" if estado == "contabilizada" else ""
            )
            tv.insert("", "end", iid=str(doc["id"]), values=vals, tags=(tag,) if tag else ())

        # Actualizar titulo de pestana con conteo
        for idx, (est, titulo) in enumerate(BANDEJAS):
            if est == estado:
                badge = f" ({len(enriquecidos)})" if enriquecidos else ""
                self._nb.tab(idx, text=titulo + badge)
                break

    # ── Seleccion y editor ────────────────────────────────────────────────────

    def _on_select(self, estado: str):
        tv = self._tvs.get(estado)
        if not tv:
            return
        sel = tv.selection()
        if not sel:
            return
        doc_id = sel[0]
        doc = self._gestor.get_documento_ocr(doc_id)
        if not doc:
            return
        self._doc_seleccionado = doc

    def _abrir_seleccionado(self, estado: str):
        """Abre el editor solo tras doble clic; el clic simple selecciona."""
        self._on_select(estado)
        doc = self._doc_seleccionado
        if not doc:
            return
        self._abrir_ventana_revision(doc)

    def _abrir_ventana_revision(self, doc: dict):
        """Abre la revision de una factura sin saturar el listado principal."""
        if self._revision_window and self._revision_window.winfo_exists():
            self._revision_window.destroy()
        ventana = tk.Toplevel(self)
        ventana.title(f"Revision OCR - {doc.get('nombre_archivo') or 'Factura'}")
        ventana.transient(self.winfo_toplevel())
        ancho = min(1900, max(1200, ventana.winfo_screenwidth() - 70))
        alto = min(1050, max(700, ventana.winfo_screenheight() - 100))
        ventana.geometry(f"{ancho}x{alto}+25+25")
        ventana.minsize(1200, 700)
        self._revision_window = ventana
        self._editor_activo = True
        estado_revision = str(doc.get("estado") or "").strip().lower()
        ventana.protocol("WM_DELETE_WINDOW", self._cerrar_ventana_revision)

        cabecera = ttk.Frame(ventana, padding=(12, 8))
        cabecera.pack(fill="x")
        ttk.Label(cabecera, text="Revision de factura", font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(cabecera, text="Cerrar", command=self._cerrar_ventana_revision).pack(side="right")

        # En la ventana propia hay espacio para trabajar en dos columnas:
        # documento grande a la izquierda y datos editables a la derecha.
        detalle = ttk.PanedWindow(ventana, orient="horizontal")
        detalle.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        preview = ttk.Frame(detalle)
        editor_shell = ttk.Frame(detalle)
        detalle.add(preview, weight=55)
        detalle.add(editor_shell, weight=45)
        self._build_preview(preview)
        self._build_editor(self._crear_editor_desplazable(editor_shell))
        self._cargar_factura_en_editor(str(doc.get("id") or ""))
        self._mostrar_preview(doc)
        if estado_revision in ("pendiente_contabilizar", "contabilizada"):
            self._bloquear_editor_revision(editor_shell, permitir_error=(estado_revision == "pendiente_contabilizar"))

    def _bloquear_editor_revision(self, contenedor, *, permitir_error: bool):
        """Impide cambios en documentos ya revisados/contabilizados."""
        def recorrer(widget):
            for hijo in widget.winfo_children():
                if isinstance(hijo, (ttk.Entry, ttk.Combobox, ttk.Button, ttk.Treeview)):
                    try:
                        hijo.configure(state="disabled")
                    except tk.TclError:
                        pass
                recorrer(hijo)
        recorrer(contenedor)
        if permitir_error:
            ttk.Button(
                contenedor, text="Pasar a errores para editar",
                command=self._pasar_revision_a_error,
            ).pack(anchor="w", padx=12, pady=(0, 8))

    def _pasar_revision_a_error(self):
        doc = self._doc_seleccionado
        if not doc:
            return
        doc["estado"] = "error"
        self._gestor.upsert_documento_ocr(doc)
        self._cerrar_ventana_revision()
        self._refresh_all()

    def _cerrar_ventana_revision(self):
        if self._revision_window and self._revision_window.winfo_exists():
            self._revision_window.destroy()
        self._revision_window = None
        self._editor_activo = False

    def _cargar_factura_en_editor(self, doc_id: str):
        """Carga datos de facturas_recibidas_ocr en el editor."""
        try:
            cur = self._gestor.conn.execute(
                "SELECT * FROM facturas_recibidas_ocr WHERE documento_id=?", (doc_id,)
            )
            row = cur.fetchone()
            if not row:
                self._limpiar_editor()
                return
            cols = [c[0] for c in cur.description]
            factura = dict(zip(cols, row))
        except Exception:
            self._limpiar_editor()
            return

        self._factura_seleccionada = factura
        self._marcas_campos = {}
        try:
            ejemplo = self._gestor.get_ejemplo_aprendizaje_ocr(str(factura["id"]))
            if ejemplo and ejemplo.get("marcas_json"):
                self._marcas_campos = json.loads(ejemplo["marcas_json"])
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            self._marcas_campos = {}
        self._proveedor_id_seleccionado = str(factura.get("proveedor_id") or "")
        self._cargar_maestro_proveedores(self._proveedor_id_seleccionado)
        relacion = (
            self._gestor.get_tercero_empresa(self._codigo, self._proveedor_id_seleccionado, self._ejercicio)
            if self._proveedor_id_seleccionado else None
        )
        self._cargar_subcuentas_plan_empresa(
            str((relacion or {}).get("subcuenta_proveedor") or "")
        )
        self._cargar_subcuentas_gasto(
            str((relacion or {}).get("subcuenta_gasto") or factura.get("cuenta_gasto") or "")
        )
        self._tipo_operacion_iva_var.set(
            str(factura.get("tipo_operacion_iva") or "INTERIOR_DEDUCIBLE")
        )
        self._lbl_proveedor_maestro.configure(text="Sin vincular al maestro." if not self._proveedor_id_seleccionado else "Vinculado al maestro.")

        # Rellenar entradas de cabecera
        for campo, var in self._entries.items():
            val = factura.get(campo)
            var.set("" if val is None else str(val))

        # Lineas IVA
        self._tv_iva.delete(*self._tv_iva.get_children())
        try:
            lineas = self._gestor.listar_lineas_iva_ocr(factura["id"])
            for l in lineas:
                self._tv_iva.insert("", "end", values=(
                    l.get("tipo_iva", ""), l.get("base", ""),
                    l.get("cuota_iva", ""), l.get("tipo_recargo", ""),
                    l.get("cuota_recargo", ""),
                ))
        except Exception:
            pass

        # Retenciones
        self._tv_ret.delete(*self._tv_ret.get_children())
        try:
            rets = self._gestor.listar_retenciones_ocr(factura["id"])
            for r in rets:
                self._tv_ret.insert("", "end", values=(
                    r.get("base_retencion", ""), r.get("tipo_retencion", ""),
                    r.get("importe_retencion", ""), r.get("clase_retencion", ""),
                ))
        except Exception:
            pass

        # Errores
        errores = factura.get("observaciones") or ""
        self._lbl_errores.configure(text=f"Avisos: {errores}" if errores else "")

    def _limpiar_editor(self):
        if not self._editor_activo:
            self._factura_seleccionada = None
            self._proveedor_id_seleccionado = ""
            return
        for var in self._entries.values():
            var.set("")
        self._tv_iva.delete(*self._tv_iva.get_children())
        for var in self._iva_vars.values():
            var.set("")
        self._iva_vars["tipo_iva"].set("21")
        self._iva_vars["tipo_recargo"].set("0")
        self._tv_ret.delete(*self._tv_ret.get_children())
        self._lbl_errores.configure(text="")
        self._factura_seleccionada = None
        self._proveedor_id_seleccionado = ""
        self._proveedor_var.set("")
        self._subcuenta_plan_var.set("")
        self._subcuenta_gasto_var.set("")
        self._tipo_operacion_iva_var.set("INTERIOR_DEDUCIBLE")
        self._lbl_proveedor_maestro.configure(text="")

    def _on_tab_changed(self, _e):
        idx = self._nb.index(self._nb.select())
        estado = BANDEJAS[idx][0]
        self._refresh_bandeja(estado)

    # ── Importar ──────────────────────────────────────────────────────────────

    def _importar(self):
        paths = filedialog.askopenfilenames(
            title="Seleccionar documentos",
            filetypes=[
                ("Documentos soportados", "*.pdf *.png *.jpg *.jpeg"),
                ("PDF", "*.pdf"),
                ("Imagenes", "*.png *.jpg *.jpeg"),
            ],
        )
        if not paths:
            return
        validos = [p for p in paths if Path(p).suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"}]
        if not validos:
            messagebox.showwarning("OCR", "Ningun fichero soportado seleccionado.")
            return
        self._lbl_status.configure(text=f"Procesando {len(validos)} documento(s)...")
        t = threading.Thread(target=self._worker_ocr, args=(validos,), daemon=True)
        self._ocr_thread = t
        t.start()
        self.after(300, self._poll_ocr)

    def _worker_ocr(self, paths: list[str]):
        try:
            from services.ocr import OcrService
            svc = OcrService(
                gestor=self._gestor,
                empresa_id=self._codigo,
                ejercicio=self._ejercicio,
                usuario=getattr(self._session, "usuario", ""),
            )
            for path in paths:
                try:
                    resultado = svc.procesar_archivo(path)
                    self._ocr_q.put(("ok", resultado))
                except Exception as exc:
                    self._ocr_q.put(("error", str(exc)))
        except Exception as exc:
            self._ocr_q.put(("error", f"Error al iniciar OcrService: {exc}"))
        finally:
            self._ocr_q.put(("done", None))

    def _poll_ocr(self):
        changed = False
        done = False
        try:
            while True:
                tipo, payload = self._ocr_q.get_nowait()
                if tipo == "done":
                    done = True
                elif tipo == "ok":
                    changed = True
                elif tipo == "error":
                    logger.warning("[UIFacturasRecibidasOcr] Worker OCR: %s", payload)
                    changed = True
        except queue.Empty:
            pass

        if changed:
            self._refresh_all()
            # Al reprocesar desde el boton de la bandeja se actualiza la
            # propuesta OCR en la base de datos, pero la ventana de revision
            # ya abierta no recibe automaticamente esos valores. Recargarla
            # aqui evita que el usuario vea los datos antiguos o en blanco.
            if self._editor_activo and self._doc_seleccionado:
                doc_id = str(self._doc_seleccionado.get("id") or "")
                doc_actualizado = self._gestor.get_documento_ocr(doc_id) if doc_id else None
                if doc_actualizado:
                    self._doc_seleccionado = doc_actualizado
                    self._cargar_factura_en_editor(doc_id)
                    self._mostrar_preview(doc_actualizado)

        if done:
            self._lbl_status.configure(text="")
            self._ocr_thread = None
        else:
            self.after(300, self._poll_ocr)

    # ── Acciones ──────────────────────────────────────────────────────────────

    def _reprocesar_seleccionado(self):
        doc_id = self._get_selected_id()
        if not doc_id:
            messagebox.showwarning("OCR", "Selecciona un documento.")
            return
        doc = self._gestor.get_documento_ocr(doc_id)
        if not doc:
            return
        self._lbl_status.configure(text="Reprocesando...")
        t = threading.Thread(target=self._worker_reprocesar, args=(doc_id,), daemon=True)
        self._ocr_thread = t
        t.start()
        self.after(300, self._poll_ocr)

    def _worker_reprocesar(self, doc_id: str):
        try:
            from services.ocr import OcrService
            svc = OcrService(
                gestor=self._gestor, empresa_id=self._codigo,
                ejercicio=self._ejercicio, usuario=getattr(self._session, "usuario", ""),
            )
            self._ocr_q.put(("ok", svc.reprocesar_documento(doc_id)))
        except Exception as exc:
            self._ocr_q.put(("error", str(exc)))
        finally:
            self._ocr_q.put(("done", None))

    def _guardar(self):
        if not self._factura_seleccionada and not self._doc_seleccionado:
            messagebox.showwarning("OCR", "No hay documento seleccionado.")
            return
        factura_id = str((self._factura_seleccionada or {}).get("id") or uuid.uuid4())
        payload = dict(self._factura_seleccionada or {
            "id": factura_id,
            "documento_id": str(self._doc_seleccionado.get("id") or ""),
            "empresa_id": self._empresa_id,
            "proveedor_id": None,
            "tipo_operacion_iva": "INTERIOR_DEDUCIBLE",
            "estado_validacion": "pendiente",
            "observaciones": "Factura creada desde revision manual OCR.",
        })
        payload["id"] = factura_id
        payload["documento_id"] = str(payload.get("documento_id") or self._doc_seleccionado.get("id") or "")
        payload["empresa_id"] = str(payload.get("empresa_id") or self._empresa_id)

        for campo, var in self._entries.items():
            valor = var.get().strip()
            if campo in ("total_factura", "base_total", "iva_total", "retencion_total"):
                try:
                    payload[campo] = _parse_importe(valor)
                except ValueError:
                    messagebox.showerror("OCR", f"Valor numerico invalido en '{campo}'.")
                    return
            else:
                payload[campo] = valor

        try:
            lineas_iva = self._lineas_iva_editor()
        except ValueError as exc:
            messagebox.showerror("OCR", str(exc))
            return

        payload["proveedor_id"] = self._proveedor_id_seleccionado or None
        payload["tipo_operacion_iva"] = self._tipo_operacion_iva_var.get().strip() or "INTERIOR_DEDUCIBLE"
        try:
            self._asegurar_proveedor_en_empresa()
        except Exception as exc:
            messagebox.showerror("OCR", f"No se pudo asignar el proveedor a la empresa: {exc}")
            return

        # Registrar correcciones si hay cambios
        try:
            from services.ocr import OcrService
            svc = OcrService(
                gestor=self._gestor,
                empresa_id=self._codigo,
                ejercicio=self._ejercicio,
                usuario=getattr(self._session, "usuario", ""),
            )
            for campo, var in self._entries.items():
                orig = str((self._factura_seleccionada or {}).get(campo) or "")
                nuevo = var.get().strip()
                if orig != nuevo:
                    svc.registrar_correccion(factura_id, campo, orig, nuevo)
        except Exception as exc:
            logger.warning("[guardar] Error al registrar correcciones: %s", exc)

        self._gestor.upsert_factura_recibida_ocr(payload)
        self._gestor.eliminar_lineas_iva_ocr(factura_id)
        for linea in lineas_iva:
            self._gestor.upsert_linea_iva_ocr({
                "factura_id": factura_id,
                **linea,
                "deducible": 1,
                "porcentaje_deduccion": 100.0,
                "tipo_operacion_iva": payload["tipo_operacion_iva"],
            })
        self._factura_seleccionada = payload
        # Recargar desde SQLite para que el formulario derecho refleje tambien
        # las facturas creadas manualmente cuando no habia propuesta OCR.
        marcas_guardadas = dict(self._marcas_campos)
        # La recarga busca por documento_id, no por el id de la factura OCR.
        self._cargar_factura_en_editor(str(payload.get("documento_id") or self._doc_seleccionado.get("id") or ""))
        self._marcas_campos = marcas_guardadas
        self._dibujar_marcas()
        self._refresh_all()
        messagebox.showinfo("OCR", "Cambios guardados.")

    def _validar_seleccionado(self):
        if not self._factura_seleccionada:
            messagebox.showwarning("OCR", "Selecciona un documento.")
            return
        factura = self._factura_seleccionada
        errores = []
        if not str(factura.get("nif_proveedor") or "").strip():
            errores.append("NIF del proveedor")
        if not str(factura.get("numero_factura") or "").strip():
            errores.append("Numero de factura")
        if not str(factura.get("fecha_factura") or "").strip():
            errores.append("Fecha de factura")
        if not float(factura.get("total_factura") or 0.0):
            errores.append("Total (es 0)")
        if errores:
            messagebox.showwarning(
                "OCR",
                "No se puede validar. Faltan campos obligatorios:\n- " + "\n- ".join(errores),
            )
            return
        factura["estado_validacion"] = "validada"
        self._gestor.upsert_factura_recibida_ocr(factura)
        # Actualizar documento a pendiente_contabilizar
        doc = self._doc_seleccionado
        if doc:
            doc["estado"] = "pendiente_contabilizar"
            self._gestor.upsert_documento_ocr(doc)
            try:
                from services.ocr import AprendizajeOcrService
                AprendizajeOcrService(self._gestor, self._codigo).registrar_factura_validada(
                    doc, factura, marcas_campos=self._marcas_campos,
                )
            except Exception as exc:
                logger.warning("[aprendizaje OCR] No se pudo registrar ejemplo: %s", exc)
            self._crear_o_actualizar_documento_contable(doc, factura)
        self._refresh_all()
        messagebox.showinfo(
            "OCR", "Documento validado y enviado a Contabilidad.\nGenera alli el suenlace.dat."
        )

    def _crear_o_actualizar_documento_contable(self, documento: dict, factura: dict):
        """Proyecta el documento OCR tipado al flujo que genera SUENLACE.

        Ambos modelos convivian, pero sin esta proyeccion los documentos nuevos
        (incluidos los que vienen de correo) no podian llegar a contabilidad.
        Se conserva el mismo ID para mantener trazabilidad directa.
        """
        doc_id = str(documento.get("id") or "")
        lineas = []
        try:
            for item in self._gestor.listar_lineas_iva_ocr(str(factura.get("id") or "")):
                lineas.append({
                    "base_imponible": item.get("base") or 0.0,
                    "tipo_iva": item.get("tipo_iva") or 0.0,
                    "cuota_iva": item.get("cuota_iva") or 0.0,
                    "tipo_recargo": item.get("tipo_recargo") or 0.0,
                    "cuota_recargo": item.get("cuota_recargo") or 0.0,
                    "tipo_operacion_iva": item.get("tipo_operacion_iva") or factura.get("tipo_operacion_iva"),
                })
        except Exception as exc:
            logger.warning("[OCR] No se pudieron obtener las lineas IVA: %s", exc)
        ruta = str(documento.get("ruta_original") or "")
        # Las cuentas elegidas en la revision OCR viven en la relacion
        # tercero-empresa. Al proyectar a facturas_recibidas_docs hay que
        # copiarlas, porque Contabilidad genera el asiento desde ese registro
        # y, si faltan, aplica 629/472/400 por defecto.
        relacion = {}
        proveedor_id = str(factura.get("proveedor_id") or "").strip()
        # Si el usuario no selecciono manualmente el proveedor, vincularlo por
        # NIF exacto contra los terceros de la empresa antes de crear el
        # documento contable. Asi se recuperan sus subcuentas configuradas.
        if not proveedor_id:
            nif_ocr = str(factura.get("nif_proveedor") or "").strip()
            try:
                nif_norm = normalizar_nif_cif(nif_ocr)
            except Exception:
                nif_norm = nif_ocr.upper().replace("-", "").replace(" ", "")
            if nif_norm:
                try:
                    for tercero in self._gestor.listar_terceros_por_empresa(self._codigo, self._ejercicio) or []:
                        try:
                            tercero_nif = normalizar_nif_cif(tercero.get("nif"))
                        except Exception:
                            tercero_nif = str(tercero.get("nif") or "").upper().replace("-", "").replace(" ", "")
                        if tercero_nif and tercero_nif == nif_norm:
                            proveedor_id = str(tercero.get("id") or tercero.get("tercero_id") or "")
                            factura["proveedor_id"] = proveedor_id
                            break
                except Exception:
                    pass
        if proveedor_id:
            try:
                relacion = self._gestor.get_tercero_empresa(
                    self._codigo, proveedor_id, self._ejercicio,
                ) or {}
            except Exception as exc:
                logger.warning("[OCR] No se pudo cargar la relacion contable del proveedor: %s", exc)
        payload = {
            "id": doc_id, "codigo_empresa": self._codigo, "ejercicio": self._ejercicio,
            "origen_path": ruta, "pdf_path": ruta if Path(ruta).suffix.lower() == ".pdf" else "",
            "estado_ocr": "procesado", "estado_validacion": "validada",
            "estado_contable": "pendiente_contabilizar", "tipo_documento": "factura_recibida",
            "tercero_id": factura.get("proveedor_id") or "",
            "cuenta_proveedor": factura.get("cuenta_proveedor") or relacion.get("subcuenta_proveedor") or "",
            "cuenta_gasto": factura.get("cuenta_gasto") or relacion.get("subcuenta_gasto") or "",
            "cuenta_iva": factura.get("cuenta_iva") or "",
            "proveedor_nif": factura.get("nif_proveedor") or "",
            "proveedor_nombre": factura.get("nombre_proveedor") or "",
            "proveedor_tipo_operacion_iva": factura.get("tipo_operacion_iva") or "INTERIOR_DEDUCIBLE",
            "numero_factura": factura.get("numero_factura") or "",
            "fecha_factura": factura.get("fecha_factura") or "",
            "fecha_operacion": factura.get("fecha_operacion") or factura.get("fecha_factura") or "",
            "fecha_asiento": factura.get("fecha_factura") or "",
            "fecha_vencimiento": factura.get("fecha_vencimiento") or "",
            "descripcion": f"Factura {factura.get('numero_factura') or ''}".strip(),
            "moneda_codigo": "EUR", "base_imponible": factura.get("base_total") or 0.0,
            "cuota_iva": factura.get("iva_total") or 0.0,
            "cuota_retencion": factura.get("retencion_total") or 0.0,
            "total": factura.get("total_factura") or 0.0, "lineas": lineas,
            "datos_extra": {
                "documento_ocr_id": doc_id,
                "tipo_operacion_iva": factura.get("tipo_operacion_iva") or "INTERIOR_DEDUCIBLE",
            },
        }
        self._gestor.upsert_factura_recibida_doc(payload)

    def _enviar_a_error(self, estado: str):
        doc_id = self._get_selected_id()
        if not doc_id:
            messagebox.showwarning("OCR", "Selecciona un documento.")
            return
        doc = self._gestor.get_documento_ocr(doc_id)
        if doc:
            doc["estado"] = "error"
            self._gestor.upsert_documento_ocr(doc)
        self._refresh_all()

    def _eliminar(self, estado: str):
        doc_id = self._get_selected_id()
        if not doc_id:
            messagebox.showwarning("OCR", "Selecciona un documento.")
            return
        if not messagebox.askyesno("OCR", "Eliminar el documento? No se puede deshacer."):
            return
        try:
            self._gestor.eliminar_documento_ocr(doc_id)
        except Exception as exc:
            messagebox.showerror("OCR", f"Error al eliminar: {exc}")
            return
        self._limpiar_editor()
        self._refresh_all()

    def _abrir_detalle(self, estado: str):
        """Abre el dialogo de detalle existente (ui_ocr_detalle.py) para edicion completa."""
        doc_id = self._get_selected_id()
        if not doc_id:
            return
        try:
            # Intentar abrir el detalle del sistema existente si hay doc en facturas_recibidas_docs
            all_docs = self._gestor.listar_facturas_recibidas_docs_filtrado(
                self._codigo, self._ejercicio, estado
            )
            all_ids = [str(d["id"]) for d in all_docs]
            if all_ids:
                from views.ui_ocr_detalle import UIOcrDetalle
                UIOcrDetalle(
                    master=self,
                    gestor=self._gestor,
                    codigo_empresa=self._codigo,
                    ejercicio=self._ejercicio,
                    doc_ids=all_ids,
                    current_id=all_ids[0],
                    on_close=self._refresh_all,
                )
        except Exception as exc:
            logger.debug("[abrir_detalle] %s", exc)

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _capturar_asiento_a3(self):
        """Lee desde A3 el numero de asiento de las facturas exportadas."""
        from services.import_a3_empresa import leer_numero_asiento_desde_a3

        tv = self._tvs.get("contabilizada")
        seleccionados = list(tv.selection()) if tv else []
        if not seleccionados:
            messagebox.showwarning(
                "OCR", "Selecciona al menos una factura contabilizada.",
                parent=self.winfo_toplevel(),
            )
            return

        codigo_digitos = "".join(ch for ch in str(self._codigo or "") if ch.isdigit())
        codigo_a3 = f"E{(codigo_digitos.zfill(5) if codigo_digitos else '00000')[:5]}"
        ejercicio = int(self._ejercicio)
        actualizadas, no_encontradas = [], []
        for documento_id in seleccionados:
            doc = self._gestor.get_factura_recibida_doc(documento_id)
            if not doc or doc.get("estado_contable") != "contabilizada":
                no_encontradas.append(str((doc or {}).get("numero_factura") or documento_id))
                continue
            numero = str(doc.get("numero_factura") or "").strip()[:10]
            descripcion = str(doc.get("descripcion") or f"Su Fra Nº. {numero}").strip()
            fecha = str(doc.get("fecha_asiento") or doc.get("fecha_factura") or "")
            mes = None
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    from datetime import datetime
                    mes = datetime.strptime(fecha, fmt).month
                    break
                except ValueError:
                    pass
            asiento = leer_numero_asiento_desde_a3(
                codigo_a3, ejercicio, numero, descripcion, mes=mes,
            )
            if asiento and self._gestor.actualizar_numero_asiento_factura_recibida(
                self._codigo, documento_id, asiento,
            ):
                actualizadas.append(f"{numero} -> asiento {asiento}")
            else:
                no_encontradas.append(numero or documento_id)

        self._refresh_all()
        partes = []
        if actualizadas:
            partes.append("Asientos capturados:\n" + "\n".join(actualizadas))
        if no_encontradas:
            partes.append(
                "No encontradas en A3ECO (importa primero el suenlace):\n"
                + "\n".join(no_encontradas)
            )
        messagebox.showinfo("OCR", "\n\n".join(partes) or "Sin cambios.", parent=self.winfo_toplevel())

    def _get_selected_id(self) -> str | None:
        try:
            idx = self._nb.index(self._nb.select())
            estado = BANDEJAS[idx][0]
            tv = self._tvs.get(estado)
            if not tv:
                return None
            sel = tv.selection()
            return sel[0] if sel else None
        except Exception:
            return None

    @property
    def _empresa(self) -> str:
        return self._codigo
