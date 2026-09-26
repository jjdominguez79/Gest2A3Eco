"""Bandeja global del archivo definitivo de facturas recibidas."""
from __future__ import annotations

import os
import threading
import tkinter as tk
import unicodedata
from datetime import date
from tkinter import messagebox, ttk

from services.facturas_recibidas_pendientes_service import (
    FacturasRecibidasPendientesService,
)


class UIFacturasRecibidasPendientes(ttk.Frame):
    def __init__(self, parent, gestor, session):
        super().__init__(parent, padding=12)
        self._gestor = gestor
        self._session = session
        self._service = FacturasRecibidasPendientesService(gestor)
        self._rows: list[dict] = []
        self._visible: list[dict] = []
        self._by_id: dict[str, dict] = {}
        self._ocr_refresh_after = None
        self._empresa = tk.StringVar(value="Todas")
        self._ejercicio = tk.StringVar(value="Todos")
        self._estado = tk.StringVar(value="Pendientes")
        self._buscar = tk.StringVar()
        self._build()
        self.refresh()

    def _build(self):
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 10))
        titles = ttk.Frame(header)
        titles.pack(side="left", fill="x", expand=True)
        ttk.Label(
            titles, text="Control de facturas recibidas",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            titles,
            text=(
                "En Pendientes permanecen hasta confirmar el asiento generado por "
                "OCR/SUENLACE o registrar su contabilizacion manual en A3."
            ),
        ).pack(anchor="w", pady=(2, 0))
        ttk.Button(header, text="Actualizar", command=self.refresh).pack(side="right")

        filters = ttk.LabelFrame(self, text="Filtros", padding=(10, 8))
        filters.pack(fill="x", pady=(0, 10))
        for column in (1, 3, 5, 7):
            filters.columnconfigure(column, weight=1)
        ttk.Label(filters, text="Empresa").grid(row=0, column=0, sticky="w")
        self._empresa_combo = ttk.Combobox(
            filters, textvariable=self._empresa, state="readonly", width=30,
        )
        self._empresa_combo.grid(row=0, column=1, sticky="ew", padx=(5, 14))
        ttk.Label(filters, text="Ejercicio").grid(row=0, column=2, sticky="w")
        self._ejercicio_combo = ttk.Combobox(
            filters, textvariable=self._ejercicio, state="readonly", width=10,
        )
        self._ejercicio_combo.grid(row=0, column=3, sticky="ew", padx=(5, 14))
        ttk.Label(filters, text="Estado").grid(row=0, column=4, sticky="w")
        ttk.Combobox(
            filters, textvariable=self._estado, state="readonly", width=22,
            values=(
                "Pendientes", "Contabilizadas por OCR/SUENLACE",
                "Contabilizadas manualmente en A3 (papel)", "Todas",
            ),
        ).grid(row=0, column=5, sticky="ew", padx=(5, 14))
        ttk.Label(filters, text="Buscar").grid(row=0, column=6, sticky="w")
        ttk.Entry(filters, textvariable=self._buscar, width=28).grid(
            row=0, column=7, sticky="ew", padx=(5, 0),
        )
        for variable in (self._empresa, self._ejercicio, self._estado, self._buscar):
            variable.trace_add("write", lambda *_args: self.apply_filters())

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True)
        columns = (
            "recibida", "empresa", "ejercicio", "documento", "factura", "remitente",
            "origen", "ocr", "estado", "impresiones", "asiento",
        )
        self._tree = ttk.Treeview(
            wrap, columns=columns, show="headings", selectmode="extended",
        )
        for key, title, width, anchor in (
            ("recibida", "Recibida", 150, "w"),
            ("empresa", "Empresa", 200, "w"),
            ("ejercicio", "Ej.", 55, "center"),
            ("documento", "Documento", 300, "w"),
            ("factura", "Nº factura", 115, "w"),
            ("remitente", "Remitente", 190, "w"),
            ("origen", "Origen", 85, "center"),
            ("ocr", "Situacion OCR", 145, "center"),
            ("estado", "Contabilizacion", 245, "w"),
            ("impresiones", "Impresiones", 85, "center"),
            ("asiento", "Asiento", 85, "center"),
        ):
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, anchor=anchor)
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(wrap, orient="vertical", command=self._tree.yview)
        scrollbar.pack(side="right", fill="y")
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.bind("<Double-1>", lambda _event: self._open_selected())

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(9, 0))
        ttk.Button(actions, text="Abrir", command=self._open_selected).pack(side="left")
        ttk.Button(
            actions, text="Imprimir seleccionadas", command=self._print_selected,
        ).pack(side="left", padx=6)
        ttk.Button(
            actions, text="Analizar con OCR en segundo plano",
            command=self._ocr_selected,
        ).pack(side="left", padx=6)
        ttk.Button(
            actions, text="Capturar asiento de A3",
            command=self._capture_a3_entries,
        ).pack(side="left", padx=6)
        ttk.Button(
            actions, text="Registrar manual en A3 (papel)",
            command=self._mark_manual,
        ).pack(side="left", padx=6)
        ttk.Button(
            actions, text="Devolver a pendientes", command=self._restore_pending,
        ).pack(side="left", padx=6)
        self._summary = ttk.Label(actions)
        self._summary.pack(side="right")

    def refresh(self):
        try:
            self._rows = self._service.listar()
        except Exception as exc:
            messagebox.showerror("Facturas recibidas", str(exc), parent=self)
            return
        companies = sorted({
            f"{row.get('codigo_empresa')} - {row.get('empresa_nombre')}"
            for row in self._rows
        }, key=str.casefold)
        self._empresa_combo.configure(values=("Todas", *companies))
        if self._empresa.get() not in self._empresa_combo.cget("values"):
            self._empresa.set("Todas")
        years = sorted({int(row.get("ejercicio") or 0) for row in self._rows}, reverse=True)
        self._ejercicio_combo.configure(values=("Todos", *map(str, years)))
        if self._ejercicio.get() not in self._ejercicio_combo.cget("values"):
            self._ejercicio.set("Todos")
        self.apply_filters()
        self._programar_refresco_ocr()

    def _programar_refresco_ocr(self):
        if self._ocr_refresh_after is not None:
            try:
                self.after_cancel(self._ocr_refresh_after)
            except tk.TclError:
                pass
            self._ocr_refresh_after = None
        if any(
            str(row.get("estado_trabajo_ocr") or "") in {"pendiente", "procesando"}
            for row in self._rows
        ):
            self._ocr_refresh_after = self.after(3_000, self._refrescar_estado_ocr)

    def _refrescar_estado_ocr(self):
        self._ocr_refresh_after = None
        if self.winfo_exists():
            self.refresh()

    def apply_filters(self):
        self._visible = self.filter_rows(
            self._rows,
            empresa=self._empresa.get(),
            ejercicio=self._ejercicio.get(),
            estado=self._estado.get(),
            texto=self._buscar.get(),
        )
        self._tree.delete(*self._tree.get_children())
        self._by_id = {}
        for row in self._visible:
            documento_id = str(row["id"])
            self._by_id[documento_id] = row
            ocr = self._ocr_state_label(row)
            estado = self._accounting_state_label(
                row.get("estado_contable"),
                metodo=row.get("metodo_contabilizacion"),
                exportada_ocr=self._exportada_desde_ocr(row),
            )
            self._tree.insert("", "end", iid=documento_id, values=(
                row.get("created_at") or "",
                row.get("empresa_nombre") or row.get("codigo_empresa") or "",
                row.get("ejercicio") or "",
                row.get("nombre_original") or "",
                row.get("numero_factura_captura") or "",
                row.get("correo_remitente") or "",
                row.get("origen") or "",
                ocr,
                estado,
                int(row.get("veces_impresa") or 0),
                row.get("numero_asiento") or "",
            ))
        pending = sum(
            1 for row in self._rows
            if row.get("estado_contable") not in {
                "contabilizada", "contabilizada_manual",
            }
        )
        self._summary.configure(
            text=f"Mostradas: {len(self._visible)} · Pendientes totales: {pending}",
        )

    @classmethod
    def filter_rows(
        cls, rows, *, empresa="Todas", ejercicio="Todos",
        estado="Pendientes", texto="",
    ) -> list[dict]:
        code = empresa.split(" - ", 1)[0] if empresa != "Todas" else ""
        query = cls._normalize(texto)
        result = []
        for row in rows:
            if code and str(row.get("codigo_empresa") or "") != code:
                continue
            if ejercicio != "Todos" and str(row.get("ejercicio") or "") != str(ejercicio):
                continue
            manual = row.get("estado_contable") == "contabilizada_manual"
            captured = row.get("estado_contable") == "contabilizada"
            if estado == "Pendientes" and (manual or captured):
                continue
            if estado == "Contabilizadas por OCR/SUENLACE" and not captured:
                continue
            if estado == "Contabilizadas manualmente en A3 (papel)" and not manual:
                continue
            haystack = " ".join(str(row.get(key) or "") for key in (
                "codigo_empresa", "empresa_nombre", "nombre_original",
                "correo_remitente", "correo_asunto", "numero_asiento",
                "numero_factura_captura",
            ))
            if query and query not in cls._normalize(haystack):
                continue
            result.append(row)
        return result

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
        return "".join(char for char in normalized if not unicodedata.combining(char))

    def _selected_ids(self) -> list[str]:
        selected = list(self._tree.selection())
        if not selected:
            messagebox.showwarning(
                "Facturas recibidas", "Selecciona al menos una factura.", parent=self,
            )
        return selected

    def _open_selected(self):
        selected = self._selected_ids()
        if not selected:
            return
        path = str(self._by_id[selected[0]].get("ruta") or "")
        try:
            os.startfile(path)
        except Exception as exc:
            messagebox.showerror("Facturas recibidas", str(exc), parent=self)

    def _print_selected(self):
        selected = self._selected_ids()
        if not selected:
            return
        self._run_background(
            "Imprimiendo...",
            lambda: self._service.imprimir(selected, usuario=self._username()),
            "Impresion solicitada",
        )

    def _ocr_selected(self):
        selected = self._selected_ids()
        if not selected:
            return
        self._run_background(
            "Encolando para OCR...",
            lambda: self._service.enviar_a_ocr(selected, usuario=self._username()),
            "OCR en segundo plano",
        )

    def _capture_a3_entries(self):
        selected = self._selected_ids()
        if not selected:
            return
        self._run_background(
            "Buscando asientos en A3ECO...",
            lambda: self._service.capturar_asientos(selected),
            "Captura de asientos",
        )

    def _mark_manual(self):
        selected = self._selected_ids()
        if not selected:
            return
        dialog = ContabilizacionManualDialog(self, len(selected))
        self.wait_window(dialog)
        if not dialog.result:
            return
        try:
            changed = self._service.marcar_contabilizadas(
                selected, usuario=self._username(), **dialog.result,
            )
        except Exception as exc:
            messagebox.showerror("Facturas recibidas", str(exc), parent=self)
            return
        self.refresh()
        messagebox.showinfo(
            "Facturas recibidas", f"Facturas marcadas: {changed}", parent=self,
        )

    def _restore_pending(self):
        selected = self._selected_ids()
        if not selected:
            return
        if not messagebox.askyesno(
            "Facturas recibidas",
            "Se eliminaran los datos de contabilizacion manual de la seleccion. ¿Continuar?",
            parent=self,
        ):
            return
        try:
            changed = self._service.devolver_a_pendientes(selected)
        except Exception as exc:
            messagebox.showerror("Facturas recibidas", str(exc), parent=self)
            return
        self.refresh()
        messagebox.showinfo(
            "Facturas recibidas", f"Facturas devueltas: {changed}", parent=self,
        )

    def _run_background(self, progress_text, operation, title):
        root = self.winfo_toplevel()
        root.configure(cursor="watch")
        self._summary.configure(text=progress_text)

        def worker():
            try:
                result = operation()
                try:
                    root.after(
                        0, self._finish_background, title, result, None,
                    )
                except (RuntimeError, tk.TclError):
                    pass
            except Exception as exc:
                try:
                    root.after(
                        0, self._finish_background, title, None, exc,
                    )
                except (RuntimeError, tk.TclError):
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def _finish_background(self, title, result, error):
        if not self.winfo_exists():
            return
        self.winfo_toplevel().configure(cursor="")
        self.refresh()
        if error:
            messagebox.showerror(title, str(error), parent=self)
            return
        etiqueta = "Encoladas" if title == "OCR en segundo plano" else "Completadas"
        lines = [f"{etiqueta}: {len(result.completados)}"]
        if title == "Captura de asientos" and result.completados:
            lines.append("\n".join(result.completados[:8]))
        if result.omitidos:
            lines.append(
                f"Omitidas: {len(result.omitidos)}\n- "
                + "\n- ".join(result.omitidos[:8])
            )
        if result.errores:
            lines.append("Errores:\n- " + "\n- ".join(result.errores[:8]))
        messagebox.showinfo(title, "\n".join(lines), parent=self)

    def _username(self) -> str:
        return str(getattr(getattr(self._session, "user", None), "nombre", ""))

    @staticmethod
    def _exportada_desde_ocr(row: dict) -> bool:
        return str(row.get("estado_documento_ocr") or "").lower() == "contabilizada" or str(
            row.get("estado_contable_ocr") or ""
        ).lower() == "contabilizada"

    @classmethod
    def _ocr_state_label(cls, row: dict) -> str:
        estado_trabajo = str(row.get("estado_trabajo_ocr") or "").strip().lower()
        if estado_trabajo == "pendiente":
            return "En cola"
        if estado_trabajo == "procesando":
            return "Procesando"
        if estado_trabajo == "error" and not row.get("ocr_documento_id"):
            return "Error de proceso"
        if not row.get("ocr_documento_id"):
            return "Sin analizar"
        estado = str(row.get("estado_documento_ocr") or "").strip().lower()
        contable = str(row.get("estado_contable_ocr") or "").strip().lower()
        if cls._exportada_desde_ocr(row):
            return "Exportada para A3"
        if estado == "error":
            return "Error"
        if estado in {"pendiente", "procesando"}:
            return "En proceso"
        if estado == "pendiente_revision":
            return "Pendiente revision"
        if estado == "pendiente_contabilizar" or contable == "pendiente_contabilizar":
            return "Lista para contabilizar"
        return "Analizada"

    @staticmethod
    def _accounting_state_label(
        value, *, metodo: str = "", exportada_ocr: bool = False,
    ) -> str:
        metodo = str(metodo or "").strip().lower()
        if value == "contabilizada":
            if metodo == "ocr_suenlace":
                return "OCR/SUENLACE · asiento confirmado en A3"
            return "Asiento confirmado en A3"
        if value == "contabilizada_manual":
            return "Manual en A3 (papel)"
        if exportada_ocr:
            return "OCR/SUENLACE · pendiente de asiento A3"
        return "Pendiente de contabilizar"


class ContabilizacionManualDialog(tk.Toplevel):
    def __init__(self, parent, cantidad: int):
        super().__init__(parent)
        self.title("Contabilizacion manual en A3 (papel)")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.resizable(False, False)
        self.result = None
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame, text=f"Registrar {cantidad} factura(s) manualmente en A3",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self._fecha = tk.StringVar(value=date.today().isoformat())
        self._asiento = tk.StringVar()
        self._observaciones = tk.StringVar()
        for row, (label, variable) in enumerate((
            ("Fecha contable", self._fecha),
            ("Numero de asiento (opcional)", self._asiento),
            ("Observaciones (opcional)", self._observaciones),
        ), start=1):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(frame, textvariable=variable, width=42).grid(
                row=row, column=1, sticky="ew", padx=(8, 0), pady=4,
            )
        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Cancelar", command=self.destroy).pack(side="left")
        ttk.Button(actions, text="Confirmar", command=self._accept).pack(
            side="left", padx=(6, 0),
        )

    def _accept(self):
        raw_date = self._fecha.get().strip()
        try:
            if raw_date:
                date.fromisoformat(raw_date)
        except ValueError:
            messagebox.showwarning(
                "Contabilizacion manual", "La fecha debe tener formato AAAA-MM-DD.",
                parent=self,
            )
            return
        self.result = {
            "fecha_contable": raw_date,
            "numero_asiento": self._asiento.get().strip(),
            "observaciones": self._observaciones.get().strip(),
        }
        self.destroy()
