"""
Utilidades compartidas por las pantallas globales del modulo
"Notificaciones Electronicas" (bandeja, certificados y buzones globales).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk


def seleccionar_cliente(parent, gestor) -> dict | None:
    """
    Muestra un dialogo modal para elegir un cliente (empresa).

    Devuelve el resumen del cliente (codigo, nombre, cif, ejercicio) o None
    si el usuario cancela.
    """
    empresas = gestor.listar_empresas_resumen()
    if not empresas:
        messagebox.showinfo("Gest2A3Eco", "No hay clientes dados de alta.", parent=parent)
        return None

    dlg = tk.Toplevel(parent)
    dlg.title("Seleccionar cliente")
    dlg.resizable(False, False)

    frm = ttk.Frame(dlg, padding=16)
    frm.pack(fill="both", expand=True)
    ttk.Label(frm, text="Cliente:").grid(row=0, column=0, sticky="e", padx=(0, 8), pady=6)

    nombres = [f"{e.get('nombre') or e.get('codigo')} ({e.get('codigo')})" for e in empresas]
    var = tk.StringVar(value=nombres[0])
    ttk.Combobox(frm, textvariable=var, values=nombres, state="readonly", width=40).grid(row=0, column=1, pady=6)

    result: dict = {}

    def _ok() -> None:
        idx = nombres.index(var.get())
        result["empresa"] = empresas[idx]
        dlg.destroy()

    def _cancel() -> None:
        dlg.destroy()

    btns = ttk.Frame(dlg, padding=(16, 0, 16, 16))
    btns.pack(fill="x")
    ttk.Button(btns, text="Cancelar", command=_cancel).pack(side="right", padx=(6, 0))
    ttk.Button(btns, text="Aceptar", command=_ok).pack(side="right")

    dlg.grab_set()
    dlg.transient(parent)
    dlg.wait_window()
    return result.get("empresa")
