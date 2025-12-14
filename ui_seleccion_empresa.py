import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import Dialog
import sqlite3
from datetime import datetime
from pathlib import Path

from import_empresas_csv import import_empresas_csv

from ui_facturas_emitidas import TercerosDialog

class EmpresaDialog(Dialog):
    def __init__(self, parent, titulo, empresa=None):
        base = {
            "codigo": "",
            "nombre": "",
            "digitos_plan": 8,
            "ejercicio": 2025,
            "serie_emitidas": "A",
            "siguiente_num_emitidas": 1,
            "cif": "",
            "direccion": "",
            "cp": "",
            "poblacion": "",
            "provincia": "",
            "telefono": "",
            "email": "",
            "logo_path": "",
        }
        if empresa:
            base.update(empresa)
        # Normaliza valores None a "" para evitar errores de conversión
        for k in ("digitos_plan", "ejercicio", "serie_emitidas", "siguiente_num_emitidas"):
            if base.get(k) is None:
                base[k] = ""
        self.empresa = base
        super().__init__(parent, titulo)

    def body(self, master):
        self.var_codigo = tk.StringVar(value=str(self.empresa.get("codigo","")))
        self.var_nombre = tk.StringVar(value=str(self.empresa.get("nombre","")))
        self.var_dig = tk.StringVar(value=str(self.empresa.get("digitos_plan") or ""))
        self.var_eje = tk.StringVar(value=str(self.empresa.get("ejercicio") or ""))
        self.var_serie = tk.StringVar(value=str(self.empresa.get("serie_emitidas") or ""))
        self.var_next = tk.StringVar(value=str(self.empresa.get("siguiente_num_emitidas") or ""))
        self.var_cif = tk.StringVar(value=str(self.empresa.get("cif","")))
        self.var_dir = tk.StringVar(value=str(self.empresa.get("direccion","")))
        self.var_cp = tk.StringVar(value=str(self.empresa.get("cp","")))
        self.var_pob = tk.StringVar(value=str(self.empresa.get("poblacion","")))
        self.var_prov = tk.StringVar(value=str(self.empresa.get("provincia","")))
        self.var_tel = tk.StringVar(value=str(self.empresa.get("telefono","")))
        self.var_mail = tk.StringVar(value=str(self.empresa.get("email","")))
        self.var_logo = tk.StringVar(value=str(self.empresa.get("logo_path","")))

        ttk.Label(master, text="Codigo").grid(row=0, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_codigo).grid(row=0, column=1)
        ttk.Label(master, text="Nombre").grid(row=1, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_nombre, width=40).grid(row=1, column=1)
        ttk.Label(master, text="Digitos plan").grid(row=2, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_dig, width=8).grid(row=2, column=1, sticky="w")
        ttk.Label(master, text="Ejercicio").grid(row=3, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_eje, width=8).grid(row=3, column=1, sticky="w")
        ttk.Label(master, text="Serie emitidas").grid(row=4, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_serie, width=10).grid(row=4, column=1, sticky="w")
        ttk.Label(master, text="Siguiente numero").grid(row=5, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_next, width=10).grid(row=5, column=1, sticky="w")
        ttk.Label(master, text="CIF/NIF").grid(row=6, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_cif, width=18).grid(row=6, column=1, sticky="w")
        ttk.Label(master, text="Direccion").grid(row=7, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_dir, width=40).grid(row=7, column=1, sticky="w")
        ttk.Label(master, text="CP").grid(row=8, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_cp, width=8).grid(row=8, column=1, sticky="w")
        ttk.Label(master, text="Poblacion").grid(row=9, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_pob, width=32).grid(row=9, column=1, sticky="w")
        ttk.Label(master, text="Provincia").grid(row=10, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_prov, width=24).grid(row=10, column=1, sticky="w")
        ttk.Label(master, text="Telefono").grid(row=11, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_tel, width=20).grid(row=11, column=1, sticky="w")
        ttk.Label(master, text="Email").grid(row=12, column=0, sticky="w"); ttk.Entry(master, textvariable=self.var_mail, width=30).grid(row=12, column=1, sticky="w")
        ttk.Label(master, text="Logo (JPG)").grid(row=13, column=0, sticky="w")
        row_logo = ttk.Frame(master)
        row_logo.grid(row=13, column=1, sticky="we")
        ttk.Entry(row_logo, textvariable=self.var_logo, width=32).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row_logo, text="Buscar", command=self._choose_logo).pack(side=tk.LEFT, padx=4)
        return master

    def _choose_logo(self):
        path = filedialog.askopenfilename(title="Seleccionar logo (JPG)", filetypes=[("JPEG", "*.jpg;*.jpeg"), ("Todos", "*.*")])
        if path:
            self.var_logo.set(path)

    def apply(self):
        try:
            self.result = {
                "codigo": self.var_codigo.get().strip(),
                "nombre": self.var_nombre.get().strip(),
                "digitos_plan": int(self.var_dig.get().strip() or "8"),
                "ejercicio": int(self.var_eje.get().strip() or "2025"),
                "serie_emitidas": self.var_serie.get().strip() or "A",
                "siguiente_num_emitidas": int(self.var_next.get().strip() or "1"),
                "cif": self.var_cif.get().strip(),
                "direccion": self.var_dir.get().strip(),
                "cp": self.var_cp.get().strip(),
                "poblacion": self.var_pob.get().strip(),
                "provincia": self.var_prov.get().strip(),
                "telefono": self.var_tel.get().strip(),
                "email": self.var_mail.get().strip(),
                "logo_path": self.var_logo.get().strip(),
            }
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", str(e))
            self.result = None

class UISeleccionEmpresa(ttk.Frame):
    def __init__(self, parent, gestor, on_ok):
        super().__init__(parent)
        self.gestor = gestor
        self.on_ok = on_ok
        self.pack(fill=tk.BOTH, expand=True)
        self.empresas_cache = []
        self._build()

    def _build(self):
        ttk.Label(self, text="Selecciona empresa", font=("Segoe UI", 12, "bold")).pack(pady=8)

        search_row = ttk.Frame(self)
        search_row.pack(fill=tk.X, padx=10, pady=(4, 0))
        ttk.Label(search_row, text="Buscar").pack(side=tk.LEFT)
        self.var_buscar = tk.StringVar()
        entry_buscar = ttk.Entry(search_row, textvariable=self.var_buscar, width=40)
        entry_buscar.pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
        ttk.Button(search_row, text="Limpiar", command=lambda: self.var_buscar.set("")).pack(side=tk.LEFT)
        self.var_buscar.trace_add("write", lambda *_: self._aplicar_filtro())

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        self.tv = ttk.Treeview(tree_frame, columns=("codigo","nombre","cif","digitos","ejercicio","serie","next"), show="headings", height=12)
        for c,t,w in (
            ("codigo","Codigo",120),
            ("nombre","Nombre",320),
            ("cif","CIF",120),
            ("digitos","Digitos",70),
            ("ejercicio","Ejercicio",80),
            ("serie","Serie",80),
            ("next","Siguiente",90),
        ):
            self.tv.heading(c, text=t); self.tv.column(c, width=w)

        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tv.yview)
        xscroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tv.xview)
        self.tv.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        self.tv.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self._refresh()

        bar = ttk.Frame(self); bar.pack(fill=tk.X, padx=10, pady=6)
        ttk.Button(bar, text="Importar CSV empresas", style="Primary.TButton", command=self._importar_csv).pack(side=tk.LEFT, padx=(0,6))
        ttk.Button(bar, text="Nueva empresa", style="Primary.TButton", command=self._nueva).pack(side=tk.LEFT)
        ttk.Button(bar, text="Editar empresa", style="Primary.TButton", command=self._editar).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Copiar empresa", style="Primary.TButton", command=self._copiar).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Eliminar empresa", style="Primary.TButton", command=self._eliminar).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Terceros", style="Primary.TButton", command=self._terceros).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Continuar", style="Primary.TButton", command=self._continuar).pack(side=tk.RIGHT)

    def _refresh(self):
        self.empresas_cache = self.gestor.listar_empresas()
        self._aplicar_filtro()

    def _aplicar_filtro(self):
        filtro = (self.var_buscar.get() or "").strip().lower()
        self.tv.delete(*self.tv.get_children())
        for e in self.empresas_cache:
            texto = " ".join([
                str(e.get("codigo","")),
                str(e.get("nombre","")),
                str(e.get("cif","")),
                str(e.get("ejercicio","")),
            ]).lower()
            if filtro and filtro not in texto:
                continue
            self.tv.insert("", tk.END, iid=f"{e.get('codigo')}::{e.get('ejercicio')}", values=(
                e.get("codigo"),
                e.get("nombre"),
                e.get("cif",""),
                e.get("digitos_plan",8),
                e.get("ejercicio") if e.get("ejercicio") is not None else "",
                e.get("serie_emitidas","A"),
                e.get("siguiente_num_emitidas",1),
            ))

    def _sel_empresa(self):
        sel = self.tv.selection()
        if not sel:
            return None, None
        codigo, _, _, _, eje, *_ = self.tv.item(sel[0], "values")
        try:
            eje_int = int(eje)
        except Exception:
            eje_int = eje
        return codigo, eje_int

    def _backup_db(self) -> Path:
        db_path = Path(self.gestor.db_path)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = db_path.suffix or ".db"
        backup_path = db_path.with_name(f"{stamp}_copy{suffix}")
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.gestor.conn.commit()
        except Exception:
            pass
        with sqlite3.connect(backup_path) as dst:
            self.gestor.conn.backup(dst)  # snapshot consistente aunque haya conexi¢n abierta
        return backup_path

    def _importar_csv(self):
        csv_path = filedialog.askopenfilename(
            title="Selecciona CSV de empresas",
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")],
        )
        if not csv_path:
            return
        try:
            backup_path = self._backup_db()
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", f"No se pudo crear la copia de seguridad:\n{e}")
            return
        try:
            n = import_empresas_csv(str(self.gestor.db_path), csv_path)
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", f"Error al importar el CSV:\n{e}")
            return
        self._refresh()
        messagebox.showinfo(
            "Gest2A3Eco",
            f"Importaci¢n completada.\nFilas procesadas: {n}.\nCopia: {backup_path.name}",
        )

    def _nueva(self):
        dlg = EmpresaDialog(self, "Nueva empresa")
        if dlg.result:
            self.gestor.upsert_empresa(dlg.result)
            self._refresh()
            messagebox.showinfo("Gest2A3Eco", "Empresa guardada.")

    def _editar(self):
        codigo, eje = self._sel_empresa()
        if not codigo:
            messagebox.showinfo("Gest2A3Eco", "Selecciona una empresa.")
            return
        emp = self.gestor.get_empresa(codigo, eje)
        dlg = EmpresaDialog(self, "Editar empresa", emp)
        if dlg.result:
            self.gestor.upsert_empresa(dlg.result)
            self._refresh()
            messagebox.showinfo("Gest2A3Eco", "Cambios guardados.")

    def _copiar(self):
        codigo, eje = self._sel_empresa()
        if not codigo:
            messagebox.showinfo("Gest2A3Eco", "Selecciona una empresa para copiar.")
            return
        emp = self.gestor.get_empresa(codigo, eje)
        if not emp:
            messagebox.showwarning("Gest2A3Eco", "No se encontró la empresa seleccionada.")
            return
        # Prepara datos base para el nuevo año con numeración reiniciada
        base = dict(emp)
        base["codigo"] = ""
        try:
            base["ejercicio"] = int(emp.get("ejercicio", 0)) + 1
        except Exception:
            pass
        base["siguiente_num_emitidas"] = 1
        dlg = EmpresaDialog(self, f"Copiar {codigo}", base)
        if not dlg.result:
            return
        if not dlg.result.get("codigo"):
            messagebox.showwarning("Gest2A3Eco", "Introduce un código para la nueva empresa.")
            return
        if self.gestor.get_empresa(dlg.result["codigo"], dlg.result.get("ejercicio")):
            messagebox.showwarning("Gest2A3Eco", "Ya existe una empresa con ese código y ejercicio.")
            return
        try:
            self.gestor.copiar_empresa(codigo, eje, dlg.result)
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", str(e))
            return
        self._refresh()
        for iid in self.tv.get_children():
            vals = self.tv.item(iid, "values") or []
            if vals and vals[0] == dlg.result["codigo"]:
                self.tv.selection_set(iid)
                self.tv.see(iid)
                break
        messagebox.showinfo("Gest2A3Eco", "Empresa copiada con plantillas y terceros.")

    def _terceros(self):
        codigo, eje = self._sel_empresa()
        if not codigo:
            messagebox.showinfo("Gest2A3Eco", "Selecciona una empresa.")
            return
        emp = self.gestor.get_empresa(codigo, eje) or {"codigo":codigo,"digitos_plan":8,"ejercicio":eje}
        TercerosDialog(self, self.gestor, emp.get("codigo"), emp.get("digitos_plan",8), emp.get("ejercicio", eje))

    def _continuar(self):
        codigo, eje = self._sel_empresa()
        if not codigo:
            messagebox.showwarning("Gest2A3Eco","Selecciona una empresa.")
            return
        emp = self.gestor.get_empresa(codigo, eje) or {}
        nombre = emp.get("nombre","")
        self.on_ok(codigo, eje, nombre)

    def _eliminar(self):
        codigo, eje = self._sel_empresa()
        if not codigo:
            messagebox.showinfo("Gest2A3Eco", "Selecciona una empresa para eliminar.")
            return
        emp = self.gestor.get_empresa(codigo, eje) or {}
        nombre = emp.get("nombre", codigo)
        if not messagebox.askyesno(
            "Gest2A3Eco",
            f"IMPORTANTE:\nVas a eliminar {nombre} (código {codigo}, ejercicio {eje}).\nSe borrarán sus plantillas, facturas y subcuentas de terceros de este ejercicio.\n¿Continuar?",
        ):
            return
        try:
            self.gestor.eliminar_empresa(codigo, eje)
        except Exception as e:
            messagebox.showerror("Gest2A3Eco", str(e))
            return
        self._refresh()
        messagebox.showinfo("Gest2A3Eco", "Empresa eliminada.")
