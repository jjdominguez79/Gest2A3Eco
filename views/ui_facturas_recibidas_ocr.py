"""
Vista unificada del modulo OCR de facturas recibidas.

Arquitectura: listado + zona de revision vertical
  Izquierda — listado de documentos por bandeja (Notebook con pestanas)
  Derecha   — vista previa amplia arriba y formulario desplazable debajo

Puntos de integracion:
  - services/ocr/OcrService       — procesamiento OCR tipado
  - services/ocr_contabilidad_service — proyeccion hacia contabilidad
  - gestor principal              — persistencia PostgreSQL
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
from services.ocr_contabilidad_service import OcrContabilidadService
from services.ocr_emitidas_contabilidad_service import OcrEmitContabilidadService
from services.terceros_ocr_service import TercerosOcrService
from utils.utilidades import load_app_config
from utils.validaciones import normalizar_nif_cif

logger = logging.getLogger(__name__)


def _normalizar_confianza(value) -> float:
    """Normaliza valores de confianza para mostrarlos en UI."""
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


IVA_TIPOS_CATALOGO = (21.0, 10.0, 7.5, 5.0, 4.0, 2.0, 0.0)
CAMPOS_APRENDIZAJE_COMUNES = (
    "NumeroFactura", "FechaFactura", "FechaVencimiento",
    "BaseTotal", "IvaTotal", "TotalFactura",
)
CAMPOS_APRENDIZAJE_POR_TIPO = {
    "factura_recibida": (
        "ProveedorNif", "ProveedorNombre", *CAMPOS_APRENDIZAJE_COMUNES,
    ),
    "factura_emitida": (
        "EmisorNif", "EmisorNombre", "ClienteNif", "ClienteNombre",
        *CAMPOS_APRENDIZAJE_COMUNES,
    ),
}
CAMPO_MARCA_A_ENTRY_COMUN = {
    "ProveedorNif": "nif_proveedor", "ProveedorNombre": "nombre_proveedor",
    "ClienteNif": "nif_proveedor", "ClienteNombre": "nombre_proveedor",
    "NumeroFactura": "numero_factura", "FechaFactura": "fecha_factura",
    "FechaVencimiento": "fecha_vencimiento", "BaseTotal": "base_total",
    "IvaTotal": "iva_total", "TotalFactura": "total_factura",
}


def _campos_aprendizaje(tipo_documento: str) -> tuple[str, ...]:
    return CAMPOS_APRENDIZAJE_POR_TIPO.get(
        tipo_documento, CAMPOS_APRENDIZAJE_POR_TIPO["factura_recibida"],
    )


def _zoom_para_ajustar(
    ancho_documento: int, alto_documento: int,
    ancho_disponible: int, alto_disponible: int,
) -> float:
    """Calcula un zoom que muestra la pagina completa sin recortarla."""
    if min(ancho_documento, alto_documento, ancho_disponible, alto_disponible) <= 1:
        return 1.0
    margen = 10
    return max(0.1, min(
        3.0,
        (ancho_disponible - margen) / ancho_documento,
        (alto_disponible - margen) / alto_documento,
    ))


def _resumen_fiscal(
    lineas_iva: list[dict], retenciones: list[dict], suplidos=0.0,
) -> dict[str, float]:
    """Calcula los totales visibles y el total esperado de la factura."""
    base = round(sum(float(linea.get("base") or 0.0) for linea in lineas_iva), 2)
    iva = round(sum(float(linea.get("cuota_iva") or 0.0) for linea in lineas_iva), 2)
    recargo = round(sum(float(linea.get("cuota_recargo") or 0.0) for linea in lineas_iva), 2)
    retencion = round(
        sum(float(linea.get("importe_retencion") or 0.0) for linea in retenciones), 2,
    )
    suplidos_num = round(float(suplidos or 0.0), 2)
    return {
        "base": base,
        "iva": iva,
        "recargo": recargo,
        "retencion": retencion,
        "suplidos": suplidos_num,
        "total_esperado": round(base + iva + recargo + suplidos_num - retencion, 2),
    }


def _totales_coherentes(total, resumen: dict[str, float], tolerancia: float = 0.05) -> bool:
    return abs(float(total or 0.0) - resumen["total_esperado"]) <= tolerancia

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
      gestor        — instancia del gestor principal de datos
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
        self._ocr_mensajes: list[str] = []
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
        self._preview_page = 0
        self._preview_page_count = 1
        self._ocultar_iva_vacias = False
        self._iva_catalog_items: list[str] = []
        self._cargando_editor = False
        self._tipo_doc_var = tk.StringVar(value="factura_recibida")
        self._fecha_contable_modo_var = tk.StringVar(value="Fecha de factura")

        self._build()
        self.after_idle(self._refresh_all)

    # ── Construccion de la UI ─────────────────────────────────────────────────

    def _build(self):
        # Cabecera
        hdr = ttk.Frame(self)
        hdr.pack(fill="x", padx=10, pady=(8, 4))
        titulo = ttk.Frame(hdr)
        titulo.pack(fill="x")
        ttk.Label(
            titulo,
            text=f"Captura documental OCR  —  {self._nombre} ({self._codigo})",
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left")
        ttk.Button(
            titulo, text="Aprendizaje",
            command=self._mostrar_estado_aprendizaje,
        ).pack(side="right", padx=(4, 0))
        ttk.Button(
            titulo, text="Reprocesar seleccionado",
            command=self._reprocesar_seleccionado,
        ).pack(side="right", padx=4)

        btn_frame = ttk.Frame(hdr)
        btn_frame.pack(fill="x", pady=(6, 0))
        self._btn_importar = ttk.Button(
            btn_frame, text="Importar PDF / imagen",
            style="Primary.TButton",
            command=self._importar,
        )
        self._btn_importar.pack(side="left", padx=4)
        ttk.Separator(btn_frame, orient="vertical").pack(side="left", padx=6, fill="y")
        ttk.Label(btn_frame, text="Documento:").pack(side="left", padx=(0, 2))
        self._radio_recibida = ttk.Radiobutton(
            btn_frame, text="Factura de proveedor",
            variable=self._tipo_doc_var, value="factura_recibida",
            command=self._on_tipo_doc_changed,
        )
        self._radio_recibida.pack(side="left")
        self._radio_emitida = ttk.Radiobutton(
            btn_frame, text="Factura de cliente",
            variable=self._tipo_doc_var, value="factura_emitida",
            command=self._on_tipo_doc_changed,
        )
        self._radio_emitida.pack(side="left", padx=(0, 4))
        ttk.Label(btn_frame, text="Fecha contable:").pack(side="left", padx=(8, 2))
        self._cb_fecha_contable_modo = ttk.Combobox(
            btn_frame,
            textvariable=self._fecha_contable_modo_var,
            values=("Fecha de factura", "Hoy"),
            state="readonly",
            width=16,
        )
        self._cb_fecha_contable_modo.pack(side="left", padx=(0, 4))

        # La pantalla inicial solo es el listado de estados. La revision se
        # abre en una ventana propia al seleccionar una factura.
        lista = ttk.Frame(self)
        lista.pack(fill="both", expand=True, padx=10, pady=4)
        self._frm_lista = lista
        self._zona_arrastre = ttk.Label(
            lista,
            text="Arrastra aquí uno o varios PDF o imágenes, o pulsa «Importar PDF / imagen»",
            style="DropZone.TLabel",
            anchor="center",
        )
        self._zona_arrastre.pack(fill="x", pady=(0, 6))
        self._zona_arrastre.bind("<Button-1>", lambda _event: self._importar())
        self._build_bandejas(lista)

        # Barra de estado
        self._lbl_status = ttk.Label(self, text="", foreground="#555")
        self._lbl_status.pack(fill="x", padx=10, pady=(0, 6))

        self._setup_drag_and_drop()

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
                bar, text=(
                    "Documento bloqueado. Para corregirlo, devuelvelo desde Contabilidad."
                )
            ).pack(side="left", padx=2)
        elif estado == "contabilizada":
            ttk.Label(
                bar, text="Exportada a suenlace.dat. Importala en A3 y captura el asiento para confirmarla."
            ).pack(side="left", padx=2)
            ttk.Button(
                bar, text="Capturar asiento de A3", style="Primary.TButton",
                command=self._capturar_asiento_a3,
            ).pack(side="left", padx=6)

    def _build_editor(self, parent: ttk.Frame):
        """Panel fiscal inspirado en el flujo de validacion de la referencia."""
        self._entries = {
            campo: tk.StringVar()
            for campo in (
                "nif_proveedor", "nombre_proveedor", "numero_factura",
                "fecha_factura", "fecha_vencimiento", "fecha_contable",
                "total_factura", "base_total", "iva_total", "retencion_total",
                "suplidos",
            )
        }
        self._pagada_var = tk.BooleanVar(value=False)

        factura = ttk.LabelFrame(parent, text="FACTURA", style="Section.TLabelframe")
        factura.pack(fill="x", padx=8, pady=(6, 4))
        ttk.Label(factura, text="Num. factura").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(factura, textvariable=self._entries["numero_factura"]).grid(
            row=0, column=1, sticky="ew", padx=4, pady=4,
        )
        ttk.Label(factura, text="NIF").grid(row=0, column=2, sticky="w", padx=(12, 4), pady=4)
        ttk.Entry(factura, textvariable=self._entries["nif_proveedor"], width=18).grid(
            row=0, column=3, sticky="ew", padx=(0, 6), pady=4,
        )

        self._lbl_tercero = ttk.Label(factura, text="Proveedor")
        self._lbl_tercero.grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self._proveedor_var = tk.StringVar()
        self._cb_proveedor = ttk.Combobox(
            factura, textvariable=self._proveedor_var, state="normal", width=36,
        )
        self._cb_proveedor.grid(row=1, column=1, columnspan=2, sticky="ew", padx=4, pady=4)
        self._cb_proveedor.bind("<<ComboboxSelected>>", self._seleccionar_proveedor_maestro)
        proveedor_acciones = ttk.Frame(factura)
        proveedor_acciones.grid(row=1, column=3, sticky="ew", padx=6, pady=4)
        ttk.Button(
            proveedor_acciones, text="Buscar", width=9,
            command=self._buscar_proveedor_maestro,
        ).pack(
            side="left", padx=2,
        )
        ttk.Button(
            proveedor_acciones, text="Alta", width=8, command=self._alta_proveedor,
        ).pack(
            side="left", padx=2,
        )
        self._lbl_proveedor_maestro = ttk.Label(factura, text="", foreground="#555")
        self._lbl_proveedor_maestro.grid(row=2, column=1, columnspan=3, sticky="w", padx=4)

        campos_fecha = (
            ("fecha_factura", "Fecha factura", 3, 0),
            ("fecha_contable", "Fecha contable", 3, 2),
            ("fecha_vencimiento", "Vencimiento", 4, 0),
        )
        for campo, etiqueta, fila, columna in campos_fecha:
            ttk.Label(factura, text=etiqueta).grid(row=fila, column=columna, sticky="w", padx=6, pady=4)
            ttk.Entry(factura, textvariable=self._entries[campo], width=18).grid(
                row=fila, column=columna + 1, sticky="ew", padx=4, pady=4,
            )
        self._chk_pagada = ttk.Checkbutton(factura, text="Pagada", variable=self._pagada_var)
        self._chk_pagada.grid(
            row=4, column=2, sticky="w", padx=(12, 4), pady=4,
        )
        ttk.Label(factura, text="Tipo de operacion").grid(row=5, column=0, sticky="w", padx=6, pady=4)
        self._tipo_operacion_iva_var = tk.StringVar(value="INTERIOR_DEDUCIBLE")
        ttk.Combobox(
            factura, textvariable=self._tipo_operacion_iva_var,
            values=PROVEEDOR_TIPOS_IVA, state="readonly", width=30,
        ).grid(row=5, column=1, columnspan=3, sticky="ew", padx=4, pady=4)

        cuentas = ttk.LabelFrame(parent, text="CUENTAS CONTABLES", style="Section.TLabelframe")
        cuentas.pack(fill="x", padx=8, pady=4)
        self._lbl_cuenta_tercero = ttk.Label(cuentas, text="Proveedor")
        self._lbl_cuenta_tercero.grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self._subcuenta_plan_var = tk.StringVar()
        self._cb_subcuenta_plan = ttk.Combobox(
            cuentas, textvariable=self._subcuenta_plan_var, state="readonly", width=42,
        )
        self._cb_subcuenta_plan.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        self._lbl_cuenta_resultado = ttk.Label(cuentas, text="Gasto")
        self._lbl_cuenta_resultado.grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self._subcuenta_gasto_var = tk.StringVar()
        self._cuentas_gasto_por_etiqueta = {}
        self._cb_subcuenta_gasto = ttk.Combobox(
            cuentas, textvariable=self._subcuenta_gasto_var, state="readonly", width=42,
        )
        self._cb_subcuenta_gasto.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        ttk.Label(cuentas, text="Suplidos").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        self._cuenta_suplidos_var = tk.StringVar(value="55509999")
        self._cuentas_suplidos_por_etiqueta = {}
        self._cb_cuenta_suplidos = ttk.Combobox(
            cuentas, textvariable=self._cuenta_suplidos_var, state="normal", width=42,
        )
        self._cb_cuenta_suplidos.grid(row=2, column=1, sticky="ew", padx=4, pady=4)
        cuentas.columnconfigure(1, weight=1)

        fiscal = ttk.Notebook(parent)
        fiscal.pack(fill="both", expand=True, padx=8, pady=4)
        iva_frame = ttk.Frame(fiscal)
        ret_frame = ttk.Frame(fiscal)
        fiscal.add(iva_frame, text="IVA")
        fiscal.add(ret_frame, text="RETENCIONES")

        iva_cols = ("tipo_iva", "base", "cuota_iva", "cuenta_gasto", "tipo_recargo", "cuota_recargo")
        self._tv_iva = ttk.Treeview(iva_frame, columns=iva_cols, show="headings", height=8, selectmode="browse")
        titulos_iva = {
            "tipo_iva": "Tipo", "base": "Base", "cuota_iva": "Cuota",
            "cuenta_gasto": "Cuenta", "tipo_recargo": "% R.E.", "cuota_recargo": "Cuota R.E.",
        }
        for campo in iva_cols:
            self._tv_iva.heading(campo, text=titulos_iva[campo])
            self._tv_iva.column(campo, width=75 if campo != "cuenta_gasto" else 105,
                                anchor="e" if campo != "cuenta_gasto" else "w")
        self._tv_iva.pack(fill="both", expand=True, padx=4, pady=(4, 2))
        self._tv_iva.bind("<<TreeviewSelect>>", self._cargar_linea_iva_en_editor)
        self._inicializar_catalogo_iva()

        iva_editor = ttk.Frame(iva_frame)
        iva_editor.pack(fill="x", padx=4, pady=3)
        self._iva_vars = {
            "tipo_iva": tk.StringVar(value="21"), "base": tk.StringVar(),
            "cuota_iva": tk.StringVar(), "cuenta_gasto": tk.StringVar(),
            "tipo_recargo": tk.StringVar(value="0"), "cuota_recargo": tk.StringVar(value="0"),
        }
        etiquetas = (
            ("tipo_iva", "% IVA", 7), ("base", "Base", 10),
            ("cuota_iva", "Cuota", 10), ("cuenta_gasto", "Cuenta", 12),
            ("tipo_recargo", "% R.E.", 7), ("cuota_recargo", "Cuota R.E.", 10),
        )
        for columna, (campo, etiqueta, ancho) in enumerate(etiquetas):
            ttk.Label(iva_editor, text=etiqueta).grid(row=0, column=columna, sticky="w", padx=2)
            estado = "readonly" if campo == "tipo_iva" else "normal"
            if campo == "tipo_iva":
                widget = ttk.Combobox(
                    iva_editor, textvariable=self._iva_vars[campo],
                    values=tuple(f"{v:g}" for v in IVA_TIPOS_CATALOGO), width=ancho, state=estado,
                )
            else:
                widget = ttk.Entry(iva_editor, textvariable=self._iva_vars[campo], width=ancho)
            widget.grid(row=1, column=columna, sticky="ew", padx=2)
        acciones_iva = ttk.Frame(iva_editor)
        acciones_iva.grid(
            row=2, column=0, columnspan=len(etiquetas), sticky="e", pady=(5, 0),
        )
        ttk.Button(
            acciones_iva, text="Aplicar", command=self._guardar_linea_iva,
        ).pack(side="left", padx=2)
        ttk.Button(
            acciones_iva, text="Vaciar", command=self._quitar_linea_iva,
        ).pack(side="left", padx=2)
        self._btn_iva_vacias = ttk.Button(
            iva_frame, text="Ocultar lineas vacias", command=self._alternar_iva_vacias,
        )
        self._btn_iva_vacias.pack(anchor="w", padx=4, pady=(0, 4))

        ret_cols = ("base_retencion", "tipo_retencion", "importe_retencion", "clase_retencion")
        self._tv_ret = ttk.Treeview(ret_frame, columns=ret_cols, show="headings", height=5, selectmode="browse")
        for c in ret_cols:
            self._tv_ret.heading(c, text=c.replace("_", " ").title())
            self._tv_ret.column(c, width=100, anchor="e")
        self._tv_ret.pack(fill="both", expand=True, padx=4, pady=4)
        self._tv_ret.bind("<<TreeviewSelect>>", self._cargar_retencion_en_editor)
        self._ret_vars = {
            "base_retencion": tk.StringVar(), "tipo_retencion": tk.StringVar(),
            "importe_retencion": tk.StringVar(), "clase_retencion": tk.StringVar(value="PROFESIONAL"),
        }
        ret_editor = ttk.Frame(ret_frame)
        ret_editor.pack(fill="x", padx=4, pady=(0, 4))
        for columna, (campo, etiqueta) in enumerate((
            ("base_retencion", "Base"), ("tipo_retencion", "% Ret."),
            ("importe_retencion", "Retencion"), ("clase_retencion", "Clase"),
        )):
            ttk.Label(ret_editor, text=etiqueta).grid(row=0, column=columna, sticky="w", padx=2)
            if campo == "clase_retencion":
                widget = ttk.Combobox(
                    ret_editor, textvariable=self._ret_vars[campo], state="readonly",
                    values=("PROFESIONAL", "ARRENDAMIENTO", "CAPITAL"), width=16,
                )
            else:
                widget = ttk.Entry(ret_editor, textvariable=self._ret_vars[campo], width=11)
            widget.grid(row=1, column=columna, sticky="ew", padx=2)
        ttk.Button(ret_editor, text="Anadir / actualizar", command=self._guardar_retencion).grid(
            row=1, column=4, padx=(6, 2),
        )
        ttk.Button(ret_editor, text="Quitar", command=self._quitar_retencion).grid(row=1, column=5, padx=2)

        totales = ttk.LabelFrame(parent, text="TOTALES", style="Section.TLabelframe")
        totales.pack(fill="x", padx=8, pady=4)
        for columna, (campo, etiqueta) in enumerate((
            ("base_total", "Base"), ("iva_total", "IVA"),
            ("retencion_total", "Retencion"), ("suplidos", "Suplidos"),
            ("total_factura", "Total factura"),
        )):
            ttk.Label(totales, text=etiqueta).grid(row=0, column=columna, sticky="w", padx=4, pady=(4, 1))
            ttk.Entry(totales, textvariable=self._entries[campo], width=12).grid(
                row=1, column=columna, sticky="ew", padx=4, pady=(0, 6),
            )
            totales.columnconfigure(columna, weight=1)
        self._entries["suplidos"].trace_add(
            "write", lambda *_args: None if self._cargando_editor else self._recalcular_totales_iva(),
        )

        detalles = ttk.LabelFrame(parent, text="DETALLES DEL DOCUMENTO", style="Section.TLabelframe")
        detalles.pack(fill="x", padx=8, pady=4)
        self._detalle_vars = {campo: tk.StringVar() for campo in ("archivo", "origen", "motor", "confianza")}
        for fila, (campo, etiqueta) in enumerate((
            ("archivo", "Archivo"), ("origen", "Origen"),
            ("motor", "Motor OCR"), ("confianza", "Confianza"),
        )):
            ttk.Label(detalles, text=etiqueta).grid(row=fila, column=0, sticky="w", padx=6, pady=2)
            ttk.Entry(detalles, textvariable=self._detalle_vars[campo], state="readonly").grid(
                row=fila, column=1, sticky="ew", padx=4, pady=2,
            )
        detalles.columnconfigure(1, weight=1)

        self._lbl_errores = ttk.Label(parent, text="", foreground="#c0392b",
                                       wraplength=520, justify="left")
        self._lbl_errores.pack(anchor="w", fill="x", padx=8, pady=(2, 8))
        factura.columnconfigure(1, weight=1)
        factura.columnconfigure(3, weight=1, minsize=180)

    def _build_preview(self, parent: ttk.Frame):
        """Vista local de la primera pagina; no envia el documento a ningun servicio."""
        barra = ttk.Frame(parent)
        barra.pack(fill="x", padx=8, pady=(8, 4))
        self._lbl_preview = ttk.Label(barra, text="Selecciona una factura para verla.")
        self._lbl_preview.grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Button(barra, text="Abrir", command=self._abrir_documento).grid(
            row=0, column=4, sticky="e",
        )
        ttk.Button(barra, text="<", width=3, command=lambda: self._cambiar_pagina_preview(-1)).grid(
            row=1, column=0, sticky="w", pady=4,
        )
        self._lbl_pagina_preview = ttk.Label(barra, text="1 / 1")
        self._lbl_pagina_preview.grid(row=1, column=1, padx=4)
        ttk.Button(barra, text=">", width=3, command=lambda: self._cambiar_pagina_preview(1)).grid(
            row=1, column=2, sticky="w", pady=4,
        )
        ttk.Button(barra, text="Ajustar", command=self._restablecer_zoom_preview).grid(
            row=1, column=3, padx=(8, 2), pady=4,
        )
        zoom_acciones = ttk.Frame(barra)
        zoom_acciones.grid(row=1, column=4, sticky="e", pady=4)
        ttk.Button(
            zoom_acciones, text="-", width=3,
            command=lambda: self._cambiar_zoom_preview(-0.2),
        ).pack(side="left", padx=(0, 2))
        ttk.Button(
            zoom_acciones, text="+", width=3,
            command=lambda: self._cambiar_zoom_preview(0.2),
        ).pack(side="left")
        ttk.Label(barra, text="Campo:").grid(row=2, column=0, sticky="w")
        self._cb_campo_marcado = ttk.Combobox(
            barra, textvariable=self._campo_marcado_var, state="readonly", width=18,
            values=_campos_aprendizaje("factura_recibida"),
        )
        self._cb_campo_marcado.grid(row=2, column=1, columnspan=2, sticky="ew", padx=4)
        ttk.Label(
            barra, text="Marca el valor en el PDF", foreground="#555",
        ).grid(
            row=2, column=3, columnspan=2, sticky="e", padx=(6, 0),
        )
        barra.columnconfigure(3, weight=1)
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
        self._preview_auto_fit = True
        self._preview_fit_after = None
        self._preview_path = ""
        self._canvas_preview.bind("<Configure>", self._programar_ajuste_preview)
        self._canvas_preview.bind("<ButtonPress-1>", self._iniciar_marca)
        self._canvas_preview.bind("<B1-Motion>", self._actualizar_marca)
        self._canvas_preview.bind("<ButtonRelease-1>", self._terminar_marca)

    def _mostrar_preview(self, doc: dict):
        self._actualizar_campos_aprendizaje(
            str(doc.get("tipo_documento") or "factura_recibida")
        )
        ruta = Path(str(doc.get("ruta_original") or ""))
        self._preview_path = str(ruta)
        self._preview_photo = None
        self._preview_imagen_original = None
        self._canvas_preview.delete("all")
        self._marcas_campos = {}
        self._preview_page = 0
        self._preview_page_count = self._contar_paginas_preview(ruta)
        if not ruta.exists():
            self._lbl_preview.configure(text=f"No se encuentra el documento original: {ruta}")
            return
        try:
            imagen = self._cargar_pagina(ruta, self._preview_page)
            self._preview_imagen_original = imagen
            self._preview_auto_fit = True
            self._ajustar_preview_al_documento()
            self._actualizar_etiqueta_pagina()
        except Exception as exc:
            self._lbl_preview.configure(text=f"No se pudo generar la vista previa: {exc}")
            self._canvas_preview.create_text(20, 20, anchor="nw", text="Usa 'Abrir documento' para verlo en el visor PDF.")

    def _contar_paginas_preview(self, ruta: Path) -> int:
        if not ruta.exists() or ruta.suffix.lower() != ".pdf":
            return 1
        try:
            import fitz
            with fitz.open(str(ruta)) as pdf:
                return max(1, int(pdf.page_count))
        except Exception:
            return 1

    def _actualizar_etiqueta_pagina(self):
        pagina = self._preview_page + 1
        self._lbl_pagina_preview.configure(text=f"{pagina} / {self._preview_page_count}")
        nombre = Path(self._preview_path).name if self._preview_path else "Documento"
        self._lbl_preview.configure(text=f"{nombre} - pagina {pagina}")

    def _cambiar_pagina_preview(self, desplazamiento: int):
        if not self._preview_path:
            return
        nueva = max(0, min(self._preview_page_count - 1, self._preview_page + desplazamiento))
        if nueva == self._preview_page:
            return
        try:
            self._preview_page = nueva
            self._preview_imagen_original = self._cargar_pagina(Path(self._preview_path), nueva)
            self._preview_auto_fit = True
            self._ajustar_preview_al_documento()
            self._actualizar_etiqueta_pagina()
        except Exception as exc:
            messagebox.showerror("OCR", f"No se pudo cargar la pagina {nueva + 1}:\n{exc}")

    def _cambiar_zoom_preview(self, incremento: float):
        if self._preview_imagen_original is None:
            return
        self._preview_auto_fit = False
        self._preview_zoom = max(0.3, min(3.0, self._preview_zoom + incremento))
        self._aplicar_zoom_preview()

    def _restablecer_zoom_preview(self):
        if self._preview_imagen_original is None:
            return
        self._preview_auto_fit = True
        self._ajustar_preview_al_documento()

    def _programar_ajuste_preview(self, _event=None):
        if not self._preview_auto_fit or self._preview_imagen_original is None:
            return
        if self._preview_fit_after is not None:
            self.after_cancel(self._preview_fit_after)
        self._preview_fit_after = self.after(100, self._ajustar_preview_al_documento)

    def _ajustar_preview_al_documento(self):
        self._preview_fit_after = None
        if self._preview_imagen_original is None:
            return
        self._canvas_preview.update_idletasks()
        self._preview_zoom = _zoom_para_ajustar(
            self._preview_imagen_original.width,
            self._preview_imagen_original.height,
            self._canvas_preview.winfo_width(),
            self._canvas_preview.winfo_height(),
        )
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
                "page": self._preview_page,
                "x": round(max(0, left) / self._preview_zoom, 2),
                "y": round(max(0, top) / self._preview_zoom, 2),
                "width": round(min(width, right / self._preview_zoom) - max(0, left) / self._preview_zoom, 2),
                "height": round(min(height, bottom / self._preview_zoom) - max(0, top) / self._preview_zoom, 2),
            }
            self._marcas_campos[campo] = marca
            texto = self._extraer_texto_marca(marca)
            entry_campo = CAMPO_MARCA_A_ENTRY_COMUN.get(campo, campo)
            if texto and entry_campo in self._entries:
                self._entries[entry_campo].set(texto)
        self._marca_inicio = None
        self._marca_rect_id = None
        self._dibujar_marcas()

    def _dibujar_marcas(self):
        if self._preview_imagen_original is None:
            return
        self._canvas_preview.delete("marca")
        for campo, marca in self._marcas_campos.items():
            if int(marca.get("page") or 0) != self._preview_page:
                continue
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
                page = pdf.load_page(self._preview_page)
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

    def _cargar_pagina(self, ruta: Path, numero_pagina: int = 0):
        from PIL import Image
        if ruta.suffix.lower() != ".pdf":
            imagen = Image.open(ruta)
            imagen.thumbnail((1250, 1200))
            return imagen.copy()
        try:
            import fitz
            pdf = fitz.open(str(ruta))
            try:
                pagina = pdf.load_page(numero_pagina)
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
                [ejecutable, "-f", str(numero_pagina + 1), "-l", str(numero_pagina + 1), "-singlefile", "-scale-to", "1400", "-png", str(ruta), str(prefijo)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            png = next(carpeta.glob("pagina.png"), None)
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
        es_emitida = str((self._doc_seleccionado or {}).get("tipo_documento") or "") == "factura_emitida"
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
            cuenta = str(tercero.get("subcuenta_cliente" if es_emitida else "subcuenta_proveedor") or "").strip()
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
        es_emitida = str((self._doc_seleccionado or {}).get("tipo_documento") or "") == "factura_emitida"
        prefijos = ("430",) if es_emitida else ("400", "410")
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
            if not codigo.startswith(prefijos):
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
                if codigo in codigos_vistos or not codigo.startswith(prefijos):
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
        """Carga cuentas de gasto o ingreso del plan contable de la empresa."""
        es_emitida = str((self._doc_seleccionado or {}).get("tipo_documento") or "") == "factura_emitida"
        iniciales = "7" if es_emitida else "6"
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
            if not codigo or codigo in vistos or codigo[0] not in iniciales:
                continue
            vistos.add(codigo)
            texto = f"{codigo} - {str(cuenta.get('nombre_subcuenta') or cuenta.get('descripcion') or '').strip()}".rstrip(" -")
            self._cuentas_gasto_por_etiqueta[texto] = codigo
            etiquetas.append(texto)
        self._cb_subcuenta_gasto.configure(values=etiquetas)
        self._subcuenta_gasto_var.set(next((e for e, c in self._cuentas_gasto_por_etiqueta.items() if c == str(seleccionada or "")), ""))

    def _subcuenta_gasto_seleccionada(self) -> str:
        return self._cuentas_gasto_por_etiqueta.get(self._subcuenta_gasto_var.get(), "")

    def _cargar_subcuentas_suplidos(self, seleccionada: str = ""):
        """Carga cuentas candidatas para suplidos, permitiendo escritura manual."""
        self._cuentas_suplidos_por_etiqueta.clear()
        cuentas = []
        try:
            cuentas = list(self._gestor.listar_maestro_subcuentas_empresa(self._codigo, activo=None) or [])
        except Exception:
            pass
        etiquetas, vistos = [], set()
        for cuenta in cuentas:
            codigo = str(cuenta.get("subcuenta") or cuenta.get("cuenta") or "").strip()
            if not codigo or codigo in vistos or not codigo.startswith(("55", "56")):
                continue
            vistos.add(codigo)
            descripcion = str(cuenta.get("nombre_subcuenta") or cuenta.get("descripcion") or "").strip()
            etiqueta = f"{codigo} - {descripcion}".rstrip(" -")
            self._cuentas_suplidos_por_etiqueta[etiqueta] = codigo
            etiquetas.append(etiqueta)
        self._cb_cuenta_suplidos.configure(values=etiquetas)
        seleccion = str(seleccionada or "55509999").strip()
        self._cuenta_suplidos_var.set(
            next((e for e, c in self._cuentas_suplidos_por_etiqueta.items() if c == seleccion), seleccion)
        )

    def _cuenta_suplidos_seleccionada(self) -> str:
        texto = self._cuenta_suplidos_var.get().strip()
        return self._cuentas_suplidos_por_etiqueta.get(texto, texto.split(" - ", 1)[0].strip())

    def _aplicar_proveedor_maestro(self, tercero: dict):
        tercero_id = str(tercero.get("id") or "").strip()
        if not tercero_id:
            return
        self._proveedor_id_seleccionado = tercero_id
        self._entries["nif_proveedor"].set(normalizar_nif_cif(tercero.get("nif")))
        self._entries["nombre_proveedor"].set(str(tercero.get("nombre") or tercero.get("nombre_legal") or ""))
        es_emitida = str((self._doc_seleccionado or {}).get("tipo_documento") or "") == "factura_emitida"
        tipo = str(tercero.get("proveedor_tipo_operacion_iva") or "").strip()
        if tipo in PROVEEDOR_TIPOS_IVA:
            self._tipo_operacion_iva_var.set(tipo)
        cuenta = str(tercero.get("subcuenta_cliente" if es_emitida else "subcuenta_proveedor") or "").strip()
        self._cargar_subcuentas_plan_empresa(cuenta)
        self._cargar_subcuentas_gasto(str(
            tercero.get("subcuenta_ingreso" if es_emitida else "subcuenta_gasto") or ""
        ))
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
            es_emitida = str(
                (self._doc_seleccionado or {}).get("tipo_documento") or ""
            ) == "factura_emitida"
            tipo_tercero = "cliente" if es_emitida else "proveedor / acreedor"
            self._lbl_proveedor_maestro.configure(
                text=f"No existe en el maestro. Usa Alta de {tipo_tercero}."
            )
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

    def _asegurar_cliente_en_empresa(self):
        """Guarda las cuentas elegidas para un cliente de factura emitida OCR."""
        tercero_id = str(self._proveedor_id_seleccionado or "")
        if not tercero_id:
            return
        relacion = self._gestor.get_tercero_empresa(
            self._codigo, tercero_id, self._ejercicio,
        ) or {"codigo_empresa": self._codigo, "tercero_id": tercero_id}
        relacion["subcuenta_cliente"] = self._subcuenta_plan_seleccionada()
        relacion["subcuenta_ingreso"] = self._subcuenta_gasto_seleccionada()
        self._gestor.upsert_tercero_empresa(relacion)

    def _alta_proveedor(self):
        es_emitida = str(
            (self._doc_seleccionado or {}).get("tipo_documento") or ""
        ) == "factura_emitida"
        dialog = tk.Toplevel(self)
        dialog.title("Alta de cliente" if es_emitida else "Alta de proveedor / acreedor")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        nif = tk.StringVar(value=normalizar_nif_cif(self._entries["nif_proveedor"].get()))
        nombre = tk.StringVar(value=self._entries["nombre_proveedor"].get().strip())
        clase = tk.StringVar(value="cliente" if es_emitida else "proveedor")
        for fila, (texto, var) in enumerate((("NIF", nif), ("Nombre", nombre))):
            ttk.Label(frame, text=texto).grid(row=fila, column=0, sticky="e", padx=(0, 6), pady=3)
            ttk.Entry(frame, textvariable=var, width=42).grid(row=fila, column=1, sticky="ew", pady=3)
        ttk.Label(frame, text="Clase").grid(row=2, column=0, sticky="e", padx=(0, 6), pady=3)
        ttk.Combobox(
            frame, textvariable=clase,
            values=(("cliente",) if es_emitida else ("proveedor", "acreedor")),
            state="readonly", width=18,
        ).grid(row=2, column=1, sticky="w", pady=3)

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
            lineas.append("Por tercero (proveedor o cliente, segun el documento):")
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
                from utils.credential_store import get_azure_storage_conn
                _conn_str = (
                    get_azure_storage_conn()
                    or os.getenv("GEST2A3ECO_AZURE_STORAGE_CONNECTION_STRING", "")
                )
                resultado = AprendizajeOcrService(self._gestor, self._codigo).exportar_a_blob(
                    connection_string=_conn_str,
                    container=str(cfg.get("azure_ocr_training_container") or "facturas-entrenamiento"),
                )
                messagebox.showinfo("Aprendizaje OCR", f"Documentos subidos: {resultado['subidos']}\nOmitidos: {resultado['omitidos']}\n\nAhora revisa y etiqueta los PDF en Document Intelligence Studio.", parent=dialog)
                dialog.destroy()
            except Exception as exc:
                messagebox.showerror("Aprendizaje OCR", str(exc), parent=dialog)
        ttk.Button(actions, text="Exportar pendientes a Azure", command=exportar).pack(side="left")
        ttk.Button(actions, text="Cerrar", command=dialog.destroy).pack(side="right")

    def _inicializar_catalogo_iva(self):
        for item in list(self._iva_catalog_items):
            if self._tv_iva.exists(item):
                self._tv_iva.delete(item)
        otros = self._tv_iva.get_children()
        if otros:
            self._tv_iva.delete(*otros)
        self._iva_catalog_items = []
        for tipo in IVA_TIPOS_CATALOGO:
            iid = "iva_" + str(tipo).replace(".", "_")
            self._tv_iva.insert(
                "", "end", iid=iid,
                values=(f"{tipo:g}", "", "", "", "0", "0"),
            )
            self._iva_catalog_items.append(iid)

    def _cargar_linea_iva_en_editor(self, _event=None):
        seleccion = self._tv_iva.selection()
        if not seleccion:
            return
        valores = self._tv_iva.item(seleccion[0], "values")
        for campo, valor in zip(("tipo_iva", "base", "cuota_iva", "cuenta_gasto", "tipo_recargo", "cuota_recargo"), valores):
            self._iva_vars[campo].set(str(valor))

    def _guardar_linea_iva(self):
        try:
            tipo = _parse_importe(self._iva_vars["tipo_iva"].get())
            base = _parse_importe(self._iva_vars["base"].get())
            cuota = _parse_importe(self._iva_vars["cuota_iva"].get())
            tipo_recargo = _parse_importe(self._iva_vars["tipo_recargo"].get())
            cuota_recargo = _parse_importe(self._iva_vars["cuota_recargo"].get())
        except ValueError:
            messagebox.showerror("OCR", "Los valores de la linea de IVA deben ser numericos.")
            return
        if not 0 <= tipo <= 100:
            messagebox.showerror("OCR", "El tipo de IVA debe estar entre 0 y 100.")
            return
        cuenta = self._iva_vars["cuenta_gasto"].get().strip()
        fila = (f"{tipo:g}", f"{base:.2f}", f"{cuota:.2f}", cuenta,
                f"{tipo_recargo:g}", f"{cuota_recargo:.2f}")
        seleccion = self._tv_iva.selection()
        if seleccion:
            self._tv_iva.item(seleccion[0], values=fila)
        else:
            iid = next((item for item in self._iva_catalog_items
                        if _parse_importe(self._tv_iva.item(item, "values")[0]) == tipo), None)
            if iid:
                self._tv_iva.item(iid, values=fila)
        self._recalcular_totales_iva()
        if self._ocultar_iva_vacias:
            self._aplicar_filtro_iva()

    def _quitar_linea_iva(self):
        for item in self._tv_iva.selection():
            tipo = self._tv_iva.item(item, "values")[0]
            self._tv_iva.item(item, values=(tipo, "", "", "", "0", "0"))
        for var in self._iva_vars.values():
            var.set("")
        self._iva_vars["tipo_iva"].set("21")
        self._iva_vars["tipo_recargo"].set("0")
        self._recalcular_totales_iva()

    def _alternar_iva_vacias(self):
        self._ocultar_iva_vacias = not self._ocultar_iva_vacias
        self._btn_iva_vacias.configure(
            text="Mostrar lineas vacias" if self._ocultar_iva_vacias else "Ocultar lineas vacias",
        )
        self._aplicar_filtro_iva()

    def _aplicar_filtro_iva(self):
        for indice, item in enumerate(self._iva_catalog_items):
            valores = self._tv_iva.item(item, "values")
            tiene_importe = any(abs(_parse_importe(v)) > 0 for v in (valores[1], valores[2], valores[4], valores[5]))
            if self._ocultar_iva_vacias and not tiene_importe:
                self._tv_iva.detach(item)
            else:
                self._tv_iva.move(item, "", indice)

    def _lineas_iva_editor(self) -> list[dict]:
        lineas = []
        for item in self._iva_catalog_items:
            valores = self._tv_iva.item(item, "values")
            try:
                tipo = _parse_importe(valores[0])
                base = _parse_importe(valores[1])
                cuota = _parse_importe(valores[2])
                tipo_recargo = _parse_importe(valores[4])
                cuota_recargo = _parse_importe(valores[5])
            except ValueError:
                raise ValueError("Hay una linea de IVA con importes invalidos.")
            if not any(abs(v) > 0 for v in (base, cuota, cuota_recargo)):
                continue
            lineas.append({
                "tipo_iva": tipo, "base": base, "cuota_iva": cuota,
                "tipo_recargo": tipo_recargo, "cuota_recargo": cuota_recargo,
                "cuenta_gasto": str(valores[3] or "").strip(),
            })
        return lineas

    def _cargar_retencion_en_editor(self, _event=None):
        seleccion = self._tv_ret.selection()
        if not seleccion:
            return
        valores = self._tv_ret.item(seleccion[0], "values")
        for campo, valor in zip(self._ret_vars, valores):
            self._ret_vars[campo].set(str(valor))

    def _guardar_retencion(self):
        try:
            base = _parse_importe(self._ret_vars["base_retencion"].get())
            tipo = _parse_importe(self._ret_vars["tipo_retencion"].get())
            importe = _parse_importe(self._ret_vars["importe_retencion"].get())
        except ValueError:
            messagebox.showerror("OCR", "Los valores de la retencion deben ser numericos.")
            return
        clase = self._ret_vars["clase_retencion"].get().strip() or "PROFESIONAL"
        valores = (f"{base:.2f}", f"{tipo:g}", f"{importe:.2f}", clase)
        seleccion = self._tv_ret.selection()
        if seleccion:
            self._tv_ret.item(seleccion[0], values=valores)
        else:
            self._tv_ret.insert("", "end", values=valores)
        self._recalcular_totales_iva()

    def _quitar_retencion(self):
        for item in self._tv_ret.selection():
            self._tv_ret.delete(item)
        for var in self._ret_vars.values():
            var.set("")
        self._ret_vars["clase_retencion"].set("PROFESIONAL")
        self._recalcular_totales_iva()

    def _retenciones_editor(self) -> list[dict]:
        resultado = []
        for item in self._tv_ret.get_children():
            valores = self._tv_ret.item(item, "values")
            try:
                base, tipo, importe = [_parse_importe(v) for v in valores[:3]]
            except ValueError as exc:
                raise ValueError("Hay una retencion con importes invalidos.") from exc
            if not any(abs(v) > 0 for v in (base, tipo, importe)):
                continue
            resultado.append({
                "base_retencion": base, "tipo_retencion": tipo,
                "importe_retencion": importe,
                "clase_retencion": str(valores[3] or "PROFESIONAL"),
            })
        return resultado

    def _recalcular_totales_iva(self):
        try:
            lineas = self._lineas_iva_editor()
        except ValueError:
            return
        if not lineas:
            return
        try:
            retenciones = self._retenciones_editor()
            suplidos = _parse_importe(self._entries["suplidos"].get())
        except (ValueError, tk.TclError):
            return
        resumen = _resumen_fiscal(lineas, retenciones, suplidos)
        self._entries["base_total"].set(f"{resumen['base']:.2f}")
        self._entries["iva_total"].set(f"{resumen['iva']:.2f}")
        self._entries["retencion_total"].set(f"{resumen['retencion']:.2f}")
        self._entries["total_factura"].set(f"{resumen['total_esperado']:.2f}")

    # ── Refresco de bandejas ──────────────────────────────────────────────────

    def _refresh_all(self):
        for estado, _ in BANDEJAS:
            self._refresh_bandeja(estado)

    def _refresh_bandeja(self, estado: str):
        tipo_doc = self._tipo_doc_var.get()
        # Cargar documentos OCR por estado (via tabla documentos_ocr)
        try:
            todos_docs = self._gestor.listar_documentos_ocr(self._empresa_id, estado)
            # Filtrar por tipo de documento seleccionado
            docs = [
                d for d in todos_docs
                if str(d.get("tipo_documento") or "factura_recibida") == tipo_doc
            ]
        except Exception:
            # Compatibilidad: si metodo no existe, fallback
            docs = []

        # Enriquecer con datos de factura
        enriquecidos = []
        for doc in docs:
            factura = None
            if tipo_doc == "factura_emitida":
                try:
                    cur = self._gestor.conn.execute(
                        "SELECT * FROM facturas_emitidas_ocr WHERE documento_id=?",
                        (doc["id"],),
                    )
                    row = cur.fetchone()
                    if row:
                        cols = [c[0] for c in cur.description]
                        raw = dict(zip(cols, row))
                        # Mapear campos para compatibilidad con COLS_LISTA
                        factura = raw
                        factura["nif_proveedor"] = raw.get("nif_cliente") or ""
                        factura["nombre_proveedor"] = raw.get("nombre_cliente") or ""
                except Exception:
                    pass
            else:
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
        ttk.Label(cabecera, text="Detalle de la factura", font=("Segoe UI", 13, "bold")).pack(side="left")
        ttk.Button(cabecera, text="Cerrar", command=self._cerrar_ventana_revision).pack(side="right")
        self._btn_revision_validar = ttk.Button(
            cabecera, text="Validar", style="Primary.TButton", command=self._validar_seleccionado,
        )
        self._btn_revision_validar.pack(side="right", padx=4)
        self._btn_revision_guardar = ttk.Button(cabecera, text="Guardar", command=self._guardar)
        self._btn_revision_guardar.pack(side="right", padx=4)
        self._btn_revision_reprocesar = ttk.Button(
            cabecera, text="Reprocesar", command=self._reprocesar_seleccionado,
        )
        self._btn_revision_reprocesar.pack(side="right", padx=4)
        estado_texto = str(doc.get("estado") or "pendiente").replace("_", " ").title()
        self._lbl_estado_revision = ttk.Label(cabecera, text=f"Estado: {estado_texto}", foreground="#002C57")
        self._lbl_estado_revision.pack(side="right", padx=12)

        # En la ventana propia hay espacio para trabajar en dos columnas:
        # documento grande a la izquierda y datos editables a la derecha.
        detalle = tk.PanedWindow(
            ventana, orient="horizontal", sashwidth=7, sashrelief="raised",
            borderwidth=0, background="#d1d5db",
        )
        detalle.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        preview = ttk.Frame(detalle)
        editor_shell = ttk.Frame(detalle)
        detalle.add(preview, minsize=360, stretch="always")
        detalle.add(editor_shell, minsize=740, stretch="always")
        self._build_preview(preview)
        self._build_editor(self._crear_editor_desplazable(editor_shell))
        self._actualizar_etiquetas_editor(
            str(doc.get("tipo_documento") or "factura_recibida") == "factura_emitida"
        )
        self._cargar_factura_en_editor(str(doc.get("id") or ""))
        self._mostrar_preview(doc)

        def ajustar_paneles_iniciales():
            """Reserva al formulario su ancho util y deja el resto al PDF."""
            total = detalle.winfo_width()
            if total <= 1:
                return
            ancho_editor = min(max(740, round(total * 0.56)), max(740, total - 360))
            detalle.sash_place(0, max(360, total - ancho_editor), 0)
            self._ajustar_preview_al_documento()

        ventana.after_idle(ajustar_paneles_iniciales)
        if estado_revision in ("pendiente_contabilizar", "contabilizada"):
            self._btn_revision_guardar.configure(state="disabled")
            self._btn_revision_validar.configure(state="disabled")
            self._btn_revision_reprocesar.configure(state="disabled")
            self._bloquear_editor_revision(editor_shell)

    def _bloquear_editor_revision(self, contenedor):
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

    def _cerrar_ventana_revision(self):
        if self._revision_window and self._revision_window.winfo_exists():
            self._revision_window.destroy()
        self._revision_window = None
        self._editor_activo = False

    def _cargar_factura_en_editor(self, doc_id: str):
        """Carga datos de la tabla OCR correspondiente en el editor."""
        tipo = str((self._doc_seleccionado or {}).get("tipo_documento") or "factura_recibida")
        try:
            if tipo == "factura_emitida":
                cur = self._gestor.conn.execute(
                    "SELECT * FROM facturas_emitidas_ocr WHERE documento_id=?", (doc_id,)
                )
            else:
                cur = self._gestor.conn.execute(
                    "SELECT * FROM facturas_recibidas_ocr WHERE documento_id=?", (doc_id,)
                )
            row = cur.fetchone()
            if not row:
                self._limpiar_editor()
                return
            cols = [c[0] for c in cur.description]
            factura = dict(zip(cols, row))
            # Para emitidas, mapear campos al esquema del editor (que usa nombres de recibidas)
            if tipo == "factura_emitida":
                factura.setdefault("nif_proveedor", factura.get("nif_cliente") or "")
                factura.setdefault("nombre_proveedor", factura.get("nombre_cliente") or "")
                factura.setdefault("proveedor_id", factura.get("cliente_id") or "")
                factura.setdefault("pagada", factura.get("cobrada") or 0)
                factura.setdefault("tipo_operacion_iva", factura.get("tipo_operacion") or "INTERIOR_DEDUCIBLE")
        except Exception:
            self._limpiar_editor()
            return

        self._factura_seleccionada = factura
        self._cargando_editor = True
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
        campo_cuenta_tercero = "subcuenta_cliente" if tipo == "factura_emitida" else "subcuenta_proveedor"
        campo_cuenta_resultado = "subcuenta_ingreso" if tipo == "factura_emitida" else "subcuenta_gasto"
        self._cargar_subcuentas_plan_empresa(
            str((relacion or {}).get(campo_cuenta_tercero) or "")
        )
        self._cargar_subcuentas_gasto(
            str(
                (relacion or {}).get(campo_cuenta_resultado)
                or factura.get("cuenta_ingreso" if tipo == "factura_emitida" else "cuenta_gasto")
                or ""
            )
        )
        self._cargar_subcuentas_suplidos(str(factura.get("cuenta_suplidos") or "55509999"))
        self._tipo_operacion_iva_var.set(
            str(factura.get("tipo_operacion_iva") or "INTERIOR_DEDUCIBLE")
        )
        self._lbl_proveedor_maestro.configure(text="Sin vincular al maestro." if not self._proveedor_id_seleccionado else "Vinculado al maestro.")

        # Rellenar entradas de cabecera
        for campo, var in self._entries.items():
            val = factura.get(campo)
            if campo == "fecha_contable" and not val:
                val = factura.get("fecha_factura")
            var.set("" if val is None else str(val))
        self._pagada_var.set(bool(factura.get("pagada")))

        # Lineas IVA
        self._inicializar_catalogo_iva()
        try:
            if tipo == "factura_emitida":
                lineas = self._gestor.listar_lineas_iva_emitida_ocr(factura["id"])
                for l in lineas:
                    tipo_iva = float(l.get("tipo_iva") or 0.0)
                    item = next((iid for iid in self._iva_catalog_items
                                 if abs(_parse_importe(self._tv_iva.item(iid, "values")[0]) - tipo_iva) < 0.001), None)
                    if item:
                        self._tv_iva.item(item, values=(
                            f"{tipo_iva:g}", l.get("base", ""), l.get("cuota_iva", ""),
                            l.get("cuenta_ingreso", ""), l.get("tipo_recargo", ""),
                            l.get("cuota_recargo", ""),
                        ))
            else:
                lineas = self._gestor.listar_lineas_iva_ocr(factura["id"])
                for l in lineas:
                    tipo_iva = float(l.get("tipo_iva") or 0.0)
                    item = next((iid for iid in self._iva_catalog_items
                                 if abs(_parse_importe(self._tv_iva.item(iid, "values")[0]) - tipo_iva) < 0.001), None)
                    if item:
                        self._tv_iva.item(item, values=(
                            f"{tipo_iva:g}", l.get("base", ""), l.get("cuota_iva", ""),
                            l.get("cuenta_gasto", ""), l.get("tipo_recargo", ""),
                            l.get("cuota_recargo", ""),
                        ))
        except Exception:
            pass

        # Retenciones
        self._tv_ret.delete(*self._tv_ret.get_children())
        try:
            if tipo == "factura_emitida":
                rets = self._gestor.listar_retenciones_emitida_ocr(factura["id"])
            else:
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
        doc = self._doc_seleccionado or {}
        self._detalle_vars["archivo"].set(str(doc.get("nombre_archivo") or ""))
        self._detalle_vars["origen"].set(str(doc.get("tipo_documento") or "factura_recibida"))
        self._detalle_vars["motor"].set(str(doc.get("motor_ocr") or ""))
        confianza = _normalizar_confianza(doc.get("confianza_global"))
        self._detalle_vars["confianza"].set(f"{confianza * 100:.0f} %")
        self._cargando_editor = False

    def _limpiar_editor(self):
        if not self._editor_activo:
            self._factura_seleccionada = None
            self._proveedor_id_seleccionado = ""
            return
        for var in self._entries.values():
            var.set("")
        self._inicializar_catalogo_iva()
        for var in self._iva_vars.values():
            var.set("")
        self._iva_vars["tipo_iva"].set("21")
        self._iva_vars["tipo_recargo"].set("0")
        self._tv_ret.delete(*self._tv_ret.get_children())
        for var in self._ret_vars.values():
            var.set("")
        self._ret_vars["clase_retencion"].set("PROFESIONAL")
        self._lbl_errores.configure(text="")
        self._factura_seleccionada = None
        self._proveedor_id_seleccionado = ""
        self._proveedor_var.set("")
        self._subcuenta_plan_var.set("")
        self._subcuenta_gasto_var.set("")
        self._cuenta_suplidos_var.set("55509999")
        self._pagada_var.set(False)
        self._tipo_operacion_iva_var.set("INTERIOR_DEDUCIBLE")
        self._lbl_proveedor_maestro.configure(text="")
        for var in self._detalle_vars.values():
            var.set("")

    def _on_tab_changed(self, _e):
        idx = self._nb.index(self._nb.select())
        estado = BANDEJAS[idx][0]
        self._refresh_bandeja(estado)

    def _on_tipo_doc_changed(self):
        """Refresca las bandejas al cambiar el tipo de factura."""
        self._actualizar_campos_aprendizaje(self._tipo_doc_var.get())
        self._actualizar_cabeceras_listado(self._tipo_doc_var.get())
        self._refresh_all()

    def _actualizar_cabeceras_listado(self, tipo_documento: str):
        """Evita mostrar 'Proveedor' al consultar facturas de cliente."""
        titulo_tercero = (
            "Cliente" if tipo_documento == "factura_emitida" else "Proveedor"
        )
        for treeview in self._tvs.values():
            treeview.heading("proveedor_nombre", text=titulo_tercero)

    def _actualizar_campos_aprendizaje(self, tipo_documento: str):
        """Muestra etiquetas de proveedor o cliente segun el documento."""
        campos = _campos_aprendizaje(tipo_documento)
        combobox = getattr(self, "_cb_campo_marcado", None)
        if combobox is not None:
            combobox.configure(values=campos)
        if self._campo_marcado_var.get() not in campos:
            self._campo_marcado_var.set(campos[0])

    def _tipo_doc_activo(self) -> str:
        return self._tipo_doc_var.get()

    def _actualizar_etiquetas_editor(self, es_emitida: bool):
        """Adapta el mismo editor fiscal a proveedor o cliente."""
        self._lbl_tercero.configure(text="Cliente" if es_emitida else "Proveedor")
        self._lbl_cuenta_tercero.configure(text="Cliente" if es_emitida else "Proveedor")
        self._lbl_cuenta_resultado.configure(text="Ingreso" if es_emitida else "Gasto")
        self._chk_pagada.configure(text="Cobrada" if es_emitida else "Pagada")

    # ── Drag & Drop ───────────────────────────────────────────────────────────

    def _setup_drag_and_drop(self):
        """Registra la zona de arrastre en el panel de bandejas."""
        raiz = self.winfo_toplevel()
        if getattr(raiz, "_dnd_available", True) is False:
            detalle = str(getattr(raiz, "_dnd_error", "") or "").strip()
            self._mostrar_dnd_no_disponible(detalle)
            return
        try:
            from tkinterdnd2 import DND_FILES
            targets = [self._zona_arrastre, *self._tvs.values(), self._nb, self._frm_lista, self]
            registrados = 0
            ultimo_error = None
            for target in targets:
                try:
                    target.drop_target_register(DND_FILES)
                    target.dnd_bind("<<Drop>>", self._on_dnd_drop)
                    target.dnd_bind("<<DragEnter>>", self._on_dnd_enter)
                    target.dnd_bind("<<DragLeave>>", self._on_dnd_leave)
                    registrados += 1
                except Exception as exc:
                    ultimo_error = exc
            if not registrados:
                raise RuntimeError(str(ultimo_error or "No se pudo registrar la zona de arrastre."))
            raiz._dnd_available = True
        except Exception as exc:
            logger.warning("[OCR] Arrastre no disponible: %s", exc)
            self._mostrar_dnd_no_disponible(str(exc))

    def _mostrar_dnd_no_disponible(self, detalle: str = ""):
        texto = "Arrastre no disponible. Haz clic aquí para seleccionar PDF o imágenes."
        self._zona_arrastre.configure(text=texto)
        self._lbl_status.configure(
            text=(
                "No se pudo activar el arrastre de Windows. Puedes importar con un clic."
                + (f" Detalle: {detalle}" if detalle else "")
            )
        )

    def _on_dnd_enter(self, event):
        try:
            self._zona_arrastre.configure(text="Suelta los documentos para procesarlos")
        except Exception:
            pass
        return getattr(event, "action", "copy")

    def _on_dnd_leave(self, event):
        try:
            self._restaurar_texto_arrastre()
        except Exception:
            pass
        return getattr(event, "action", "copy")

    def _on_dnd_drop(self, event):
        try:
            self._restaurar_texto_arrastre()
        except Exception:
            pass
        paths = self._parse_dnd_paths(event.data)
        validos = [p for p in paths if Path(p).suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"}]
        if not validos:
            messagebox.showwarning("OCR", "Ningun fichero soportado arrastrado.")
            return getattr(event, "action", "copy")
        self._iniciar_procesamiento(validos)
        return getattr(event, "action", "copy")

    def _restaurar_texto_arrastre(self):
        self._zona_arrastre.configure(
            text="Arrastra aquí uno o varios PDF o imágenes, o pulsa «Importar PDF / imagen»"
        )

    @staticmethod
    def _parse_dnd_paths(raw: str) -> list[str]:
        """Parsea el formato Tcl list de tkinterdnd2 (paths con espacios entre llaves)."""
        import re
        paths = []
        for m in re.finditer(r'\{([^}]+)\}|(\S+)', raw):
            p = m.group(1) or m.group(2)
            if p:
                paths.append(p)
        return paths

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
        self._iniciar_procesamiento(validos)

    def _iniciar_procesamiento(self, paths: list[str]):
        if self._ocr_thread and self._ocr_thread.is_alive():
            messagebox.showwarning("OCR", "Ya hay documentos procesándose.")
            return
        tipo_documento = self._tipo_doc_var.get()
        fecha_contable = (
            datetime.now().strftime("%Y-%m-%d")
            if self._fecha_contable_modo_var.get() == "Hoy"
            else ""
        )
        self._lbl_status.configure(text=f"Procesando {len(paths)} documento(s)...")
        self._ocr_mensajes = []
        self._bloquear_opciones_importacion(True)
        t = threading.Thread(
            target=self._worker_ocr,
            args=(paths, tipo_documento, fecha_contable),
            daemon=True,
        )
        self._ocr_thread = t
        t.start()
        self.after(75, self._poll_ocr)

    def _bloquear_opciones_importacion(self, bloquear: bool):
        estado = "disabled" if bloquear else "normal"
        self._btn_importar.configure(state=estado)
        self._radio_recibida.configure(state=estado)
        self._radio_emitida.configure(state=estado)
        self._cb_fecha_contable_modo.configure(
            state="disabled" if bloquear else "readonly"
        )

    def _worker_ocr(
        self, paths: list[str], tipo_documento: str, fecha_contable: str,
    ):
        try:
            from services.ocr import OcrService
            svc = OcrService(
                gestor=self._gestor,
                empresa_id=self._codigo,
                ejercicio=self._ejercicio,
                usuario=getattr(self._session, "usuario", ""),
                tipo_documento=tipo_documento,
                fecha_contable=fecha_contable,
            )
            for path in paths:
                try:
                    resultado = svc.procesar_archivo(
                        path,
                        progress_callback=lambda documento: self._ocr_q.put(
                            ("progress", documento)
                        ),
                    )
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
        mensajes = self._ocr_mensajes
        try:
            while True:
                tipo, payload = self._ocr_q.get_nowait()
                if tipo == "done":
                    done = True
                elif tipo == "progress":
                    changed = True
                    nombre = str((payload or {}).get("nombre_archivo") or "documento")
                    self._lbl_status.configure(text=f"Procesando {nombre}...")
                elif tipo == "ok":
                    changed = True
                    if payload.get("errores") and payload.get("estado") in {
                        "error", "duplicado",
                    }:
                        mensajes.extend(str(error) for error in payload["errores"])
                elif tipo == "error":
                    logger.warning("[UIFacturasRecibidasOcr] Worker OCR: %s", payload)
                    mensajes.append(str(payload))
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
            self._lbl_status.configure(
                text=" · ".join(dict.fromkeys(mensajes)) if mensajes else "Procesamiento finalizado."
            )
            self._ocr_thread = None
            self._bloquear_opciones_importacion(False)
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
        self._ocr_mensajes = []
        self._bloquear_opciones_importacion(True)
        t = threading.Thread(target=self._worker_reprocesar, args=(doc_id,), daemon=True)
        self._ocr_thread = t
        t.start()
        self.after(75, self._poll_ocr)

    def _worker_reprocesar(self, doc_id: str):
        try:
            from services.ocr import OcrService
            svc = OcrService(
                gestor=self._gestor, empresa_id=self._codigo,
                ejercicio=self._ejercicio, usuario=getattr(self._session, "usuario", ""),
            )
            self._ocr_q.put(("ok", svc.reprocesar_documento(
                doc_id,
                progress_callback=lambda documento: self._ocr_q.put(
                    ("progress", documento)
                ),
            )))
        except Exception as exc:
            self._ocr_q.put(("error", str(exc)))
        finally:
            self._ocr_q.put(("done", None))

    def _guardar(self, mostrar_confirmacion: bool = True) -> bool:
        if not self._factura_seleccionada and not self._doc_seleccionado:
            messagebox.showwarning("OCR", "No hay documento seleccionado.")
            return False
        tipo = str((self._doc_seleccionado or {}).get("tipo_documento") or "factura_recibida")
        es_emitida = tipo == "factura_emitida"
        factura_id = str((self._factura_seleccionada or {}).get("id") or uuid.uuid4())
        payload = dict(self._factura_seleccionada or {
            "id": factura_id,
            "documento_id": str(self._doc_seleccionado.get("id") or ""),
            "empresa_id": self._empresa_id,
            "proveedor_id": None,
            "tipo_operacion_iva": "INTERIOR_DEDUCIBLE",
            "estado_validacion": "pendiente",
            "observaciones": "Factura creada desde revision manual OCR.",
            "fecha_contable": "",
            "pagada": 0,
            "suplidos": 0.0,
            "cuenta_suplidos": "55509999",
        })
        payload["id"] = factura_id
        payload["documento_id"] = str(payload.get("documento_id") or self._doc_seleccionado.get("id") or "")
        payload["empresa_id"] = str(payload.get("empresa_id") or self._empresa_id)

        for campo, var in self._entries.items():
            valor = var.get().strip()
            if campo in ("total_factura", "base_total", "iva_total", "retencion_total", "suplidos"):
                try:
                    payload[campo] = _parse_importe(valor)
                except ValueError:
                    messagebox.showerror("OCR", f"Valor numerico invalido en '{campo}'.")
                    return False
            else:
                payload[campo] = valor

        try:
            lineas_iva = self._lineas_iva_editor()
        except ValueError as exc:
            messagebox.showerror("OCR", str(exc))
            return False
        try:
            retenciones = self._retenciones_editor()
        except ValueError as exc:
            messagebox.showerror("OCR", str(exc))
            return False

        payload["proveedor_id"] = self._proveedor_id_seleccionado or None
        payload["tipo_operacion_iva"] = self._tipo_operacion_iva_var.get().strip() or "INTERIOR_DEDUCIBLE"
        payload["pagada"] = 1 if self._pagada_var.get() else 0
        payload["cuenta_suplidos"] = self._cuenta_suplidos_seleccionada() or "55509999"
        if (
            self._proveedor_id_seleccionado
            and self._subcuenta_plan_seleccionada()
            and self._subcuenta_gasto_seleccionada()
        ):
            try:
                if es_emitida:
                    self._asegurar_cliente_en_empresa()
                else:
                    self._asegurar_proveedor_en_empresa()
            except Exception as exc:
                messagebox.showerror(
                    "OCR", f"No se pudieron guardar las cuentas del tercero: {exc}",
                )
                return False

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

        if es_emitida:
            payload.update({
                "cliente_id": self._proveedor_id_seleccionado or None,
                "nif_cliente": payload.get("nif_proveedor") or "",
                "nombre_cliente": payload.get("nombre_proveedor") or "",
                "cobrada": 1 if self._pagada_var.get() else 0,
                "tipo_operacion": "01",
                "subcuenta_cliente": self._subcuenta_plan_seleccionada(),
                "cuenta_ingreso": self._subcuenta_gasto_seleccionada(),
            })
            self._gestor.upsert_factura_emitida_ocr(payload)
            self._gestor.eliminar_lineas_iva_emitida_ocr(factura_id)
            for linea in lineas_iva:
                self._gestor.upsert_linea_iva_emitida_ocr({
                    "factura_id": factura_id,
                    "tipo_iva": linea.get("tipo_iva") or 0.0,
                    "base": linea.get("base") or 0.0,
                    "cuota_iva": linea.get("cuota_iva") or 0.0,
                    "tipo_recargo": linea.get("tipo_recargo") or 0.0,
                    "cuota_recargo": linea.get("cuota_recargo") or 0.0,
                    "cuenta_ingreso": linea.get("cuenta_gasto") or "",
                    "tipo_operacion": "01",
                })
            self._gestor.eliminar_retenciones_emitida_ocr(factura_id)
            for retencion in retenciones:
                self._gestor.upsert_retencion_emitida_ocr({
                    "factura_id": factura_id, **retencion,
                })
        else:
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
            self._gestor.eliminar_retenciones_ocr(factura_id)
            for retencion in retenciones:
                self._gestor.upsert_retencion_ocr({"factura_id": factura_id, **retencion})
        self._factura_seleccionada = payload
        # Recargar desde la base de datos para que el formulario derecho refleje tambien
        # las facturas creadas manualmente cuando no habia propuesta OCR.
        marcas_guardadas = dict(self._marcas_campos)
        # La recarga busca por documento_id, no por el id de la factura OCR.
        self._cargar_factura_en_editor(str(payload.get("documento_id") or self._doc_seleccionado.get("id") or ""))
        self._marcas_campos = marcas_guardadas
        self._dibujar_marcas()
        self._refresh_all()
        if mostrar_confirmacion:
            messagebox.showinfo("OCR", "Cambios guardados.")
        return True

    def _errores_validacion_revision(self) -> list[str]:
        """Comprueba que la factura esta completa y lista para contabilidad."""
        tipo = str(
            (self._doc_seleccionado or {}).get("tipo_documento")
            or "factura_recibida"
        )
        tercero = "cliente" if tipo == "factura_emitida" else "proveedor"
        errores = []
        nif = self._entries["nif_proveedor"].get().strip()
        if not nif:
            errores.append(f"NIF del {tercero}")
        if not self._entries["nombre_proveedor"].get().strip():
            errores.append(f"Nombre del {tercero}")
        if not self._proveedor_id_seleccionado:
            errores.append(f"{tercero.title()} vinculado al maestro")
        if not self._entries["numero_factura"].get().strip():
            errores.append("Numero de factura")

        for campo, etiqueta in (
            ("fecha_factura", "Fecha de factura"),
            ("fecha_contable", "Fecha contable"),
        ):
            valor = self._entries[campo].get().strip()
            fecha = None
            for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    fecha = datetime.strptime(valor, formato)
                    break
                except ValueError:
                    continue
            if fecha is None:
                errores.append(f"{etiqueta} valida")
            elif campo == "fecha_contable" and fecha.year != int(self._ejercicio):
                errores.append(f"Fecha contable dentro del ejercicio {self._ejercicio}")

        cuenta_tercero = self._subcuenta_plan_seleccionada()
        cuenta_resultado = self._subcuenta_gasto_seleccionada()
        if not cuenta_tercero:
            errores.append(f"Cuenta contable del {tercero}")
        if not cuenta_resultado:
            errores.append(
                "Cuenta de ingresos" if tipo == "factura_emitida" else "Cuenta de gastos"
            )

        try:
            lineas = self._lineas_iva_editor()
            retenciones = self._retenciones_editor()
            base_total = _parse_importe(self._entries["base_total"].get())
            iva_total = _parse_importe(self._entries["iva_total"].get())
            retencion_total = _parse_importe(self._entries["retencion_total"].get())
            suplidos = _parse_importe(self._entries["suplidos"].get())
            total = _parse_importe(self._entries["total_factura"].get())
        except ValueError as exc:
            errores.append(str(exc))
            return errores
        if not lineas:
            errores.append("Al menos una linea fiscal con base e IVA")
            return errores
        resumen = _resumen_fiscal(lineas, retenciones, suplidos)
        for informado, calculado, etiqueta in (
            (base_total, resumen["base"], "Base total"),
            (iva_total, resumen["iva"], "IVA total"),
            (retencion_total, resumen["retencion"], "Retencion total"),
            (total, resumen["total_esperado"], "Total factura"),
        ):
            if abs(informado - calculado) > 0.05:
                errores.append(
                    f"{etiqueta} no cuadra: informado {informado:.2f}, "
                    f"calculado {calculado:.2f}"
                )
        if abs(total) <= 0.0001:
            errores.append("Total de factura distinto de cero")
        if abs(suplidos) > 0.0001 and not self._cuenta_suplidos_seleccionada():
            errores.append("Cuenta contable de suplidos")
        return errores

    def _validar_seleccionado(self):
        if not self._factura_seleccionada and not self._doc_seleccionado:
            messagebox.showwarning("OCR", "Selecciona un documento.")
            return
        errores = self._errores_validacion_revision()
        if errores:
            messagebox.showwarning(
                "OCR",
                "No se puede validar. Corrige estos datos:\n- " + "\n- ".join(errores),
            )
            return
        if not self._guardar(mostrar_confirmacion=False):
            return
        factura = self._factura_seleccionada
        tipo = str((self._doc_seleccionado or {}).get("tipo_documento") or "factura_recibida")
        factura["estado_validacion"] = "validada"
        if tipo == "factura_emitida":
            self._gestor.upsert_factura_emitida_ocr(factura)
        else:
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
            if tipo == "factura_emitida":
                svc_contab = OcrEmitContabilidadService(
                    gestor=self._gestor,
                    codigo_empresa=self._codigo,
                    ejercicio=self._ejercicio,
                )
            else:
                svc_contab = OcrContabilidadService(
                    gestor=self._gestor,
                    codigo_empresa=self._codigo,
                    ejercicio=self._ejercicio,
                )
            svc_contab.proyectar_factura_validada(doc, factura)
        self._refresh_all()
        messagebox.showinfo(
            "OCR", "Documento validado y enviado a Contabilidad.\nGenera alli el suenlace.dat."
        )

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
