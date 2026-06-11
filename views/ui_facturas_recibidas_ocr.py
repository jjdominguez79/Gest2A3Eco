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
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

logger = logging.getLogger(__name__)

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

        # Panel horizontal: lista + detalle
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=4)

        # Panel izquierdo: bandejas
        left = ttk.Frame(paned)
        paned.add(left, weight=40)
        self._build_bandejas(left)

        # Panel derecho: editor
        right = ttk.Frame(paned)
        paned.add(right, weight=60)
        self._build_editor(right)

        # Barra de estado
        self._lbl_status = ttk.Label(self, text="", foreground="#555")
        self._lbl_status.pack(fill="x", padx=10, pady=(0, 6))

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
            ttk.Button(bar, text="Generar suenlace", style="Primary.TButton",
                       command=self._generar_suenlace).pack(side="left", padx=2)
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
        ttk.Button(btn_frame, text="Generar suenlace",
                   command=self._generar_suenlace).pack(side="left", padx=4)

        # Errores OCR
        self._lbl_errores = ttk.Label(parent, text="", foreground="#c0392b",
                                       wraplength=400, justify="left")
        self._lbl_errores.pack(anchor="w", padx=8, pady=2)

    # ── Refresco de bandejas ──────────────────────────────────────────────────

    def _refresh_all(self):
        for estado, _ in BANDEJAS:
            self._refresh_bandeja(estado)

    def _refresh_bandeja(self, estado: str):
        # Cargar documentos OCR por estado (via tabla documentos_ocr)
        try:
            docs = self._gestor.listar_documentos_ocr(self._empresa, estado)
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
            confianza = doc.get("confianza_global") or 0.0
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
        ruta = doc.get("ruta_original") or ""
        if not ruta or not Path(ruta).exists():
            messagebox.showerror("OCR", f"Fichero original no encontrado:\n{ruta}")
            return
        self._lbl_status.configure(text="Reprocesando...")
        t = threading.Thread(target=self._worker_ocr, args=([ruta],), daemon=True)
        self._ocr_thread = t
        t.start()
        self.after(300, self._poll_ocr)

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
                    payload[campo] = float(valor) if valor else 0.0
                except ValueError:
                    messagebox.showerror("OCR", f"Valor numerico invalido en '{campo}'.")
                    return
            else:
                payload[campo] = valor

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
        self._refresh_all()
        messagebox.showinfo("OCR", "Documento validado.")

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

    def _generar_suenlace(self):
        """Genera suenlace.dat para documentos validados usando el flujo existente."""
        doc_id = self._get_selected_id()
        if not doc_id:
            messagebox.showwarning("OCR", "Selecciona un documento validado.")
            return
        # Buscar doc equivalente en facturas_recibidas_docs (flujo existente)
        try:
            doc = self._gestor.get_factura_recibida_doc(doc_id)
            if not doc:
                messagebox.showwarning(
                    "OCR",
                    "Este documento aun no tiene un registro en el flujo de suenlace.\n"
                    "Usa la pantalla 'Captura documental' principal para generar suenlace.",
                )
                return
            errors = []
            if not str(doc.get("proveedor_nif") or "").strip():
                errors.append("NIF del proveedor")
            if not str(doc.get("numero_factura") or "").strip():
                errors.append("Numero de factura")
            if not float(doc.get("total") or 0.0):
                errors.append("Total (es 0)")
            if errors:
                messagebox.showwarning(
                    "OCR",
                    "Faltan datos para generar suenlace:\n- " + "\n- ".join(errors),
                )
                return
            from services.ocr_recibidas_service import generate_suenlace_for_docs, mark_docs_as_generated
            regs = generate_suenlace_for_docs(self._gestor, self._codigo, self._ejercicio, [doc])
            if not regs:
                messagebox.showwarning("OCR", "No se generaron registros.")
                return
            save_path = filedialog.asksaveasfilename(
                title="Guardar fichero suenlace.dat",
                defaultextension=".dat",
                initialfile=f"{self._codigo}.dat",
                filetypes=[("Ficheros DAT", "*.dat")],
            )
            if not save_path:
                return
            with open(save_path, "w", encoding="latin-1", newline="") as f:
                f.writelines(regs)
            mark_docs_as_generated(self._gestor, [doc], estado_contable="contabilizada")
            self._refresh_all()
            messagebox.showinfo("OCR", f"Fichero generado:\n{save_path}")
        except Exception as exc:
            messagebox.showerror("OCR", f"Error al generar suenlace:\n{exc}")

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
