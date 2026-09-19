"""
Vista global: Obtencion de certificados administrativos (Hacienda, Seguridad
Social, etc.). Acceso a nivel de despacho (no dentro de cada cliente).

Permite:
  - Elegir un cliente y un tipo de certificado y solicitar su obtencion.
  - Ver el listado de solicitudes de todos los clientes con su resumen
    (estado, resultado, fechas, ruta del PDF).
  - Abrir el PDF obtenido y compartirlo por email con el cliente.
  - Publicar el PDF en el area documental que consume la aplicacion Flutter.
"""
from __future__ import annotations

import os
import tempfile
import threading
import tkinter as tk
import unicodedata
import uuid
from datetime import date
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from views.notificaciones_theme import *  # noqa: F401,F403
from services.aapp.certificados import TIPOS
from services.backend_client_service import BackendClientService


def _label_tipo(code: str) -> str:
    org, descr, _url = TIPOS.get(code, ("", code, ""))
    return f"{descr} ({org})" if org else descr


def _normalizar_busqueda(valor) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(ch for ch in texto if not unicodedata.combining(ch)).casefold()


def _label_cliente(empresa: dict) -> str:
    nombre = str(empresa.get("nombre") or "Sin nombre").strip()
    cif = str(empresa.get("cif") or "").strip()
    codigo = str(empresa.get("codigo") or "").strip()
    partes = [nombre]
    if cif:
        partes.append(cif)
    if codigo:
        partes.append(codigo)
    return " - ".join(partes)


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
        ("flutter",   "Flutter",      75, "center"),
    ]

    def __init__(self, master, gestor, session=None):
        super().__init__(master)
        self._gestor = gestor
        self._session = session
        self._cache: list[dict] = []
        self._todas_empresas: list[str] = []
        self._cliente_codes: dict[str, str] = {}
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
        tk.Label(bar, text="Buscar:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(8, 4))
        self._var_buscar_cliente = tk.StringVar()
        self._ent_buscar_cliente = ttk.Entry(
            bar, textvariable=self._var_buscar_cliente, width=22,
        )
        self._ent_buscar_cliente.pack(side="left", padx=(0, 8))
        self._ent_buscar_cliente.bind("<KeyRelease>", self._on_filtrar_clientes)
        tk.Label(bar, text="Cliente:", bg="#e2e8f0", font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self._var_cliente = tk.StringVar()
        self._cb_cliente = ttk.Combobox(
            bar, textvariable=self._var_cliente, state="readonly", width=38,
        )
        self._cb_cliente.pack(side="left", padx=(0, 10))
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
        tk.Label(
            bar,
            text="El worker usa exclusivamente la copia cifrada de Azure",
            bg="#e2e8f0",
            fg=_SUB,
            font=("Segoe UI", 8),
        ).pack(side="left")

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
        self._btn_publicar = tk.Button(
            tb, text="Enviar a documentos", bg="#7c3aed", fg="white",
            command=self._on_publicar, state="disabled", **btn,
        )
        self._btn_publicar.pack(side="left", padx=(0, 5))
        self._btn_reintentar = tk.Button(
            tb, text="Reintentar", bg="#d97706", fg="white",
            command=self._on_reintentar, state="disabled", **btn,
        )
        self._btn_reintentar.pack(side="left", padx=(0, 5))
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
        self._tv.tag_configure("REQUIERE REINTENTO", foreground="#d97706")
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
        return self._cliente_codes.get(txt) if txt else None

    def _tipo_sel(self):
        lbl = self._var_tipo.get()
        if lbl in self._tipo_labels:
            return self._tipo_codes[self._tipo_labels.index(lbl)]
        return None

    def _on_filtrar_clientes(self, event=None):
        texto = _normalizar_busqueda(self._var_buscar_cliente.get())
        if texto:
            filtradas = [
                label for label in self._todas_empresas
                if texto in _normalizar_busqueda(label)
            ]
        else:
            filtradas = self._todas_empresas
        self._cb_cliente.configure(values=filtradas)
        if filtradas:
            self._var_cliente.set(filtradas[0])
        else:
            self._var_cliente.set("")

    def _on_select(self, _e=None):
        r = self._fila()
        tiene_pdf = bool(r and (r.get("document_id") or r.get("receipt_document_id")))
        self._btn_pdf.configure(state="normal" if tiene_pdf else "disabled")
        self._btn_email.configure(state="normal" if r and r.get("document_id") else "disabled")
        publicable = bool(
            r
            and r.get("requester_type") == "desktop"
            and r.get("status") == "completed"
            and r.get("document_id")
            and r.get("document_status") == "draft"
        )
        self._btn_publicar.configure(state="normal" if publicable else "disabled")
        reintentable = bool(r and r.get("status") in {"needs_action", "failed", "awaiting_issuance"})
        self._btn_reintentar.configure(
            state="normal" if reintentable else "disabled",
            text="Comprobar emision" if r and r.get("submitted_at") else "Reintentar",
        )
        eliminable = bool(
            r
            and r.get("status") in {"failed", "cancelled"}
            and not r.get("document_id")
            and not r.get("receipt_document_id")
            and not r.get("submitted_at")
        )
        self._btn_del.configure(state="normal" if eliminable else "disabled")

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
        anterior = next((
            r for r in self._cache
            if r.get("company_code") == cod
            and r.get("certificate_type") == tipo
            and r.get("status") in {"needs_action", "failed", "awaiting_issuance"}
        ), None)
        accion = "Reintentar" if anterior else "Solicitar"
        detalle = (
            "Se volvera a poner en cola la solicitud existente, sin crear un duplicado."
            if anterior else
            "La solicitud se enviara al worker, que utilizara exclusivamente "
            "el certificado cifrado custodiado en Azure."
        )
        if not messagebox.askyesno(f"{accion} certificado",
                                   f"{accion} '{_label_tipo(tipo)}' para el cliente {cod}?\n\n"
                                   f"{detalle}", parent=self.winfo_toplevel()):
            return
        parametros = dict(anterior.get("parameters") or {}) if anterior else None
        if not anterior:
            parametros = self._pedir_parametros(tipo)
            if parametros is None:
                return
        self._btn_solicitar.configure(state="disabled")

        def _worker():
            try:
                backend = BackendClientService()
                estado = backend.get_client_certificate_status(company_code=cod)
                if not estado.get("configured"):
                    raise ValueError(
                        "El cliente no tiene un certificado custodiado en Azure. "
                        "Configuralo antes de crear la solicitud."
                    )
                if anterior:
                    result = backend.retry_certificate_request(anterior["id"])
                else:
                    result = backend.create_certificate_request(
                        company_code=cod,
                        certificate_type=tipo,
                        parameters=parametros,
                        idempotency_key=f"desktop-{uuid.uuid4().hex}",
                    )
                self.after(0, lambda: self._solicitud_fin(result, None))
            except Exception as exc:
                self.after(0, lambda error=exc: self._solicitud_fin(None, error))

        threading.Thread(target=_worker, daemon=True).start()

    def _pedir_parametros(self, tipo):
        """Solicita solo los datos adicionales exigidos por cada organismo."""
        parent = self.winfo_toplevel()
        if tipo == "AEAT_CONTRATISTAS":
            tax_id = simpledialog.askstring(
                "Contratistas y subcontratistas",
                "CIF/NIF de la empresa con la que el cliente contrata:",
                parent=parent,
            )
            if tax_id is None:
                return None
            tax_id = "".join(ch for ch in tax_id.upper() if ch.isalnum())
            if len(tax_id) < 8:
                messagebox.showwarning(
                    "Dato obligatorio", "Introduce un CIF/NIF valido.", parent=parent,
                )
                return None
            name = simpledialog.askstring(
                "Contratistas y subcontratistas",
                "Nombre o razon social de esa empresa (opcional):",
                parent=parent,
            )
            if name is None:
                return None
            parametros = {"contracting_party_tax_id": tax_id}
            if name.strip():
                parametros["contracting_party_name"] = name.strip()
            return parametros
        if tipo == "TGSS_SIN_DEUDA_FECHA":
            value = simpledialog.askstring(
                "Certificado a una fecha",
                "Fecha del certificado (AAAA-MM-DD):",
                initialvalue=date.today().isoformat(),
                parent=parent,
            )
            if value is None:
                return None
            return {"as_of_date": value.strip()}
        return {}

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

    def _solicitud_fin(self, res, error=None):
        self._cerrar_progreso()
        try:
            self._btn_solicitar.configure(state="normal")
        except Exception:
            pass
        if error is not None:
            messagebox.showerror("No se pudo obtener",
                                 str(error),
                                 parent=self.winfo_toplevel())
        else:
            messagebox.showinfo(
                "Solicitud enviada",
                "La solicitud ha quedado en cola. El worker obtendra el certificado "
                "y lo dejara disponible en esta pantalla. Solo se enviara al area "
                "del cliente cuando pulses 'Enviar a documentos'.",
                parent=self.winfo_toplevel(),
            )
        self.refresh()

    # ------------------------------------------------------------------ acciones
    def _on_reintentar(self):
        solicitud = self._fila()
        if not solicitud or solicitud.get("status") not in {"needs_action", "failed", "awaiting_issuance"}:
            return
        if not messagebox.askyesno(
            "Reintentar certificado",
            ("Se consultara el expediente ya presentado, sin pedir otro certificado."
             if solicitud.get("submitted_at") else
             "La misma solicitud volvera a ponerse en cola para que el worker la procese."),
            parent=self.winfo_toplevel(),
        ):
            return
        self._btn_reintentar.configure(state="disabled")

        def _worker():
            try:
                result = BackendClientService().retry_certificate_request(solicitud["id"])
                self.after(0, lambda: self._solicitud_fin(result, None))
            except Exception as exc:
                self.after(0, lambda error=exc: self._solicitud_fin(None, error))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_abrir_pdf(self):
        r = self._fila()
        if not r:
            return
        try:
            pdf = self._descargar_pdf(r)
            os.startfile(pdf)  # Windows
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", f"No se pudo abrir el PDF:\n{exc}",
                                 parent=self.winfo_toplevel())

    def _on_email(self):
        r = self._fila()
        if not r or not r.get("document_id"):
            return
        empresa = self._gestor.get_empresa(r.get("company_code")) or {}
        destino = empresa.get("email") or empresa.get("correo") or ""
        asunto = f"{_label_tipo(r.get('certificate_type'))} - {r.get('company_name') or r.get('company_code')}"
        cuerpo = (f"Adjunto el certificado solicitado.\n\n"
                  f"Cliente: {r.get('company_name') or r.get('company_code')}\n"
                  f"Tipo: {_label_tipo(r.get('certificate_type'))}\n"
                  f"Fecha: {r.get('completed_at') or r.get('created_at') or ''}\n")
        try:
            pdf = self._descargar_pdf(r)
            from services.email_service import open_outlook_email
            open_outlook_email(to=destino, subject=asunto, body=cuerpo, attachments=[pdf])
        except Exception as exc:
            messagebox.showerror("Gest2A3Eco", f"No se pudo preparar el email:\n{exc}",
                                 parent=self.winfo_toplevel())

    def _descargar_pdf(self, solicitud):
        if not (solicitud.get("document_id") or solicitud.get("receipt_document_id")):
            raise ValueError("La solicitud todavia no tiene un PDF disponible.")
        content, filename, _content_type = (
            BackendClientService().download_certificate_request_document(
                solicitud["id"],
                **({"receipt": True} if not solicitud.get("document_id") else {}),
            )
        )
        if not content.startswith(b"%PDF-"):
            raise ValueError("El servidor no devolvio un PDF valido.")
        safe_name = os.path.basename(filename) or f"certificado-{solicitud['id']}.pdf"
        target = Path(tempfile.gettempdir()) / f"gestinem-{uuid.uuid4().hex}-{safe_name}"
        target.write_bytes(content)
        return str(target)

    def _on_publicar(self):
        solicitud = self._fila()
        if (
            not solicitud
            or solicitud.get("document_status") != "draft"
            or not solicitud.get("document_id")
        ):
            return
        if not messagebox.askyesno(
            "Enviar a documentos",
            "El certificado se publicara en el area documental del cliente y se le "
            "enviara una notificacion. ¿Quieres continuar?",
            parent=self.winfo_toplevel(),
        ):
            return
        self._btn_publicar.configure(state="disabled")

        def _worker():
            try:
                resultado = BackendClientService().publish_certificate_request_document(
                    solicitud["id"],
                )
                self.after(0, lambda: self._publicacion_fin(resultado, None))
            except Exception as exc:
                self.after(
                    0,
                    lambda error=exc: self._publicacion_fin(None, error),
                )

        threading.Thread(target=_worker, daemon=True).start()

    def _publicacion_fin(self, resultado, error=None):
        if error is None and resultado:
            messagebox.showinfo(
                "Documento publicado",
                "El certificado ya esta disponible en el modulo de documentos del cliente.",
                parent=self.winfo_toplevel(),
            )
        else:
            messagebox.showerror(
                "No se pudo publicar",
                str(error or "El servidor no confirmo la publicacion"),
                parent=self.winfo_toplevel(),
            )
        self.refresh()

    def _on_eliminar(self):
        solicitud = self._fila()
        if (
            not solicitud
            or solicitud.get("status") not in {"failed", "cancelled"}
            or solicitud.get("document_id")
        ):
            return
        if not messagebox.askyesno(
            "Eliminar intento",
            "Se eliminara definitivamente este intento sin documento. ¿Continuar?",
            parent=self.winfo_toplevel(),
        ):
            return
        self._btn_del.configure(state="disabled")

        def _worker():
            try:
                BackendClientService().delete_certificate_request(solicitud["id"])
                self.after(0, lambda: self._eliminacion_fin(None))
            except Exception as exc:
                self.after(0, lambda error=exc: self._eliminacion_fin(error))

        threading.Thread(target=_worker, daemon=True).start()

    def _eliminacion_fin(self, error=None):
        if error is None:
            messagebox.showinfo(
                "Intento eliminado",
                "La solicitud fallida se ha eliminado.",
                parent=self.winfo_toplevel(),
            )
        else:
            messagebox.showerror(
                "No se pudo eliminar", str(error), parent=self.winfo_toplevel(),
            )
        self.refresh()

    # ------------------------------------------------------------------ refresh
    def refresh(self):
        # clientes
        empresas = self._gestor.listar_empresas_resumen()
        empresas = sorted(
            empresas,
            key=lambda e: (
                _normalizar_busqueda(e.get("nombre")),
                _normalizar_busqueda(e.get("cif")),
                _normalizar_busqueda(e.get("codigo")),
            ),
        )
        self._todas_empresas = [_label_cliente(e) for e in empresas]
        self._cliente_codes = {
            _label_cliente(e): str(e.get("codigo") or "") for e in empresas
        }
        self._cb_cliente.configure(values=self._todas_empresas)
        if self._todas_empresas and self._var_cliente.get() not in self._cliente_codes:
            self._var_cliente.set(self._todas_empresas[0])

        self._lbl_status.configure(text="Consultando solicitudes centrales...")

        def _worker():
            try:
                items = BackendClientService().list_certificate_requests(limit=500)
                self.after(0, lambda: self._refresh_fin(items, None))
            except Exception as exc:
                self.after(0, lambda error=exc: self._refresh_fin([], error))

        threading.Thread(target=_worker, daemon=True).start()

    def _refresh_fin(self, items, error=None):
        # Las operaciones internas (por ejemplo DEHU_SYNC) se consultan desde
        # su propia pantalla y no deben mezclarse con certificados obtenidos.
        self._cache = [
            item for item in items if item.get("certificate_type") in TIPOS
        ]
        self._tv.delete(*self._tv.get_children())
        for r in self._cache:
            status = str(r.get("status") or "").lower()
            estado = {
                "queued": "PENDIENTE",
                "processing": "PROCESANDO",
                "completed": "OBTENIDO",
                "awaiting_issuance": "PENDIENTE EMISION",
                "needs_action": "REQUIERE REINTENTO",
                "failed": "ERROR",
                "cancelled": "CANCELADO",
            }.get(status, status.upper())
            self._tv.insert("", tk.END, values=(
                r.get("id"),
                r.get("company_name") or r.get("company_code") or "",
                _label_tipo(r.get("certificate_type")),
                r.get("issuing_organization") or "",
                estado,
                r.get("certificate_result") or r.get("error_message") or r.get("result_summary") or "",
                (r.get("created_at") or "")[:16].replace("T", " "),
                (r.get("completed_at") or "")[:16].replace("T", " "),
                "Si" if r.get("document_id") else "Resguardo" if r.get("receipt_document_id") else "-",
                (
                    "Publicado"
                    if r.get("document_status") == "published"
                    else "Pendiente"
                    if r.get("document_status") == "draft"
                    else "-"
                ),
            ), tags=(estado,))
        n = len(self._cache)
        obt = sum(1 for r in self._cache if r.get("status") == "completed")
        texto = f"{n} solicitud(es) centrales  |  Obtenidos: {obt}"
        if error is not None:
            texto = f"No se pudieron consultar las solicitudes centrales: {error}"
        self._lbl_status.configure(text=texto)
        self._btn_pdf.configure(state="disabled")
        self._btn_email.configure(state="disabled")
        self._btn_publicar.configure(state="disabled")
        self._btn_reintentar.configure(state="disabled")
        self._btn_del.configure(state="disabled")
