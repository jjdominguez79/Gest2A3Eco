"""Dialogos de configuracion global (solo accesibles desde el administrador)."""

import smtplib
import ssl
import tkinter as tk
from tkinter import messagebox, ttk

from services.email_service import load_smtp_config, save_smtp_config
from utils.utilidades import load_app_config, save_app_config


def abrir_configuracion_ocr(parent):
    dialog = tk.Toplevel(parent)
    dialog.title("Configuracion OCR")
    dialog.transient(parent)
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
    for row, label, var in ((1, "Endpoint Azure", endpoint), (2, "Clave Azure", key), (3, "ID modelo personalizado", model_id)):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=var, show="*" if row == 2 else "", width=55).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
    ttk.Label(frame, text="Usa el endpoint y KEY1 del mismo recurso de Document Intelligence que contiene el modelo. Tras cambiarlo, reinicia la aplicacion.", wraplength=560, foreground="#555").grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def save():
        selected = motor.get().strip().lower()
        if selected == "azure" and (not endpoint.get().strip() or not key.get().strip()):
            messagebox.showwarning("OCR", "Indica endpoint y clave de Azure.", parent=dialog)
            return
        cfg.update({
            "ocr_motor_activo": selected,
            "azure_doc_intelligence_endpoint": endpoint.get().strip(),
            "azure_doc_intelligence_key": key.get().strip(),
            "azure_doc_intelligence_model_id": model_id.get().strip(),
        })
        save_app_config(cfg)
        dialog.destroy()

    actions = ttk.Frame(frame)
    actions.grid(row=5, column=0, columnspan=2, sticky="e", pady=(12, 0))
    ttk.Button(actions, text="Cancelar", command=dialog.destroy).pack(side="left", padx=(0, 6))
    ttk.Button(actions, text="Guardar", command=save).pack(side="left")
    frame.columnconfigure(1, weight=1)


def abrir_configuracion_email(parent):
    dialog = tk.Toplevel(parent)
    dialog.title("Configuracion de email (SMTP)")
    dialog.transient(parent)
    dialog.grab_set()
    frame = ttk.Frame(dialog, padding=14)
    frame.pack(fill="both", expand=True)
    cfg = dict(load_smtp_config())
    fields = (("Servidor SMTP", "host", False), ("Puerto", "port", False), ("Usuario", "user", False), ("Contrasena", "password", True), ("Email remitente", "from_addr", False))
    vars_ = {}
    for row, (label, key, secret) in enumerate(fields):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=3)
        var = tk.StringVar(value=str(cfg.get(key) or ("587" if key == "port" else "")))
        vars_[key] = var
        ttk.Entry(frame, textvariable=var, show="*" if secret else "", width=42).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
    tls = tk.BooleanVar(value=bool(cfg.get("use_tls", True)))
    ssl_ = tk.BooleanVar(value=bool(cfg.get("use_ssl", False)))
    ttk.Checkbutton(frame, text="Usar STARTTLS", variable=tls).grid(row=5, column=0, columnspan=2, sticky="w")
    ttk.Checkbutton(frame, text="Usar SSL", variable=ssl_).grid(row=6, column=0, columnspan=2, sticky="w")
    status = ttk.Label(frame, text="", wraplength=420)
    status.grid(row=7, column=0, columnspan=2, sticky="w", pady=5)

    def build():
        try:
            port = int(vars_["port"].get().strip() or "587")
        except ValueError:
            port = 587
        return {"host": vars_["host"].get().strip(), "port": port, "user": vars_["user"].get().strip(), "password": vars_["password"].get(), "from_addr": vars_["from_addr"].get().strip(), "use_tls": tls.get(), "use_ssl": ssl_.get()}

    def test():
        test_cfg = build()
        try:
            if test_cfg["use_ssl"]:
                with smtplib.SMTP_SSL(test_cfg["host"], test_cfg["port"], context=ssl.create_default_context(), timeout=8) as server:
                    if test_cfg["user"]: server.login(test_cfg["user"], test_cfg["password"])
            else:
                with smtplib.SMTP(test_cfg["host"], test_cfg["port"], timeout=8) as server:
                    server.ehlo()
                    if test_cfg["use_tls"]: server.starttls(); server.ehlo()
                    if test_cfg["user"]: server.login(test_cfg["user"], test_cfg["password"])
            status.configure(text="Conexion correcta", foreground="#198754")
        except Exception as exc:
            status.configure(text=f"Error de conexion: {exc}", foreground="#c0392b")

    def save():
        save_smtp_config(build())
        dialog.destroy()

    actions = ttk.Frame(frame); actions.grid(row=8, column=0, columnspan=2, pady=(10, 0))
    ttk.Button(actions, text="Probar conexion", command=test).pack(side="left", padx=4)
    ttk.Button(actions, text="Guardar", command=save).pack(side="left", padx=4)
    ttk.Button(actions, text="Cancelar", command=dialog.destroy).pack(side="left", padx=4)
    frame.columnconfigure(1, weight=1)
