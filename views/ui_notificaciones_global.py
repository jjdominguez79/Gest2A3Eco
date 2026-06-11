"""
Modulo global "Notificaciones Electronicas".

Centro operativo del despacho para la gestion de notificaciones
electronicas de TODOS los clientes. Se accede desde el menu principal
(no es necesario entrar cliente por cliente).

Subpantallas:
    - Bandeja global:    notificaciones de todos los clientes.
    - Certificados:      certificados digitales de todos los clientes.
    - Buzones:           buzones de notificacion de todos los clientes.
    - Organismos:        catalogo global de organismos (sin cambios).
    - Sincronizaciones:  historico global de sincronizaciones (logs).

El cliente es una dimension de configuracion y filtrado: la configuracion
detallada de certificados/buzones de un cliente concreto vive tambien en su
ficha (UIConfiguracionEmpresa), pero ambas vistas operan sobre las mismas
tablas (notif_certificados, notif_buzones, notif_bandeja, ...).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from views.notificaciones_theme import *  # noqa: F401,F403
from views.ui_bandeja_global import UIBandejaGlobal
from views.ui_buzones_global import UIBuzonesGlobal
from views.ui_certificados_global import UICertificadosGlobal
from views.ui_organismos import UIOrganismos
from views.ui_sync_logs import UISyncLogs


class UINotificacionesGlobal(ttk.Frame):
    """Contenedor del modulo global de Notificaciones Electronicas."""

    def __init__(self, master, gestor, session=None, on_open_empresa=None):
        super().__init__(master)
        self._gestor = gestor
        self._session = session
        self._on_open_empresa = on_open_empresa
        self._tabs: dict[str, ttk.Frame] = {}
        self._build()

    def _build(self) -> None:
        hdr = tk.Frame(self, bg=_HDR_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="✉  Notificaciones Electronicas", bg=_HDR_BG, fg=_HDR_FG,
                 font=("Segoe UI", 13, "bold"), anchor="w").pack(side="left", padx=16, pady=10)
        tk.Label(hdr, text="Gestion centralizada de notificaciones de todos los clientes",
                 bg=_HDR_BG, fg=_HDR_SUB, font=("Segoe UI", 9)).pack(side="left", pady=10)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self._nb = nb

        bandeja = UIBandejaGlobal(nb, self._gestor, session=self._session, on_open_empresa=self._on_open_empresa)
        nb.add(bandeja, text="Bandeja global")

        certificados = UICertificadosGlobal(nb, self._gestor, session=self._session)
        nb.add(certificados, text="Certificados")

        buzones = UIBuzonesGlobal(nb, self._gestor, session=self._session)
        nb.add(buzones, text="Buzones")

        organismos = UIOrganismos(nb, self._gestor, session=self._session)
        nb.add(organismos, text="Organismos")

        logs = UISyncLogs(nb, self._gestor, session=self._session)
        nb.add(logs, text="Sincronizaciones / Logs")

        self._views = [bandeja, certificados, buzones, organismos, logs]
        nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, _e=None) -> None:
        idx = self._nb.index(self._nb.select())
        view = self._views[idx]
        if hasattr(view, "refresh"):
            view.refresh()

    def refresh(self) -> None:
        for view in self._views:
            if hasattr(view, "refresh"):
                view.refresh()
