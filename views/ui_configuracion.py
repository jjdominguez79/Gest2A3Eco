"""Dialogos de configuracion global (solo accesibles desde el administrador)."""

import tkinter as tk
from tkinter import messagebox, ttk

from utils.utilidades import load_app_config, save_app_config


def abrir_configuracion_ocr(parent):
    dialog = tk.Toplevel(parent)
    dialog.title("Configuracion OCR")
    dialog.transient(parent)
    dialog.grab_set()
    frame = ttk.Frame(dialog, padding=14)
    frame.pack(fill="both", expand=True)
    cfg = load_app_config()
    from utils.credential_store import get_azure_doc_key, store_azure_doc_key
    motor = tk.StringVar(value=str(cfg.get("ocr_motor_activo") or ""))
    endpoint = tk.StringVar(value=str(cfg.get("azure_doc_intelligence_endpoint") or ""))
    key = tk.StringVar(value=get_azure_doc_key() or "")
    model_id = tk.StringVar(value=str(cfg.get("azure_doc_intelligence_model_id") or ""))
    ttk.Label(frame, text="Motor OCR").grid(row=0, column=0, sticky="w", pady=3)
    ttk.Combobox(frame, textvariable=motor, state="readonly", values=("", "azure"), width=42).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=3)
    for row, label, var in ((1, "Endpoint Azure", endpoint), (2, "Clave Azure", key), (3, "ID modelo personalizado", model_id)):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=var, show="*" if row == 2 else "", width=55).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
    ttk.Label(frame, text="Usa el endpoint y KEY1 del mismo recurso de Document Intelligence que contiene el modelo. Tras cambiarlo, reinicia la aplicacion.", wraplength=560, foreground="#555").grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def save():
        selected = motor.get().strip().lower()
        if selected == "azure" and (not endpoint.get().strip() or not key.get().strip()):
            messagebox.showwarning("OCR", "Indica endpoint y clave de Azure.", parent=dialog)
            return
        azure_key = key.get().strip()
        if azure_key:
            store_azure_doc_key(azure_key)
        cfg.update({
            "ocr_motor_activo": selected,
            "azure_doc_intelligence_endpoint": endpoint.get().strip(),
            "azure_doc_intelligence_model_id": model_id.get().strip(),
        })
        save_app_config(cfg)
        dialog.destroy()

    actions = ttk.Frame(frame)
    actions.grid(row=5, column=0, columnspan=2, sticky="e", pady=(12, 0))
    ttk.Button(actions, text="Cancelar", command=dialog.destroy).pack(side="left", padx=(0, 6))
    ttk.Button(actions, text="Guardar", command=save).pack(side="left")
    frame.columnconfigure(1, weight=1)
