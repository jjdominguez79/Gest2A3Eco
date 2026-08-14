"""Tests de regresion para el bug de validacion del codigo A3 al crear empresa nueva.

Bug: al crear una empresa nueva, _empresa.get("codigo") y _codigo son vacios,
por lo que se llamaba a normalizar_codigo_empresa_a3("") que lanzaba un error
falso antes de llegar a validar el codigo nuevo introducido por el usuario.
"""
from unittest.mock import MagicMock, patch, call
import pytest

from utils.validaciones import normalizar_codigo_empresa_a3


# ---------------------------------------------------------------------------
# Tests unitarios de la funcion de validacion (sin UI)
# ---------------------------------------------------------------------------

def test_normalizar_codigo_valido():
    assert normalizar_codigo_empresa_a3("E01100") == "E01100"


def test_normalizar_codigo_vacio_lanza_error():
    with pytest.raises(ValueError, match="E seguido de exactamente cinco digitos"):
        normalizar_codigo_empresa_a3("")


def test_normalizar_codigo_invalido_lanza_error():
    with pytest.raises(ValueError):
        normalizar_codigo_empresa_a3("XXXX")


# ---------------------------------------------------------------------------
# Helpers para simular UIConfiguracionEmpresa._save() sin Tkinter
# ---------------------------------------------------------------------------

def _make_save_fn(empresa_dict, codigo_str):
    """Devuelve una funcion que ejecuta la logica de _save() aislada de Tkinter."""
    from utils.validaciones import normalizar_codigo_empresa_a3

    def _save_logic(gestor):
        codigo = normalizar_codigo_empresa_a3(codigo_str)
        codigo_anterior_raw = empresa_dict.get("codigo") or ""
        codigo_anterior = (
            normalizar_codigo_empresa_a3(codigo_anterior_raw)
            if codigo_anterior_raw
            else ""
        )
        if codigo_anterior and codigo != codigo_anterior:
            gestor.cambiar_codigo_empresa(codigo_anterior, codigo)
        return codigo, codigo_anterior

    return _save_logic


# ---------------------------------------------------------------------------
# Escenario 1: empresa NUEVA con codigo valido
# ---------------------------------------------------------------------------

def test_empresa_nueva_codigo_valido_se_acepta():
    """E01100 debe aceptarse al crear empresa nueva sin codigo anterior."""
    gestor = MagicMock()
    save = _make_save_fn({}, "E01100")
    codigo, codigo_anterior = save(gestor)
    assert codigo == "E01100"
    assert codigo_anterior == ""
    gestor.cambiar_codigo_empresa.assert_not_called()


def test_empresa_nueva_sin_codigo_anterior():
    """Empresa nueva con _empresa vacio: no debe intentarse validar codigo anterior."""
    gestor = MagicMock()
    save = _make_save_fn({"codigo": None}, "E00001")
    codigo, codigo_anterior = save(gestor)
    assert codigo_anterior == ""
    gestor.cambiar_codigo_empresa.assert_not_called()


# ---------------------------------------------------------------------------
# Escenario 2: codigo nuevo invalido sigue rechazandose
# ---------------------------------------------------------------------------

def test_codigo_nuevo_invalido_sigue_fallando():
    """Un codigo nuevo con formato incorrecto debe seguir lanzando ValueError."""
    with pytest.raises(ValueError):
        save = _make_save_fn({}, "INVALIDO")
        save(MagicMock())


def test_codigo_vacio_sigue_fallando():
    with pytest.raises(ValueError):
        save = _make_save_fn({}, "")
        save(MagicMock())


# ---------------------------------------------------------------------------
# Escenario 3: edicion de empresa existente sin cambio de codigo
# ---------------------------------------------------------------------------

def test_edicion_empresa_sin_cambio_codigo_no_llama_cambiar():
    """Si el codigo no cambia, cambiar_codigo_empresa no debe invocarse."""
    gestor = MagicMock()
    save = _make_save_fn({"codigo": "E01100"}, "E01100")
    codigo, codigo_anterior = save(gestor)
    assert codigo == "E01100"
    assert codigo_anterior == "E01100"
    gestor.cambiar_codigo_empresa.assert_not_called()


# ---------------------------------------------------------------------------
# Escenario 4: edicion de empresa existente cambiando codigo
# ---------------------------------------------------------------------------

def test_edicion_empresa_cambia_codigo_llama_cambiar():
    """Si el codigo cambia de un valor valido a otro, debe invocarse cambiar_codigo_empresa."""
    gestor = MagicMock()
    save = _make_save_fn({"codigo": "E01100"}, "E02200")
    codigo, codigo_anterior = save(gestor)
    assert codigo == "E02200"
    assert codigo_anterior == "E01100"
    gestor.cambiar_codigo_empresa.assert_called_once_with("E01100", "E02200")


# ---------------------------------------------------------------------------
# Escenario 5: cambiar_codigo_empresa solo si hay codigo anterior Y cambia
# ---------------------------------------------------------------------------

def test_cambiar_codigo_empresa_solo_con_anterior_y_cambio():
    """Tabla de verdad: solo se invoca cuando anterior no vacio Y distinto al nuevo."""
    gestor = MagicMock()

    # Sin anterior -> no se invoca
    _make_save_fn({}, "E00001")(gestor)
    gestor.cambiar_codigo_empresa.assert_not_called()

    # Con anterior igual -> no se invoca
    _make_save_fn({"codigo": "E00001"}, "E00001")(gestor)
    gestor.cambiar_codigo_empresa.assert_not_called()

    # Con anterior distinto -> se invoca
    _make_save_fn({"codigo": "E00001"}, "E00002")(gestor)
    gestor.cambiar_codigo_empresa.assert_called_once_with("E00001", "E00002")
