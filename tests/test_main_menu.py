from main import (
    _deshabilitar_boton_secundario,
    _posicion_menu_contextual,
    _restaurar_boton_secundario,
)


class _RootFalso:
    def __init__(self):
        self.bindings = {}
        self.unbound = []

    @staticmethod
    def winfo_pointerx():
        return 640

    @staticmethod
    def winfo_pointery():
        return 180

    def bind_all(self, sequence, callback):
        self.bindings[sequence] = callback

    def unbind_all(self, sequence):
        self.unbound.append(sequence)


def test_menu_configuracion_se_abre_junto_al_puntero():
    root = _RootFalso()

    assert _posicion_menu_contextual(root) == (648, 188)


def test_boton_secundario_queda_bloqueado_en_toda_la_aplicacion():
    root = _RootFalso()

    _deshabilitar_boton_secundario(root)

    assert set(root.bindings) == {"<Button-3>", "<ButtonRelease-3>"}
    assert all(callback(None) == "break" for callback in root.bindings.values())

    _restaurar_boton_secundario(root)
    assert root.unbound == ["<Button-3>", "<ButtonRelease-3>"]
