"""
Modulo Notificaciones Electronicas — contenedor principal.

Organiza las cuatro pantallas del modulo en un Notebook:
  1. Bandeja    — notificaciones recibidas de organismos
  2. Buzones    — canales de recepcion configurados
  3. Organismos — catalogo de administraciones
  4. Certificados — certificados digitales

En el primer acceso siembra datos simulados si la empresa no tiene datos previos.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from controllers.ui_notificaciones_controller import UINotificacionesController
from views.ui_bandeja_notificaciones import UIBandejaNotificaciones
from views.ui_buzones import UIBuzones
from views.ui_certificados import UICertificados
from views.ui_organismos import UIOrganismos


class UINotificaciones(ttk.Frame):
    """
    Contenedor principal del modulo Notificaciones Electronicas.
    Muestra cuatro pestanas: Bandeja, Buzones, Organismos, Certificados.
    """

    def __init__(self, master, gestor, codigo: str, ejercicio: int, nombre: str = "", session=None):
        super().__init__(master)
        self._gestor    = gestor
        self._codigo    = codigo
        self._ejercicio = int(ejercicio)
        self._nombre    = nombre
        self._session   = session

        # Sembrar datos simulados al primer acceso (idempotente)
        self._sembrar_si_necesario()

        # Controlador de la bandeja (orquesta acciones sobre notif_bandeja)
        self._controller = UINotificacionesController(
            self, gestor, codigo, ejercicio, session=session
        )

        self._build()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        # ── Pestana 1: Bandeja ──────────────────────────────────────────────
        tab_bandeja = ttk.Frame(nb)
        nb.add(tab_bandeja, text="  \u2709  Bandeja  ")
        UIBandejaNotificaciones(
            tab_bandeja, self._controller, session=self._session
        ).pack(fill="both", expand=True)

        # ── Pestana 2: Buzones ──────────────────────────────────────────────
        tab_buzones = ttk.Frame(nb)
        nb.add(tab_buzones, text="  \u25a6  Buzones  ")
        UIBuzones(
            tab_buzones, self._gestor, self._codigo, session=self._session
        ).pack(fill="both", expand=True)

        # ── Pestana 3: Organismos ───────────────────────────────────────────
        tab_org = ttk.Frame(nb)
        nb.add(tab_org, text="  \u2318  Organismos  ")
        UIOrganismos(
            tab_org, self._gestor, session=self._session
        ).pack(fill="both", expand=True)

        # ── Pestana 4: Certificados ─────────────────────────────────────────
        tab_cert = ttk.Frame(nb)
        nb.add(tab_cert, text="  \u2460  Certificados  ")
        UICertificados(
            tab_cert, self._gestor, self._codigo, session=self._session
        ).pack(fill="both", expand=True)

    # ------------------------------------------------------------------ seed

    def _sembrar_si_necesario(self) -> None:
        """
        Siembra organismos globales y datos de empresa si estan vacios.
        Totalmente idempotente: no inserta si ya existen datos.
        """
        try:
            self._gestor.sembrar_organismos_simulados()
            self._gestor.sembrar_datos_empresa_simulados(self._codigo, self._ejercicio)
        except Exception:
            # No debe interrumpir la carga del modulo si falla el seeder
            pass
