from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from services.import_a3_empresa import importar_empresa_desde_a3
from utils.validaciones import validar_nif_cif_nie
from views.ui_facturas_emitidas import TerceroFicha


def _to_float_es(x) -> float:
    try:
        if x is None or x == "":
            return 0.0
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            return float(x)
        s = str(x).strip().replace("\xa0", " ")
        s = "".join(ch for ch in s if ch.isdigit() or ch in ".,-")
        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        return 0.0


class EmpresaDialog(tk.Toplevel):
    def __init__(self, parent, titulo, empresa=None, gestor=None):
        super().__init__(parent)
        self.title(titulo)
        self.geometry("1020x760")
        self.minsize(920, 660)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self._gestor = gestor
        self._empresa = dict(empresa or {})
        self._is_edit = bool(self._empresa.get("codigo"))
        self._bank_items = []
        self._exercise_rows = []
        self._build()
        self.wait_visibility()
        self.focus_set()
        self.wait_window(self)

    def _build(self):
        self.var_codigo = tk.StringVar(value=str(self._empresa.get("codigo", "")))
        self.var_nombre = tk.StringVar(value=str(self._empresa.get("nombre", "")))
        self.var_dig = tk.StringVar(value=str(self._empresa.get("digitos_plan", 8) or "8"))
        self.var_cif = tk.StringVar(value=str(self._empresa.get("cif", "")))
        self.var_dir = tk.StringVar(value=str(self._empresa.get("direccion", "")))
        self.var_cp = tk.StringVar(value=str(self._empresa.get("cp", "")))
        self.var_pob = tk.StringVar(value=str(self._empresa.get("poblacion", "")))
        self.var_prov = tk.StringVar(value=str(self._empresa.get("provincia", "")))
        self.var_tel = tk.StringVar(value=str(self._empresa.get("telefono", "")))
        self.var_mail = tk.StringVar(value=str(self._empresa.get("email", "")))
        self.var_logo = tk.StringVar(value=str(self._empresa.get("logo_path", "")))
        self.var_logo_w = tk.StringVar(value=str(self._empresa.get("logo_max_width_mm") or ""))
        self.var_logo_h = tk.StringVar(value=str(self._empresa.get("logo_max_height_mm") or ""))
        self.var_activo = tk.BooleanVar(value=bool(self._empresa.get("activo", True)))
        self.var_a3_info = tk.StringVar(value="Sin importacion realizada.")

        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        nb = ttk.Notebook(root)
        nb.grid(row=0, column=0, sticky="nsew")

        self._build_general_tab(ttk.Frame(nb, padding=14), nb)
        self._build_exercises_tab(ttk.Frame(nb, padding=14), nb)
        self._build_banks_tab(ttk.Frame(nb, padding=14), nb)
        self._build_third_parties_tab(ttk.Frame(nb, padding=14), nb)
        self._build_import_tab(ttk.Frame(nb, padding=14), nb)

        actions = ttk.Frame(root)
        actions.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        if self._is_edit:
            ttk.Button(actions, text="Eliminar empresa", style="Danger.TButton", command=self._request_delete).pack(side=tk.LEFT)
        ttk.Button(actions, text="Cancelar", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(actions, text="Guardar", style="Primary.TButton", command=self.apply).pack(side=tk.RIGHT, padx=(0, 8))

    def _build_general_tab(self, tab, nb):
        nb.add(tab, text="General")
        tab.columnconfigure(1, weight=1)
        tab.columnconfigure(3, weight=1)
        fields = [
            ("Codigo", self.var_codigo, 0, 0, 14),
            ("Nombre", self.var_nombre, 1, 0, None),
            ("Digitos plan", self.var_dig, 2, 0, 10),
            ("CIF/NIF", self.var_cif, 3, 0, 20),
            ("Telefono", self.var_tel, 3, 2, 20),
            ("Email", self.var_mail, 4, 0, None),
            ("Direccion", self.var_dir, 5, 0, None),
            ("CP", self.var_cp, 6, 0, 10),
            ("Poblacion", self.var_pob, 6, 2, None),
            ("Provincia", self.var_prov, 7, 0, None),
        ]
        for text, var, row, col, width in fields:
            ttk.Label(tab, text=text).grid(row=row, column=col, sticky="w", pady=4, padx=(18 if col else 0, 0))
            kwargs = {"textvariable": var}
            if width:
                kwargs["width"] = width
            entry = ttk.Entry(tab, **kwargs)
            span = 1 if width else 3 if row in (1, 4, 5, 7) else 1
            entry.grid(row=row, column=col + 1, columnspan=span, sticky="ew" if not width else "w", pady=4)
        ttk.Checkbutton(tab, text="Activo", variable=self.var_activo).grid(row=2, column=3, sticky="w", pady=4)
        ttk.Label(tab, text="Logo (JPG)").grid(row=8, column=0, sticky="w", pady=4)
        row_logo = ttk.Frame(tab)
        row_logo.grid(row=8, column=1, columnspan=3, sticky="ew", pady=4)
        row_logo.columnconfigure(0, weight=1)
        ttk.Entry(row_logo, textvariable=self.var_logo).pack(side=tk.LEFT, fill="x", expand=True)
        ttk.Button(row_logo, text="Buscar", command=self._choose_logo).pack(side=tk.LEFT, padx=4)
        ttk.Label(tab, text="Logo ancho (mm)").grid(row=9, column=0, sticky="w", pady=4)
        ttk.Entry(tab, textvariable=self.var_logo_w, width=10).grid(row=9, column=1, sticky="w", pady=4)
        ttk.Label(tab, text="Logo alto (mm)").grid(row=9, column=2, sticky="w", pady=4, padx=(18, 0))
        ttk.Entry(tab, textvariable=self.var_logo_h, width=10).grid(row=9, column=3, sticky="w", pady=4)

    def _build_exercises_tab(self, tab, nb):
        nb.add(tab, text="Ejercicios")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        ttk.Label(tab, text="Cada ejercicio mantiene sus propias series y contadores.").grid(row=0, column=0, sticky="w", pady=(0, 8))
        frame = ttk.Frame(tab)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.tv_ejercicios = ttk.Treeview(
            frame,
            columns=("ejercicio", "serie", "siguiente", "serie_rect", "siguiente_rect"),
            show="headings",
            height=10,
        )
        headings = (
            ("ejercicio", "Ejercicio", 100),
            ("serie", "Serie emitidas", 120),
            ("siguiente", "Sig. emitidas", 110),
            ("serie_rect", "Serie rect.", 120),
            ("siguiente_rect", "Sig. rect.", 110),
        )
        for col, text, width in headings:
            self.tv_ejercicios.heading(col, text=text)
            self.tv_ejercicios.column(col, width=width, anchor="w")
        self.tv_ejercicios.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tv_ejercicios.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tv_ejercicios.configure(yscrollcommand=scroll.set)
        btns = ttk.Frame(tab)
        btns.grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Anadir ejercicio", style="Primary.TButton", command=self._add_exercise).pack(side=tk.LEFT)
        ttk.Button(btns, text="Editar", command=self._edit_exercise).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Eliminar", command=self._remove_exercise).pack(side=tk.LEFT)
        self.lbl_ejercicios = ttk.Label(tab, text="")
        self.lbl_ejercicios.grid(row=3, column=0, sticky="w", pady=(10, 0))
        self._load_exercises()

    def _build_banks_tab(self, tab, nb):
        nb.add(tab, text="Bancos")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        ttk.Label(tab, text="Cuentas bancarias de la empresa").grid(row=0, column=0, sticky="w", pady=(0, 8))
        frame = ttk.Frame(tab)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.tv_bancos_empresa = ttk.Treeview(frame, columns=("cuenta",), show="headings", height=10)
        self.tv_bancos_empresa.heading("cuenta", text="Cuenta bancaria / IBAN")
        self.tv_bancos_empresa.column("cuenta", anchor="w", width=420)
        self.tv_bancos_empresa.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tv_bancos_empresa.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tv_bancos_empresa.configure(yscrollcommand=scroll.set)
        btns = ttk.Frame(tab)
        btns.grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Anadir", style="Primary.TButton", command=self._add_bank).pack(side=tk.LEFT)
        ttk.Button(btns, text="Editar", command=self._edit_bank).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Eliminar", command=self._remove_bank).pack(side=tk.LEFT)
        self._load_banks_from_text(str(self._empresa.get("cuentas_bancarias") or self._empresa.get("cuenta_bancaria") or ""))

    def _build_third_parties_tab(self, tab, nb):
        nb.add(tab, text="Terceros")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        ttk.Label(tab, text="Terceros asignados a esta empresa").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.tv_terceros_empresa = ttk.Treeview(
            tab,
            columns=("nif", "nombre", "cliente", "proveedor", "ingreso", "gasto"),
            show="headings",
        )
        for col, text, width in (
            ("nif", "NIF", 120),
            ("nombre", "Nombre", 320),
            ("cliente", "Subcuenta cliente", 140),
            ("proveedor", "Subcuenta proveedor", 140),
            ("ingreso", "Subcuenta ingreso", 140),
            ("gasto", "Subcuenta gasto", 140),
        ):
            self.tv_terceros_empresa.heading(col, text=text)
            self.tv_terceros_empresa.column(col, width=width, anchor="w")
        self.tv_terceros_empresa.grid(row=1, column=0, sticky="nsew")
        self.tv_terceros_empresa.bind("<Double-1>", lambda _e: self._edit_third_party_accounts())
        btns = ttk.Frame(tab)
        btns.grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Nuevo tercero", style="Primary.TButton", command=self._new_third_party).pack(side=tk.LEFT)
        ttk.Button(btns, text="Asignar existente", command=self._assign_existing_third_party).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Editar", command=self._edit_third_party).pack(side=tk.LEFT)
        ttk.Button(btns, text="Subcuentas", command=self._edit_third_party_accounts).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Quitar asignacion", command=self._remove_third_party_assignment).pack(side=tk.LEFT, padx=6)
        self.lbl_terceros_info = ttk.Label(tab, text="")
        self.lbl_terceros_info.grid(row=3, column=0, sticky="w", pady=(8, 0))
        self._load_terceros()

    def _build_import_tab(self, tab, nb):
        nb.add(tab, text="Importar A3")
        tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="Importar datos base desde A3 usando solo el codigo de empresa.").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10)
        )
        ttk.Label(tab, text="Codigo A3 (E00000)").grid(row=1, column=0, sticky="w")
        ttk.Entry(tab, textvariable=self.var_codigo, width=14).grid(row=1, column=1, sticky="w")
        ttk.Button(tab, text="Importar desde A3", style="Primary.TButton", command=self._import_from_a3).grid(row=1, column=2, sticky="w", padx=(10, 0))
        ttk.Label(tab, textvariable=self.var_a3_info, justify="left").grid(row=2, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Label(tab, text="Detalle capturado desde A3ECO").grid(row=3, column=0, columnspan=3, sticky="w", pady=(14, 6))
        frame = ttk.Frame(tab)
        frame.grid(row=4, column=0, columnspan=3, sticky="nsew")
        tab.rowconfigure(4, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.txt_a3_preview = tk.Text(frame, height=14, wrap="word", state="disabled")
        self.txt_a3_preview.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.txt_a3_preview.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.txt_a3_preview.configure(yscrollcommand=scroll.set)

    def _exercise_from_row(self, row: dict | None) -> dict:
        data = dict(row or {})
        return {
            "ejercicio": int(data.get("ejercicio") or 2025),
            "serie_emitidas": str(data.get("serie_emitidas") or "A"),
            "siguiente_num_emitidas": int(data.get("siguiente_num_emitidas") or 1),
            "serie_emitidas_rect": str(data.get("serie_emitidas_rect") or "R"),
            "siguiente_num_emitidas_rect": int(data.get("siguiente_num_emitidas_rect") or 1),
        }

    def _load_exercises(self):
        self._exercise_rows = []
        codigo = str(self._empresa.get("codigo") or "")
        if self._gestor and codigo:
            try:
                rows = [dict(x) for x in self._gestor.listar_empresas() if str(x.get("codigo") or "") == codigo]
            except Exception:
                rows = []
            for row in sorted(rows, key=lambda item: int(item.get("ejercicio") or 0)):
                self._exercise_rows.append(self._exercise_from_row(row))
        if not self._exercise_rows:
            self._exercise_rows.append(self._exercise_from_row(self._empresa))
        self._refresh_exercises_tree()

    def _refresh_exercises_tree(self):
        self.tv_ejercicios.delete(*self.tv_ejercicios.get_children())
        for row in self._exercise_rows:
            ejercicio = int(row["ejercicio"])
            self.tv_ejercicios.insert("", "end", iid=str(ejercicio), values=(
                ejercicio,
                row["serie_emitidas"],
                row["siguiente_num_emitidas"],
                row["serie_emitidas_rect"],
                row["siguiente_num_emitidas_rect"],
            ))
        self.lbl_ejercicios.configure(text=f"Ejercicios configurados: {len(self._exercise_rows)}")

    def _exercise_editor(self, initial=None):
        data = self._exercise_from_row(initial)
        top = tk.Toplevel(self)
        top.title("Ejercicio")
        top.resizable(False, False)
        top.transient(self)
        top.grab_set()
        vars_map = {
            "ejercicio": tk.StringVar(value=str(data["ejercicio"])),
            "serie_emitidas": tk.StringVar(value=data["serie_emitidas"]),
            "siguiente_num_emitidas": tk.StringVar(value=str(data["siguiente_num_emitidas"])),
            "serie_emitidas_rect": tk.StringVar(value=data["serie_emitidas_rect"]),
            "siguiente_num_emitidas_rect": tk.StringVar(value=str(data["siguiente_num_emitidas_rect"])),
        }
        frm = ttk.Frame(top, padding=12)
        frm.pack(fill="both", expand=True)
        labels = (
            ("ejercicio", "Ejercicio"),
            ("serie_emitidas", "Serie emitidas"),
            ("siguiente_num_emitidas", "Sig. emitidas"),
            ("serie_emitidas_rect", "Serie rectificativas"),
            ("siguiente_num_emitidas_rect", "Sig. rectificativas"),
        )
        for idx, (key, text) in enumerate(labels):
            ttk.Label(frm, text=text).grid(row=idx, column=0, sticky="w", pady=4)
            ttk.Entry(frm, textvariable=vars_map[key], width=18).grid(row=idx, column=1, sticky="w", pady=4)
        result = {"value": None}

        def _ok():
            try:
                result["value"] = {
                    "ejercicio": int(vars_map["ejercicio"].get().strip()),
                    "serie_emitidas": vars_map["serie_emitidas"].get().strip() or "A",
                    "siguiente_num_emitidas": int(vars_map["siguiente_num_emitidas"].get().strip() or "1"),
                    "serie_emitidas_rect": vars_map["serie_emitidas_rect"].get().strip() or "R",
                    "siguiente_num_emitidas_rect": int(vars_map["siguiente_num_emitidas_rect"].get().strip() or "1"),
                }
            except Exception as exc:
                messagebox.showerror("Gest2A3Eco", str(exc), parent=top)
                return
            top.destroy()

        btns = ttk.Frame(frm)
        btns.grid(row=len(labels), column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(btns, text="Guardar", style="Primary.TButton", command=_ok).pack(side=tk.LEFT)
        ttk.Button(btns, text="Cancelar", command=top.destroy).pack(side=tk.LEFT, padx=(6, 0))
        top.wait_window()
        return result["value"]

    def _selected_exercise(self):
        sel = self.tv_ejercicios.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except Exception:
            return None

    def _add_exercise(self):
        payload = self._exercise_editor()
        if not payload:
            return
        if any(int(row["ejercicio"]) == payload["ejercicio"] for row in self._exercise_rows):
            messagebox.showwarning("Gest2A3Eco", "Ese ejercicio ya existe.", parent=self)
            return
        self._exercise_rows.append(payload)
        self._exercise_rows.sort(key=lambda row: int(row["ejercicio"]))
        self._refresh_exercises_tree()

    def _edit_exercise(self):
        ejercicio = self._selected_exercise()
        if ejercicio is None:
            return
        current = next((row for row in self._exercise_rows if int(row["ejercicio"]) == ejercicio), None)
        if not current:
            return
        payload = self._exercise_editor(current)
        if not payload:
            return
        if payload["ejercicio"] != ejercicio and any(int(row["ejercicio"]) == payload["ejercicio"] for row in self._exercise_rows):
            messagebox.showwarning("Gest2A3Eco", "Ese ejercicio ya existe.", parent=self)
            return
        current.update(payload)
        self._exercise_rows.sort(key=lambda row: int(row["ejercicio"]))
        self._refresh_exercises_tree()

    def _remove_exercise(self):
        ejercicio = self._selected_exercise()
        if ejercicio is None:
            return
        if len(self._exercise_rows) <= 1:
            messagebox.showwarning("Gest2A3Eco", "Debe existir al menos un ejercicio.", parent=self)
            return
        self._exercise_rows = [row for row in self._exercise_rows if int(row["ejercicio"]) != ejercicio]
        self._refresh_exercises_tree()

    def _load_banks_from_text(self, text: str):
        self._bank_items = [line.strip() for line in str(text or "").replace(";", "\n").replace(",", "\n").splitlines() if line.strip()]
        self._refresh_banks_tree()

    def _refresh_banks_tree(self):
        self.tv_bancos_empresa.delete(*self.tv_bancos_empresa.get_children())
        for idx, cuenta in enumerate(self._bank_items):
            self.tv_bancos_empresa.insert("", "end", iid=str(idx), values=(cuenta,))

    def _selected_bank_index(self):
        sel = self.tv_bancos_empresa.selection()
        return int(sel[0]) if sel else None

    def _add_bank(self):
        value = simpledialog.askstring("Banco empresa", "Cuenta bancaria o IBAN:", parent=self)
        if value and value.strip():
            self._bank_items.append(value.strip())
            self._refresh_banks_tree()

    def _edit_bank(self):
        idx = self._selected_bank_index()
        if idx is None:
            return
        value = simpledialog.askstring("Banco empresa", "Cuenta bancaria o IBAN:", initialvalue=self._bank_items[idx], parent=self)
        if value and value.strip():
            self._bank_items[idx] = value.strip()
            self._refresh_banks_tree()

    def _remove_bank(self):
        idx = self._selected_bank_index()
        if idx is None:
            return
        del self._bank_items[idx]
        self._refresh_banks_tree()

    def _load_terceros(self):
        self.tv_terceros_empresa.delete(*self.tv_terceros_empresa.get_children())
        codigo = str(self._empresa.get("codigo") or "")
        ejercicio = max((int(row["ejercicio"]) for row in self._exercise_rows), default=int(self._empresa.get("ejercicio") or 0))
        if not self._gestor or not codigo:
            self.lbl_terceros_info.configure(text="Guarda o abre una empresa existente para consultar sus terceros.")
            return
        try:
            terceros = self._gestor.listar_terceros_por_empresa(codigo, ejercicio)
        except Exception:
            terceros = []
        for idx, tercero in enumerate(terceros):
            tid = str(tercero.get("id") or idx)
            self.tv_terceros_empresa.insert("", "end", iid=tid, values=(
                tercero.get("nif", ""),
                tercero.get("nombre", ""),
                tercero.get("subcuenta_cliente", ""),
                tercero.get("subcuenta_proveedor", ""),
                tercero.get("subcuenta_ingreso", ""),
                tercero.get("subcuenta_gasto", ""),
            ))
        self.lbl_terceros_info.configure(text=f"Terceros asignados: {len(terceros)}")

    def _selected_third_party_id(self):
        sel = self.tv_terceros_empresa.selection()
        return str(sel[0]) if sel else None

    def _codigo_empresa_actual(self):
        return self.var_codigo.get().strip() or str(self._empresa.get("codigo") or "")

    def _nif_duplicado(self, nif: str | None, exclude_id: str | None = None) -> bool:
        val = "".join(str(nif or "").strip().upper().split())
        if not val:
            return False
        for tercero in (self._gestor.listar_terceros() if self._gestor else []):
            if exclude_id is not None and str(tercero.get("id")) == str(exclude_id):
                continue
            if "".join(str(tercero.get("nif") or "").strip().upper().split()) == val:
                return True
        return False

    def _save_third_party(self, payload: dict, third_party_id: str | None = None):
        nif = payload.get("nif")
        if nif and not validar_nif_cif_nie(nif):
            raise ValueError("NIF/CIF/NIE invalido.")
        if self._nif_duplicado(nif, exclude_id=third_party_id):
            raise ValueError("Ya existe un tercero con ese CIF/NIF.")
        if third_party_id:
            payload["id"] = third_party_id
        tid = self._gestor.upsert_tercero(payload)
        self._gestor.upsert_tercero_empresa(
            {
                "tercero_id": tid,
                "codigo_empresa": self._codigo_empresa_actual(),
                "ejercicio": 0,
                "subcuenta_cliente": "",
                "subcuenta_proveedor": "",
                "subcuenta_ingreso": "",
                "subcuenta_gasto": "",
            }
        )
        self._load_terceros()

    def _new_third_party(self):
        codigo = self._codigo_empresa_actual()
        if not codigo:
            messagebox.showwarning("Gest2A3Eco", "Guarda primero la empresa para asignar terceros.", parent=self)
            return
        dlg = TerceroFicha(self, None)
        if not dlg.result:
            return
        try:
            self._save_third_party(dlg.result)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self)

    def _edit_third_party(self):
        tid = self._selected_third_party_id()
        if not tid:
            return
        tercero = next((row for row in self._gestor.listar_terceros() if str(row.get("id")) == tid), None)
        if not tercero:
            return
        dlg = TerceroFicha(self, tercero)
        if not dlg.result:
            return
        try:
            self._save_third_party(dlg.result, third_party_id=tid)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self)

    def _edit_third_party_accounts(self):
        tid = self._selected_third_party_id()
        codigo = self._codigo_empresa_actual()
        if not tid or not codigo or not self._gestor:
            return
        rel = self._gestor.get_tercero_empresa(codigo, tid, 0) or {}
        tercero = next((row for row in self._gestor.listar_terceros() if str(row.get("id")) == tid), None) or {}
        top = tk.Toplevel(self)
        top.title("Subcuentas del tercero")
        top.resizable(False, False)
        top.transient(self)
        top.grab_set()
        frm = ttk.Frame(top, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=f"{tercero.get('nombre', '')} ({tercero.get('nif', '')})").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        vars_map = {
            "subcuenta_cliente": tk.StringVar(value=str(rel.get("subcuenta_cliente") or "")),
            "subcuenta_proveedor": tk.StringVar(value=str(rel.get("subcuenta_proveedor") or "")),
            "subcuenta_ingreso": tk.StringVar(value=str(rel.get("subcuenta_ingreso") or "")),
            "subcuenta_gasto": tk.StringVar(value=str(rel.get("subcuenta_gasto") or "")),
        }
        labels = (
            ("subcuenta_cliente", "Subcuenta cliente"),
            ("subcuenta_proveedor", "Subcuenta proveedor"),
            ("subcuenta_ingreso", "Subcuenta ingreso"),
            ("subcuenta_gasto", "Subcuenta gasto"),
        )
        for idx, (key, text) in enumerate(labels, start=1):
            ttk.Label(frm, text=text).grid(row=idx, column=0, sticky="w", pady=4)
            ttk.Entry(frm, textvariable=vars_map[key], width=24).grid(row=idx, column=1, sticky="w", pady=4)

        def _ok():
            self._gestor.upsert_tercero_empresa(
                {
                    "tercero_id": tid,
                    "codigo_empresa": codigo,
                    "ejercicio": 0,
                    "subcuenta_cliente": vars_map["subcuenta_cliente"].get().strip(),
                    "subcuenta_proveedor": vars_map["subcuenta_proveedor"].get().strip(),
                    "subcuenta_ingreso": vars_map["subcuenta_ingreso"].get().strip(),
                    "subcuenta_gasto": vars_map["subcuenta_gasto"].get().strip(),
                }
            )
            top.destroy()
            self._load_terceros()

        btns = ttk.Frame(frm)
        btns.grid(row=len(labels) + 1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(btns, text="Guardar", style="Primary.TButton", command=_ok).pack(side=tk.LEFT)
        ttk.Button(btns, text="Cancelar", command=top.destroy).pack(side=tk.LEFT, padx=(6, 0))
        top.wait_window()

    def _assign_existing_third_party(self):
        codigo = self._codigo_empresa_actual()
        if not codigo:
            messagebox.showwarning("Gest2A3Eco", "Guarda primero la empresa para asignar terceros.", parent=self)
            return
        assigned = {str(item) for item in self.tv_terceros_empresa.get_children()}
        terceros = [t for t in self._gestor.listar_terceros() if str(t.get("id")) not in assigned]
        if not terceros:
            messagebox.showinfo("Gest2A3Eco", "No hay terceros disponibles para asignar.", parent=self)
            return
        top = tk.Toplevel(self)
        top.title("Asignar tercero")
        top.resizable(False, False)
        top.transient(self)
        top.grab_set()
        frm = ttk.Frame(top, padding=10)
        frm.pack(fill="both", expand=True)
        lb = tk.Listbox(frm, height=min(12, len(terceros)), width=60, exportselection=False)
        for tercero in terceros:
            lb.insert(tk.END, f"{tercero.get('nombre', '')} ({tercero.get('nif', '')})")
        lb.pack(fill="both", expand=True)
        if terceros:
            lb.selection_set(0)

        def _ok():
            sel = lb.curselection()
            if not sel:
                top.destroy()
                return
            tercero = terceros[sel[0]]
            self._gestor.upsert_tercero_empresa(
                {
                    "tercero_id": tercero.get("id"),
                    "codigo_empresa": codigo,
                    "ejercicio": 0,
                    "subcuenta_cliente": "",
                    "subcuenta_proveedor": "",
                    "subcuenta_ingreso": "",
                    "subcuenta_gasto": "",
                }
            )
            top.destroy()
            self._load_terceros()

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Asignar", style="Primary.TButton", command=_ok).pack(side=tk.LEFT)
        ttk.Button(btns, text="Cancelar", command=top.destroy).pack(side=tk.LEFT, padx=(6, 0))
        top.wait_window()

    def _remove_third_party_assignment(self):
        tid = self._selected_third_party_id()
        codigo = self._codigo_empresa_actual()
        if not tid or not codigo:
            return
        if not messagebox.askyesno("Gest2A3Eco", "Quitar la asignacion del tercero a esta empresa?", parent=self):
            return
        try:
            self._gestor.eliminar_tercero_empresa(codigo, tid)
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self)
            return
        self._load_terceros()

    def _import_from_a3(self):
        try:
            data = importar_empresa_desde_a3(self.var_codigo.get())
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self)
            return
        self.var_codigo.set(str(data.get("codigo") or ""))
        if data.get("nombre"):
            self.var_nombre.set(str(data.get("nombre") or ""))
        if data.get("cif"):
            self.var_cif.set(str(data.get("cif") or ""))
        payload = self._exercise_from_row(data)
        current = next((row for row in self._exercise_rows if int(row["ejercicio"]) == payload["ejercicio"]), None)
        if current:
            current.update(payload)
        else:
            self._exercise_rows.append(payload)
            self._exercise_rows.sort(key=lambda row: int(row["ejercicio"]))
        self._refresh_exercises_tree()
        self.var_a3_info.set("Importacion A3 completada.\n" + str(data.get("_a3_info") or "Datos basicos detectados."))
        self._set_a3_preview(data)

    def _set_a3_preview(self, data: dict | None):
        payload = dict(data or {})
        lines = [
            f"Codigo: {payload.get('codigo', '')}",
            f"Nombre: {payload.get('nombre', '')}",
            f"CIF/NIF: {payload.get('cif', '')}",
            f"Ejercicio detectado: {payload.get('ejercicio', '')}",
            f"Digitos de plan: {payload.get('digitos_plan', '')}",
            f"Serie emitidas: {payload.get('serie_emitidas', '')}",
            f"Siguiente emitidas: {payload.get('siguiente_num_emitidas', '')}",
            f"Serie rectificativas: {payload.get('serie_emitidas_rect', '')}",
            f"Siguiente rectificativas: {payload.get('siguiente_num_emitidas_rect', '')}",
            "",
            "Origen A3 detectado:",
            str(payload.get("_a3_info") or "Sin detalle."),
        ]
        raw = str(payload.get("_a3_raw_header") or "").strip()
        if raw:
            lines.extend(["", "Cabecera leida del fichero A3:", raw])
        self.txt_a3_preview.configure(state="normal")
        self.txt_a3_preview.delete("1.0", tk.END)
        self.txt_a3_preview.insert("1.0", "\n".join(lines).strip() + "\n")
        self.txt_a3_preview.configure(state="disabled")

    def _choose_logo(self):
        path = filedialog.askopenfilename(title="Seleccionar logo (JPG)", filetypes=[("JPEG", "*.jpg;*.jpeg"), ("Todos", "*.*")])
        if path:
            self.var_logo.set(path)

    def _request_delete(self):
        codigo = self.var_codigo.get().strip() or str(self._empresa.get("codigo") or "")
        if not codigo:
            return
        if not messagebox.askyesno("Gest2A3Eco", f"Se eliminara la empresa {codigo} con todos sus ejercicios.\nContinuar?", parent=self):
            return
        self.result = {"_action": "delete_company", "codigo": codigo}
        self.destroy()

    def apply(self):
        try:
            if not self._exercise_rows:
                raise ValueError("Debes configurar al menos un ejercicio.")
            cuentas_text = "\n".join(self._bank_items).strip()
            logo_w_txt = self.var_logo_w.get().strip()
            logo_h_txt = self.var_logo_h.get().strip()
            base = {
                "codigo": self.var_codigo.get().strip(),
                "nombre": self.var_nombre.get().strip(),
                "digitos_plan": int(self.var_dig.get().strip() or "8"),
                "cuenta_bancaria": self._bank_items[0] if self._bank_items else "",
                "cuentas_bancarias": cuentas_text,
                "cif": self.var_cif.get().strip(),
                "direccion": self.var_dir.get().strip(),
                "cp": self.var_cp.get().strip(),
                "poblacion": self.var_pob.get().strip(),
                "provincia": self.var_prov.get().strip(),
                "telefono": self.var_tel.get().strip(),
                "email": self.var_mail.get().strip(),
                "logo_path": self.var_logo.get().strip(),
                "logo_max_width_mm": _to_float_es(logo_w_txt) if logo_w_txt else None,
                "logo_max_height_mm": _to_float_es(logo_h_txt) if logo_h_txt else None,
                "activo": bool(self.var_activo.get()),
            }
            ejercicios = []
            for row in sorted(self._exercise_rows, key=lambda item: int(item["ejercicio"])):
                item = dict(base)
                item.update(row)
                ejercicios.append(item)
            self.result = {"_action": "save_company", "_exercise_configs": ejercicios, **ejercicios[-1]}
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self)
            self.result = None
