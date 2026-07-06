"""
Vista global: Obtencion de certificados administrativos (Hacienda, Seguridad
Social, etc.). Acceso a nivel de despacho (no dentro de cada cliente).

Permite:
  - Elegir un cliente y un tipo de certificado y solicitar su obtencion.
  - Ver el listado de solicitudes de todos los clientes con su resumen
    (estado, resultado, fechas, ruta del PDF).
  - Abrir el PDF obtenido y compartirlo por email con el cliente.
"""
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from views.notificaciones_theme import *  # noqa: F401,F403
from services.aapp.certificados import TIPOS, solicitar_certificado, requisitos_ok
from services.aapp.base import OpcionesSync


def _label_tipo(code: str) -> str:
    org, descr, _url = TIPOS.get(code, ("", code, ""))
    return f"{descr} ({org})" if org else descr


class UICertificadosObtenidos(ttk.Frame):
    """Pestana global de solicitud/obtencion de certificados."""

    _COLS = [
        ("cliente",   "Cliente",     160, "w"),
        ("tipo",      "Certificado", 220, "w"),
        ("organismo", "Organismo",    80, "center"),
        ("estado",    "Estado",       95, "center"),
        ("resultado", "Resultado",    90, "center"),
        ("f_sol",     "Solicitado",  120, "center"),
        ("f_obt",     "Obtenido",    120, "center"),
        ("pdf",       "PDF",          50, "center"),
    ]

    def __init__(self, master, gestor, session=None):
        super().__init__(master)
        self._gestor = gestor
        self._session = session
        self._cache: list[dict] = []
        self._todas_empresas: list[str] = []
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build
    def _build(self):
        hdr = tk.Frame(self, bg=_HDR_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="\U0001F4C4  Obtencion de certificados", bg=_HDR_BG, fg=_HDR_FG,
                 font=("Segoe UI", 11, "bold")).pack(side="left", padx=16, pady=10)
        tk.Label(hdr, text="Solicita certificados de Hacienda, Seguridad Social, etc. para tus clientes",
                 bg=_HDR_BG, fg=_HDR_SUB, font=("Segoe UI", 9)).pack(side="left", pady=10)

        # Barra de solicitud
        bar = tk.Frame(self, bg="#e2e8f0", pady=6)
        bar.pack(fill="x", padx=8, pady=(0, 2))
        tk.Label(bar, text="Cliente:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(8, 4))
        self._var_cliente = tk.StringVar()
        self._cb_cliente = ttk.Combobox(bar, textvariable=self._var_cliente, state="normal", width=30)
        self._cb_cliente.pack(side="left", padx=(0, 10))
        self._cb_cliente.bind("<KeyRelease>", self._on_filtrar_clientes)
        self._cb_cliente.bind("<<ComboboxSelected>>", lambda _e: self._cb_cliente.icursor(tk.END))
        tk.Label(bar, text="Certificado:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self._tipo_labels = [_label_tipo(t) for t in TIPOS]
        self._tipo_codes = list(TIPOS.keys())
        self._var_tipo = tk.StringVar()
        self._cb_tipo = ttk.Combobox(bar, textvariable=self._var_tipo, state="readonly", width=42,
                                     values=self._tipo_labels)
        self._cb_tipo.pack(side="left", padx=(0, 10))
        self._btn_solicitar = tk.Button(bar, text="Solicitar", bg=_PRIMARY, fg="white",
                                        font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                                        padx=14, pady=3, command=self._on_solicitar)
        self._btn_solicitar.pack(side="left", padx=(0, 10))
        self._var_ver_navegador = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="Mostrar navegador", variable=self._var_ver_navegador,
                       bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left")

        # Toolbar acciones
        tb = tk.Frame(self, bg=_BG, pady=6)
        tb.pack(fill="x", padx=8)
        btn = dict(font=("Segoe UI", 9), relief="flat", cursor="hand2", padx=10, pady=4)
        self._btn_pdf = tk.Button(tb, text="Abrir PDF", bg="#475569", fg="white",
                                  command=self._on_abrir_pdf, state="disabled", **btn)
        self._btn_pdf.pack(side="left", padx=(0, 5))
        self._btn_email = tk.Button(tb, text="Compartir por email", bg="#0ea5e9", fg="white",
                                    command=self._on_email, state="disabled", **btn)
        self._btn_email.pack(side="left", padx=(0, 5))
        self._btn_del = tk.Button(tb, text="Eliminar", bg=_DANGER, fg="white",
                                  command=self._on_eliminar, state="disabled", **btn)
        self._btn_del.pack(side="left", padx=(0, 5))
        tk.Button(tb, text="↻ Actualizar", bg="#64748b", fg="white", command=self.refresh, **btn).pack(side="left")

        # Tabla
        wrapper = tk.Frame(self, bg=_BG)
        wrapper.pack(fill="both", expand=True, padx=8, pady=4)
        col_ids = ["_id"] + [c[0] for c in self._COLS]
        self._tv = ttk.Treeview(wrapper, columns=col_ids, show="headings", selectmode="browse")
        self._tv.column("_id", width=0, stretch=False)
        self._tv.heading("_id", text="")
        for key, header, width, anchor in self._COLS:
            self._tv.heading(key, text=header)
            self._tv.column(key, width=width, anchor=anchor, stretch=(key == "tipo"))
        self._tv.tag_configure("OBTENIDO",  foreground=_SUCCESS)
        self._tv.tag_configure("PENDIENTE", foreground=_WARNING)
        self._tv.tag_configure("ERROR",     foreground=_DANGER)
        sb = ttk.Scrollbar(wrapper, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=sb.set)
        self._tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._tv.bind("<<TreeviewSelect>>", self._on_select)
        self._tv.bind("<Double-1>", lambda _e: self._on_abrir_pdf())

        self._lbl_status = tk.Label(self, text="", bg=_BG, fg=_SUB, font=("Segoe UI", 8), anchor="w")
        self._lbl_status.pack(fill="x", side="bottom", padx=8)

    # ------------------------------------------------------------------ helpers
    def _fila(self):
        sel = self._tv.selection()
        if not sel:
            return None
        sid = self._tv.set(sel[0], "_id")
        return next((r for r in self._cache if str(r.get("id")) == str(sid)), None)

    def _cliente_sel(self):
        txt = self._var_cliente.get()
        return txt.split(" - ", 1)[0].strip() if txt else None

    def _tipo_sel(self):
        lbl = self._var_tipo.get()
        if lbl in self._tipo_labels:
            return self._tipo_codes[self._tipo_labels.index(lbl)]
        return None

    def _on_filtrar_clientes(self, event=None):
        if event and event.keysym in ("Return", "Tab", "Down", "Up", "Escape"):
            return
        texto = self._var_cliente.get().strip().lower()
        if texto:
            filtradas = [e for e in self._todas_empresas if texto in e.lower()]
        else:
            filtradas = self._todas_empresas
        self._cb_cliente.configure(values=filtradas)
        if filtradas:
            self._cb_cliente.event_generate("<<ComboboxDropdown>>")

    def _on_select(self, _e=None):
        r = self._fila()
        tiene_pdf = bool(r and r.get("pdf_path") and os.path.isfile(r.get("pdf_path") or ""))
        self._btn_pdf.configure(state="normal" if tiene_pdf else "disabled")
        self._btn_email.configure(state="normal" if tiene_pdf else "disabled")
        self._btn_del.configure(state="normal" if r else "disabled")

    # ------------------------------------------------------------------ solicitar
    def _on_solicitar(self):
        cod = self._cliente_sel()
        tipo = self._tipo_sel()
        if not cod:
            messagebox.showinfo("Gest2A3Eco", "Selecciona un cliente.", parent=self.winfo_toplevel())
            return
        if not tipo:
            messagebox.showinfo("Gest2A3Eco", "Selecciona un tipo de certificado.", parent=self.winfo_toplevel())
            return
        ok_req, msg_req = requisitos_ok(self._gestor, cod, tipo)
        if not ok_req:
            messagebox.showwarning("Faltan requisitos", msg_req, parent=self.winfo_toplevel())
            return
        if not messagebox.askyesno("Solicitar certificado",
                                   f"Solicitar '{_label_tipo(tipo)}' para el cliente {cod}?\n\n"
                                   "Se accedera al organismo con el certificado del cliente. Puede tardar.",
                                   parent=self.winfo_toplevel()):
            return
        self._btn_solicitar.configure(state="disabled")
        ver = bool(self._var_ver_navegador.get())
        self._mostrar_progreso(f"Solicitando '{_label_tipo(tipo)}'\npara el cliente {cod}...\n\n"
                               "Accediendo al organismo. Puede tardar unos segundos.")

        def _worker():
            import os as _os
            _logs = _os.path.join(_os.getcwd(), "logs")
            _op = OpcionesSync(headless=not ver, modo_diagnostico=True, carpeta_diagnostico=_logs)
            res = solicitar_certificado(self._gestor, cod, tipo, _op)
            self.after(0, lambda: self._solicitud_fin(res))

        threading.Thread(target=_worker, daemon=True).start()

    def _mostrar_progreso(self, texto):
        dlg = tk.Toplevel(self.winfo_toplevel())
        dlg.title("Procesando")
        dlg.resizable(False, False)
        dlg.transient(self.winfo_toplevel())
        try:
            dlg.protocol("WM_DELETE_WINDOW", lambda: None)  # no cerrable
        except Exception:
            pass
        ttk.Label(dlg, text=texto, justify="center", padding=18).pack()
        pb = ttk.Progressbar(dlg, mode="indeterminate", length=300)
        pb.pack(padx=18, pady=(0, 16))
        pb.start(12)
        dlg.update_idletasks()
        try:
            x = self.winfo_toplevel().winfo_rootx() + 120
            y = self.winfo_toplevel().winfo_rooty() + 120
            dlg.geometry(f"+{x}+{y}")
        except Exception:
            pass
        dlg.grab_set()
        self._prog = dlg

    def _cerrar_progreso(self):
        try:
            if getattr(self, "_prog", None) is not None:
                self._prog.grab_release()
                self._prog.destroy()
        except Exception:
            pass
        self._prog = None

    def _solicitud_fin(self, res):
        self._cerrar_progreso()
        try:
            self._btn_solicitar.configure(state="normal")
        except Exception:
            pass
        if res.estado == "OBTENIDO":
            messagebox.showinfo("Certificado obtenido",
                                f"{_label_tipo(res.tipo)}\nResultado: {res.resultado or '-'}\n"
                                f"PDF: {res.pdf_path or '-'}",
                                parent=self.winfo_toplevel())
        elif res.estado == "PENDIENTE":
            messagebox.showwarning("Pendiente de calibrar",
                                   res.mensaje or "El flujo de este certificado aun no esta disponible.",
                                   parent=self.winfo_toplevel())
        else:
            messagebox.showerror("No se pudo obtener",
                                 res.mensaje or "Error al solicitar el certificado.",
                                 parent=self.winfo_toplevel())
        self.refresh()

    # ------------------------------------------------------------------ acciones
    def _on_abrir_pdf(self):
        r = self._fila()
        if not r:
            return
        pdf = r.get("pdf_path")
        if not pdf or not os.path.isfile(pdf):
            messagebox.showwarning("Gest2A3Eco", "No hay PDF disponible para esta solicitud.",
                                   parent=self.winfo_toplevel())
            return
        try:
            os.startfile(pdf)  # Windows
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", f"No se pudo abrir el PDF:\n{exc}",
                                 parent=self.winfo_toplevel())

    def _on_email(self):
        r = self._fila()
        if not r:
            return
        pdf = r.get("pdf_path")
        if not pdf or not os.path.isfile(pdf):
            messagebox.showwarning("Gest2A3Eco", "No hay PDF que adjuntar.", parent=self.winfo_toplevel())
            return
        destino = r.get("empresa_email") or ""
        asunto = f"{_label_tipo(r.get('tipo'))} - {r.get('empresa_nombre') or r.get('codigo_empresa')}"
        cuerpo = (f"Adjunto el certificado solicitado.\n\n"
                  f"Cliente: {r.get('empresa_nombre') or r.get('codigo_empresa')}\n"
                  f"Tipo: {_label_tipo(r.get('tipo'))}\n"
                  f"Fecha: {r.get('fecha_obtencion') or r.get('fecha_solicitud') or ''}\n")
        try:
            from services.email_service import open_outlook_email
            open_outlook_email(to=destino, subject=asunto, body=cuerpo, attachments=[pdf])
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", f"No se pudo preparar el email:\n{exc}",
                                 parent=self.winfo_toplevel())

    def _on_eliminar(self):
        r = self._fila()
        if not r:
            return
        if not messagebox.askyesno("Eliminar solicitud",
                                   "Eliminar esta solicitud del listado?",
                                   parent=self.winfo_toplevel()):
            return
        try:
            self._gestor.eliminar_cert_solicitud(r.get("codigo_empresa"), r.get("id"))
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", str(exc), parent=self.winfo_toplevel())
            return
        self.refresh()

    # ------------------------------------------------------------------ refresh
    def refresh(self):
        # clientes
        empresas = self._gestor.listar_empresas_resumen()
        self._todas_empresas = [f"{e['codigo']} - {e.get('nombre','')}" for e in empresas]
        self._cb_cliente.configure(values=self._todas_empresas)

        self._cache = self._gestor.listar_cert_solicitudes_global()
        self._tv.delete(*self._tv.get_children())
        for r in self._cache:
            self._tv.insert("", tk.END, values=(
                r.get("id"),
                r.get("empresa_nombre") or r.get("codigo_empresa") or "",
                _label_tipo(r.get("tipo")),
                r.get("organismo") or "",
                r.get("estado") or "",
                r.get("resultado") or "",
                (r.get("fecha_solicitud") or "")[:16].replace("T", " "),
                (r.get("fecha_obtencion") or "")[:16].replace("T", " "),
                "Si" if (r.get("pdf_path") and os.path.isfile(r.get("pdf_path") or "")) else "-",
            ), tags=(r.get("estado") or "",))
        n = len(self._cache)
        obt = sum(1 for r in self._cache if r.get("estado") == "OBTENIDO")
        self._lbl_status.configure(text=f"{n} solicitud(es)  |  Obtenidos: {obt}")
        self._btn_pdf.configure(state="disabled")
        self._btn_email.configure(state="disabled")
        self._btn_del.configure(state="disabled")
