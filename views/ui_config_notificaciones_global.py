"""Configuracion unica de sincronizacion y comunicacion de notificaciones."""
from __future__ import annotations

import threading
import re
import tkinter as tk
from tkinter import messagebox, ttk

from services.aapp.notification_communication import (
    DEFAULT_EMAIL_HTML,
    DEFAULT_EMAIL_SUBJECT,
    render_email_notificaciones,
)
from services.aapp.configuracion_notificaciones import aplicar_programacion_global
from views.notificaciones_theme import *  # noqa: F401,F403
from views.ui_buzones import PERIODICIDADES


class UIConfigNotificacionesGlobal(ttk.Frame):
    def __init__(self, master, gestor, session=None):
        super().__init__(master)
        self._gestor = gestor
        self._session = session
        self._build()
        self.refresh()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=_HDR_BG)
        hdr.pack(fill="x")
        tk.Label(
            hdr, text="Configuracion global", bg=_HDR_BG, fg=_HDR_FG,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left", padx=16, pady=10)
        tk.Label(
            hdr, text="Una unica politica para todos los buzones DEHu",
            bg=_HDR_BG, fg=_HDR_SUB, font=("Segoe UI", 9),
        ).pack(side="left", pady=10)

        form = tk.Frame(self, bg=_BG)
        form.pack(fill="both", expand=True, padx=18, pady=14)
        form.columnconfigure(1, weight=1)

        self._var_periodicidad = tk.StringVar(value="MANUAL")
        self._var_hora_diaria = tk.StringVar()
        self._var_avisar = tk.BooleanVar(value=False)
        self._var_email_interno = tk.StringVar()
        self._var_asunto = tk.StringVar(value=DEFAULT_EMAIL_SUBJECT)

        tk.Label(form, text="Periodicidad de sincronizacion:", bg=_BG, fg=_TEXT).grid(
            row=0, column=0, sticky="e", padx=(0, 8), pady=4,
        )
        ttk.Combobox(
            form, textvariable=self._var_periodicidad, values=PERIODICIDADES,
            state="readonly", width=22,
        ).grid(row=0, column=1, sticky="w", pady=4)
        tk.Label(form, text="Hora diaria (Madrid):", bg=_BG, fg=_TEXT).grid(
            row=1, column=0, sticky="e", padx=(0, 8), pady=4,
        )
        ttk.Entry(form, textvariable=self._var_hora_diaria, width=8).grid(
            row=1, column=1, sticky="w", pady=4,
        )
        tk.Label(
            form, text="Formato HH:MM. Se aplica cuando la periodicidad es DIARIA.",
            bg=_BG, fg=_SUB, font=("Segoe UI", 8),
        ).grid(row=2, column=1, sticky="w", pady=(0, 5))
        tk.Label(form, text="Email del resumen interno:", bg=_BG, fg=_TEXT).grid(
            row=3, column=0, sticky="e", padx=(0, 8), pady=4,
        )
        ttk.Entry(form, textvariable=self._var_email_interno, width=50).grid(
            row=3, column=1, sticky="w", pady=4,
        )
        ttk.Checkbutton(
            form,
            text="Enviar aviso por email al comunicar notificaciones al cliente",
            variable=self._var_avisar,
        ).grid(row=4, column=1, sticky="w", pady=(5, 2))
        tk.Label(
            form,
            text="El destinatario se toma siempre del campo Email de la ficha de cada cliente.",
            bg=_BG, fg=_SUB, font=("Segoe UI", 8),
        ).grid(row=5, column=1, sticky="w", pady=(0, 10))

        tk.Label(form, text="Asunto del email:", bg=_BG, fg=_TEXT).grid(
            row=6, column=0, sticky="e", padx=(0, 8), pady=4,
        )
        ttk.Entry(form, textvariable=self._var_asunto, width=70).grid(
            row=6, column=1, sticky="ew", pady=4,
        )
        tk.Label(form, text="Plantilla HTML:", bg=_BG, fg=_TEXT).grid(
            row=7, column=0, sticky="ne", padx=(0, 8), pady=4,
        )
        editor_wrap = tk.Frame(form, bg=_BG)
        editor_wrap.grid(row=7, column=1, sticky="nsew", pady=4)
        form.rowconfigure(7, weight=1)
        self._txt_html = tk.Text(editor_wrap, wrap="none", height=18, font=("Consolas", 9))
        sy = ttk.Scrollbar(editor_wrap, orient="vertical", command=self._txt_html.yview)
        sx = ttk.Scrollbar(editor_wrap, orient="horizontal", command=self._txt_html.xview)
        self._txt_html.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.pack(side="right", fill="y")
        sx.pack(side="bottom", fill="x")
        self._txt_html.pack(fill="both", expand=True)
        tk.Label(
            form,
            text="Campos: {nombre_cliente}, {nif_cliente}, {cantidad}, {asunto}, {asuntos}, {notificaciones}",
            bg=_BG, fg=_SUB, font=("Segoe UI", 8),
        ).grid(row=8, column=1, sticky="w", pady=(2, 8))

        buttons = tk.Frame(form, bg=_BG)
        buttons.grid(row=9, column=1, sticky="e")
        ttk.Button(buttons, text="Restaurar plantilla", command=self._restaurar).pack(side="left", padx=4)
        ttk.Button(buttons, text="Comprobar plantilla", command=self._vista_previa).pack(side="left", padx=4)
        self._btn_guardar = tk.Button(
            buttons, text="Guardar y aplicar a todos los buzones", bg=_PRIMARY,
            fg="white", relief="flat", cursor="hand2", padx=12, pady=5,
            command=self._guardar,
        )
        self._btn_guardar.pack(side="left", padx=4)

        if self._session is not None and not self._session.is_admin():
            self._btn_guardar.configure(state="disabled")

    def refresh(self) -> None:
        config = self._gestor.get_notif_config_global()
        self._var_periodicidad.set(config.get("periodicidad_sync") or "MANUAL")
        self._var_hora_diaria.set(config.get("hora_sync_diaria") or "")
        self._var_avisar.set(bool(config.get("avisar_cliente_email")))
        self._var_email_interno.set(config.get("email_resumen_interno") or "")
        self._var_asunto.set(config.get("email_asunto") or DEFAULT_EMAIL_SUBJECT)
        self._txt_html.delete("1.0", tk.END)
        self._txt_html.insert("1.0", config.get("email_html") or DEFAULT_EMAIL_HTML)

    def _restaurar(self) -> None:
        self._var_asunto.set(DEFAULT_EMAIL_SUBJECT)
        self._txt_html.delete("1.0", tk.END)
        self._txt_html.insert("1.0", DEFAULT_EMAIL_HTML)

    def _datos(self) -> dict:
        return {
            "periodicidad_sync": self._var_periodicidad.get() or "MANUAL",
            "hora_sync_diaria": self._var_hora_diaria.get().strip(),
            "avisar_cliente_email": bool(self._var_avisar.get()),
            "email_resumen_interno": self._var_email_interno.get().strip(),
            "email_asunto": self._var_asunto.get().strip(),
            "email_html": self._txt_html.get("1.0", tk.END).strip(),
        }

    def _validar(self, datos: dict) -> None:
        hora = datos["hora_sync_diaria"]
        if datos["periodicidad_sync"] == "DIARIA" and not hora:
            raise ValueError("Indica la hora diaria de sincronizacion (HH:MM).")
        if hora and not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", hora):
            raise ValueError("La hora diaria debe tener formato HH:MM.")
        if datos["email_resumen_interno"] and "@" not in datos["email_resumen_interno"]:
            raise ValueError("El email del resumen interno no es valido.")
        if not datos["email_asunto"]:
            raise ValueError("El asunto del email no puede estar vacio.")
        if not datos["email_html"]:
            raise ValueError("La plantilla HTML no puede estar vacia.")
        render_email_notificaciones(
            datos,
            {"nombre": "Cliente de ejemplo", "cif": "B12345678"},
            [{"asunto": "Aviso de ejemplo", "organismo_emisor": "DEHu", "fecha_puesta_disposicion": "2026-09-14"}],
        )

    def _vista_previa(self) -> None:
        try:
            datos = self._datos()
            self._validar(datos)
            asunto, html = render_email_notificaciones(
                datos,
                {"nombre": "Cliente de ejemplo", "cif": "B12345678"},
                [{"asunto": "Notificacion de ejemplo", "organismo_emisor": "AEAT", "fecha_puesta_disposicion": "2026-09-14"}],
            )
        except Exception as exc:
            messagebox.showerror("Plantilla", str(exc), parent=self.winfo_toplevel())
            return
        dialog = tk.Toplevel(self)
        dialog.title(asunto)
        dialog.geometry("760x520")
        text = tk.Text(dialog, wrap="word")
        text.insert("1.0", html)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True, padx=8, pady=8)

    def _guardar(self) -> None:
        try:
            datos = self._datos()
            self._validar(datos)
            self._gestor.upsert_notif_config_global(datos)
        except Exception as exc:
            messagebox.showerror("Configuracion global", str(exc), parent=self.winfo_toplevel())
            return
        self._btn_guardar.configure(state="disabled", text="Aplicando...")

        def worker():
            try:
                guardados, errores = aplicar_programacion_global(self._gestor, datos)
            except Exception as exc:
                guardados, errores = 0, [str(exc)]
            self.after(0, lambda: self._aplicado(guardados, errores))

        threading.Thread(target=worker, daemon=True).start()

    def _aplicado(self, guardados: int, errores: list[str]) -> None:
        self._btn_guardar.configure(state="normal", text="Guardar y aplicar a todos los buzones")
        texto = f"Configuracion guardada. Buzones aplicados: {guardados}."
        if errores:
            texto += f"\nErrores: {len(errores)}\n\n" + "\n".join(errores[:10])
        messagebox.showinfo("Configuracion global", texto, parent=self.winfo_toplevel())
