"""Previsualizacion de PDFs y seleccion de paginas para imprimir."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


class PrevisualizacionImpresionDialog(tk.Toplevel):
    def __init__(self, parent, documentos: list[dict]):
        super().__init__(parent)
        self.title("Previsualizar e imprimir facturas")
        self.geometry("1120x760")
        self.minsize(880, 620)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.result: dict[str, list[int]] | None = None
        self._documentos: dict[str, dict] = {}
        self._paginas: dict[str, tuple[str, int]] = {}
        self._marcadas: set[tuple[str, int]] = set()
        self._imagen = None
        self._build()
        self._cargar(documentos)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        ttk.Label(
            self,
            text="Selecciona las paginas que quieres imprimir",
            font=("Segoe UI", 14, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 4))

        left = ttk.Frame(self, padding=(14, 6, 8, 8))
        left.grid(row=1, column=0, sticky="nsew")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self._tree = ttk.Treeview(
            left, columns=("imprimir", "documento", "pagina"),
            show="headings", selectmode="browse", height=24,
        )
        for key, title, width in (
            ("imprimir", "Imprimir", 72),
            ("documento", "Documento", 250),
            ("pagina", "Pagina", 65),
        ):
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, anchor="center" if key != "documento" else "w")
        scroll = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self._tree.bind("<<TreeviewSelect>>", self._mostrar_seleccion)
        self._tree.bind("<ButtonRelease-1>", self._click_tabla)
        self._tree.bind("<space>", lambda _event: self._alternar_actual())

        tools = ttk.Frame(left)
        tools.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(tools, text="Marcar todas", command=self._marcar_todas).pack(side="left")
        ttk.Button(tools, text="Ninguna", command=self._desmarcar_todas).pack(side="left", padx=6)

        preview_frame = ttk.Frame(self, padding=(8, 6, 14, 8))
        preview_frame.grid(row=1, column=1, sticky="nsew")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        self._preview = ttk.Label(
            preview_frame, text="Selecciona una pagina", anchor="center",
            relief="sunken",
        )
        self._preview.grid(row=0, column=0, sticky="nsew")

        bottom = ttk.Frame(self, padding=(14, 4, 14, 12))
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew")
        self._summary = ttk.Label(bottom, text="")
        self._summary.pack(side="left")
        ttk.Button(bottom, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(
            bottom, text="Imprimir paginas seleccionadas", command=self._accept,
        ).pack(side="right", padx=(0, 8))

    def _cargar(self, documentos: list[dict]) -> None:
        try:
            import fitz
        except ImportError as exc:
            self.destroy()
            raise RuntimeError("PyMuPDF no esta disponible para previsualizar PDFs.") from exc

        errores = []
        indice = 0
        for raw in documentos:
            documento = dict(raw)
            documento_id = str(documento.get("id") or "")
            path = Path(str(documento.get("ruta") or ""))
            nombre = str(documento.get("nombre_original") or path.name or documento_id)
            if not documento_id or not path.is_file() or path.suffix.lower() != ".pdf":
                errores.append(f"{nombre}: no es un PDF disponible")
                continue
            try:
                with fitz.open(str(path)) as pdf:
                    total = len(pdf)
            except Exception as exc:
                errores.append(f"{nombre}: {exc}")
                continue
            if total < 1:
                errores.append(f"{nombre}: PDF sin paginas")
                continue
            self._documentos[documento_id] = documento
            for pagina in range(1, total + 1):
                indice += 1
                iid = f"pagina-{indice}"
                self._paginas[iid] = (documento_id, pagina)
                self._marcadas.add((documento_id, pagina))
                self._tree.insert(
                    "", "end", iid=iid, values=("[x]", nombre, pagina),
                )
        if errores:
            messagebox.showwarning(
                "Previsualizar facturas",
                "No se pudieron previsualizar algunos documentos:\n- "
                + "\n- ".join(errores[:8]),
                parent=self,
            )
        if not self._paginas:
            self.destroy()
            raise ValueError("No hay ningun PDF disponible para imprimir.")
        primero = next(iter(self._paginas))
        self._tree.selection_set(primero)
        self._tree.focus(primero)
        self._update_summary()
        self.after_idle(self._mostrar_seleccion)

    def _click_tabla(self, event) -> None:
        iid = self._tree.identify_row(event.y)
        columna = self._tree.identify_column(event.x)
        if iid and columna == "#1":
            self._tree.selection_set(iid)
            self._alternar(iid)

    def _alternar_actual(self) -> str:
        seleccion = self._tree.selection()
        if seleccion:
            self._alternar(seleccion[0])
        return "break"

    def _alternar(self, iid: str) -> None:
        clave = self._paginas.get(iid)
        if not clave:
            return
        if clave in self._marcadas:
            self._marcadas.remove(clave)
        else:
            self._marcadas.add(clave)
        valores = list(self._tree.item(iid, "values"))
        valores[0] = "[x]" if clave in self._marcadas else "[ ]"
        self._tree.item(iid, values=valores)
        self._update_summary()

    def _marcar_todas(self) -> None:
        self._marcadas = set(self._paginas.values())
        for iid in self._paginas:
            valores = list(self._tree.item(iid, "values"))
            valores[0] = "[x]"
            self._tree.item(iid, values=valores)
        self._update_summary()

    def _desmarcar_todas(self) -> None:
        self._marcadas.clear()
        for iid in self._paginas:
            valores = list(self._tree.item(iid, "values"))
            valores[0] = "[ ]"
            self._tree.item(iid, values=valores)
        self._update_summary()

    def _update_summary(self) -> None:
        self._summary.configure(
            text=f"Paginas seleccionadas: {len(self._marcadas)} de {len(self._paginas)}",
        )

    def _mostrar_seleccion(self, _event=None) -> None:
        seleccion = self._tree.selection()
        if not seleccion:
            return
        documento_id, pagina = self._paginas[seleccion[0]]
        path = Path(str(self._documentos[documento_id]["ruta"]))
        try:
            import fitz
            from PIL import Image, ImageTk

            with fitz.open(str(path)) as pdf:
                pix = pdf[pagina - 1].get_pixmap(
                    matrix=fitz.Matrix(1.15, 1.15), alpha=False,
                )
            imagen = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            imagen.thumbnail((650, 650), Image.Resampling.LANCZOS)
            self._imagen = ImageTk.PhotoImage(imagen)
            self._preview.configure(image=self._imagen, text="")
        except Exception as exc:
            self._imagen = None
            self._preview.configure(image="", text=f"No se pudo mostrar la pagina:\n{exc}")

    def _accept(self) -> None:
        if not self._marcadas:
            messagebox.showwarning(
                "Imprimir facturas", "Selecciona al menos una pagina.", parent=self,
            )
            return
        result: dict[str, list[int]] = {}
        for documento_id, pagina in sorted(self._marcadas):
            result.setdefault(documento_id, []).append(pagina)
        self.result = result
        self.destroy()


def seleccionar_paginas_impresion(parent, documentos: list[dict]):
    dialog = PrevisualizacionImpresionDialog(parent, documentos)
    parent.wait_window(dialog)
    return dialog.result
