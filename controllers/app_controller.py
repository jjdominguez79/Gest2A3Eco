from tkinter import ttk

from views.ui_seleccion_empresa import UISeleccionEmpresa
from views.ui_plantillas import UIPlantillasEmpresa
from views.ui_procesos import UIProcesos
from views.ui_facturas_emitidas import UIFacturasEmitidas


class AppController:
    """
    Controlador principal (MVC) encargado de la navegacion entre pantallas.
    """

    def __init__(self, content_frame: ttk.Frame, gestor):
        self._content = content_frame
        self._gestor = gestor
        self._current_frame = None

    def start(self):
        self.show(self.build_seleccion)

    def show(self, factory):
        if self._current_frame is not None:
            self._current_frame.destroy()
        frame = factory(self._content)
        frame.pack(fill="both", expand=True)
        self._current_frame = frame

    def build_seleccion(self, parent):
        return UISeleccionEmpresa(parent, self._gestor, self.on_empresa_ok)

    def on_empresa_ok(self, codigo, ejercicio, nombre):
        self.show(lambda parent: self.build_dashboard(parent, codigo, ejercicio, nombre))

    def build_dashboard(self, parent, codigo, ejercicio, nombre):
        nb = ttk.Notebook(parent)
        nb.add(
            UIPlantillasEmpresa(nb, self._gestor, codigo, ejercicio, nombre),
            text="Plantillas",
        )
        nb.add(
            UIFacturasEmitidas(nb, self._gestor, codigo, ejercicio, nombre),
            text="Facturas emitidas",
        )
        nb.add(
            UIProcesos(nb, self._gestor, codigo, ejercicio, nombre),
            text="Generar ficheros",
        )
        return nb
