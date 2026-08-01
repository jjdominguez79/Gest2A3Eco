"""
Vista unificada del modulo OCR de facturas recibidas.

Arquitectura: panel dividido horizontalmente
  Izquierda — listado de documentos por bandeja (Notebook con pestanas)
  Derecha   — panel de edicion de cabecera, IVA y retencion del doc seleccionado

Puntos de integracion:
  - services/ocr/OcrService       — procesamiento OCR tipado
  - services/ocr_recibidas_service — generacion suenlace.dat (flujo existente)
  - models/gestor_sqlite           — persistencia
  - controllers/ui_ocr_facturas_controller — logica existente de bandejas

Esta pantalla complementa (no reemplaza) ui_ocr_facturas.py + ui_ocr_detalle.py.
"""
from __future__ import annotations

import logging
import queue
import os
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from utils.utilidades import load_app_config, save_app_config

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
            btn_frame, text="Configurar OCR",
            command=self._configurar_ocr,
        ).pack(side="left", padx=4)

        # Panel horizontal: lista + detalle
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=4)

        # Panel izquierdo: bandejas
        left = ttk.Frame(paned)
        paned.add(left, weight=40)
        self._build_bandejas(left)

        # Panel derecho: vista previa y campos visibles simultaneamente.
        right = ttk.Frame(paned)
        paned.add(right, weight=60)
        detalle = ttk.PanedWindow(right, orient="horizontal")
        detalle.pack(fill="both", expand=True)
        preview = ttk.Frame(detalle)
        editor = ttk.Frame(detalle)
        detalle.add(preview, weight=48)
        detalle.add(editor, weight=52)
        self._build_preview(preview)
        self._build_editor(editor)

        # Barra de estado
        self._lbl_status = ttk.Label(self, text="", foreground="#555")
        self._lbl_status.pack(fill="x", padx=10, pady=(0, 6))

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
        ttk.Label(frame, text="Motor OCR").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(frame, textvariable=motor, state="readonly", values=("", "azure"), width=42).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=3)
        ttk.Label(frame, text="Endpoint Azure").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=endpoint, width=55).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)
        ttk.Label(frame, text="Clave Azure").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=key, show="*", width=55).grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=3)
        ttk.Label(
            frame,
            text=("Azure Document Intelligence usa el modelo prebuilt-invoice. "
                  "Los documentos se enviaran al servicio de Azure para su analisis."),
            wraplength=520, foreground="#555",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

        def save():
            selected = motor.get().strip().lower()
            if selected == "azure" and (not endpoint.get().strip() or not key.get().strip()):
                messagebox.showwarning("OCR", "Indica endpoint y clave de Azure.", parent=dialog)
                return
            cfg["ocr_motor_activo"] = selected
            cfg["azure_doc_intelligence_endpoint"] = endpoint.get().strip()
            cfg["azure_doc_intelligence_key"] = key.get().strip()
            save_app_config(cfg)
            dialog.destroy()
            self._lbl_status.configure(text="Configuracion OCR guardada. Los documentos nuevos usaran el motor seleccionado.")

        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
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
            tv = ttk.Treeview(frame, columns=COL_IDS, show="headings", selectmode="browse")
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
            tv.bind("<Double-1>",         lambda _e, est=estado: self._abrir_detalle(est))

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
        ttk.Button(barra, text="Abrir documento", command=self._abrir_documento).pack(side="right")
        marco = ttk.Frame(parent)
        marco.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._lbl_preview_imagen = ttk.Label(marco, anchor="center")
        self._lbl_preview_imagen.pack(fill="both", expand=True)
        self._preview_photo = None
        self._preview_path = ""

    def _mostrar_preview(self, doc: dict):
        ruta = Path(str(doc.get("ruta_original") or ""))
        self._preview_path = str(ruta)
        self._preview_photo = None
        self._lbl_preview_imagen.configure(image="", text="")
        if not ruta.exists():
            self._lbl_preview.configure(text=f"No se encuentra el documento original: {ruta}")
            return
        try:
            imagen = self._cargar_primera_pagina(ruta)
            from PIL import ImageTk
            self._preview_photo = ImageTk.PhotoImage(imagen)
            self._lbl_preview_imagen.configure(image=self._preview_photo)
            self._lbl_preview.configure(text=f"{ruta.name} - primera pagina")
        except Exception as exc:
            self._lbl_preview.configure(text=f"No se pudo generar la vista previa: {exc}")
            self._lbl_preview_imagen.configure(text="Usa 'Abrir documento' para verlo en el visor PDF.")

    def _cargar_primera_pagina(self, ruta: Path):
        from PIL import Image
        if ruta.suffix.lower() != ".pdf":
            imagen = Image.open(ruta)
            imagen.thumbnail((760, 900))
            return imagen.copy()
        try:
            import fitz
            pdf = fitz.open(str(ruta))
            pagina = pdf.load_page(0)
            pix = pagina.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            imagen = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            pdf.close()
        except ImportError:
            ejecutable = shutil.which("pdftoppm")
            if not ejecutable:
                raise RuntimeError("Falta PyMuPDF o pdftoppm para visualizar PDFs.")
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
        imagen.thumbnail((760, 900))
        return imagen

    def _abrir_documento(self):
        if not self._preview_path or not Path(self._preview_path).exists():
            messagebox.showwarning("OCR", "No hay documento original disponible.")
            return
        try:
            os.startfile(self._preview_path)
        except Exception as exc:
            messagebox.showerror("OCR", f"No se pudo abrir el documento:\n{exc}")

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
        self._cargar_factura_en_editor(doc_id)
        self._mostrar_preview(doc)

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
        if not self._factura_seleccionada:
            messagebox.showwarning("OCR", "No hay documento seleccionado.")
            return
        factura_id = self._factura_seleccionada["id"]
        payload = dict(self._factura_seleccionada)

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
                orig = str(self._factura_seleccionada.get(campo) or "")
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
                "tipo_operacion_iva": "INTERIOR_DEDUCIBLE",
            })
        self._factura_seleccionada = payload
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
                })
        except Exception as exc:
            logger.warning("[OCR] No se pudieron obtener las lineas IVA: %s", exc)
        ruta = str(documento.get("ruta_original") or "")
        payload = {
            "id": doc_id, "codigo_empresa": self._codigo, "ejercicio": self._ejercicio,
            "origen_path": ruta, "pdf_path": ruta if Path(ruta).suffix.lower() == ".pdf" else "",
            "estado_ocr": "procesado", "estado_validacion": "validada",
            "estado_contable": "pendiente_contabilizar", "tipo_documento": "factura_recibida",
            "proveedor_nif": factura.get("nif_proveedor") or "",
            "proveedor_nombre": factura.get("nombre_proveedor") or "",
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
            "datos_extra": {"documento_ocr_id": doc_id},
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
        # Eliminar factura asociada
        try:
            self._gestor.conn.execute(
                "DELETE FROM facturas_recibidas_ocr WHERE documento_id=?", (doc_id,)
            )
            self._gestor.conn.execute(
                "DELETE FROM documentos_ocr WHERE id=?", (doc_id,)
            )
            self._gestor.conn.commit()
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
