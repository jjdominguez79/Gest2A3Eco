"""Ordenacion reutilizable para tablas ``ttk.Treeview``."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation


_NUMERO = re.compile(r"^[+-]?\d+(?:[.,]\d+)?%?$")
_FECHA_INICIAL = re.compile(
    r"^(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?"
    r"|\d{2}/\d{2}/\d{4}(?: \d{2}:\d{2}(?::\d{2})?)?)"
)
_FORMATOS_FECHA = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
)


def _texto_orden(valor) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or "").strip())
    return "".join(
        caracter for caracter in texto if not unicodedata.combining(caracter)
    ).casefold()


def _fecha_orden(texto: str) -> datetime | None:
    candidato = texto.strip()
    if not candidato:
        return None
    fecha_inicial = _FECHA_INICIAL.match(candidato)
    if fecha_inicial:
        candidato = fecha_inicial.group(1)
    try:
        return datetime.fromisoformat(candidato.replace("Z", "+00:00")).replace(
            tzinfo=None,
        )
    except ValueError:
        pass
    for formato in _FORMATOS_FECHA:
        try:
            return datetime.strptime(candidato, formato)
        except ValueError:
            continue
    return None


def clave_orden_treeview(valor):
    """Devuelve una clave comparable para fechas, numeros y texto visible."""
    texto = str(valor or "").strip()
    fecha = _fecha_orden(texto)
    if fecha is not None:
        return 0, fecha
    numero = texto.replace(" ", "")
    if _NUMERO.fullmatch(numero):
        try:
            return 1, Decimal(numero.rstrip("%").replace(",", "."))
        except InvalidOperation:
            pass
    return 2, _texto_orden(texto)


class OrdenadorTreeview:
    """Convierte todas las cabeceras visibles en controles de ordenacion."""

    def __init__(
        self, tree, columnas, *, columna_inicial: str = "",
        descendente: bool = False,
    ):
        self._tree = tree
        self._titulos = dict(columnas)
        self._columna = columna_inicial if columna_inicial in self._titulos else ""
        self._descendente = bool(descendente)
        self._actualizar_cabeceras()

    @property
    def columna(self) -> str:
        return self._columna

    @property
    def descendente(self) -> bool:
        return self._descendente

    def ordenar(self, columna: str) -> None:
        if columna not in self._titulos:
            return
        if self._columna == columna:
            self._descendente = not self._descendente
        else:
            self._columna = columna
            self._descendente = False
        self._actualizar_cabeceras()
        self.reaplicar()

    def reaplicar(self) -> None:
        """Aplica otra vez el orden despues de repoblar el Treeview."""
        if not self._columna:
            return
        hijos = list(self._tree.get_children(""))
        con_valor = []
        sin_valor = []
        for posicion, item_id in enumerate(hijos):
            valor = self._tree.set(item_id, self._columna)
            if str(valor or "").strip():
                con_valor.append((clave_orden_treeview(valor), posicion, item_id))
            else:
                sin_valor.append((posicion, item_id))
        con_valor.sort(key=lambda item: item[0], reverse=self._descendente)
        ordenados = [item[2] for item in con_valor]
        ordenados.extend(item[1] for item in sin_valor)
        for posicion, item_id in enumerate(ordenados):
            self._tree.move(item_id, "", posicion)

    def _actualizar_cabeceras(self) -> None:
        for columna, titulo in self._titulos.items():
            indicador = ""
            if columna == self._columna:
                indicador = " \u25bc" if self._descendente else " \u25b2"
            self._tree.heading(
                columna,
                text=f"{titulo}{indicador}",
                command=lambda key=columna: self.ordenar(key),
            )
