from __future__ import annotations

from typing import Protocol


class DgtRepository(Protocol):
    def listar_expedientes(self) -> list[dict]:
        ...

    def get_expediente(self, expediente_id: str) -> dict | None:
        ...

    def get_expediente_por_referencia(self, referencia: str) -> dict | None:
        ...

    def upsert_expediente(self, expediente: dict) -> str:
        ...

    def validar_expediente(self, expediente_id: str, user_id: int) -> None:
        ...

    def insertar_documento_generado(self, doc: dict) -> int:
        ...

    def listar_documentos_generados(self, expediente_id: str) -> list[dict]:
        ...


class SQLiteDgtRepository:
    """
    Adaptador SQLite actual para Trámites DGT.

    Mantiene el servicio desacoplado del gestor concreto para poder sustituirlo
    por una API online o un repositorio híbrido sin cambiar la UI.
    """

    def __init__(self, gestor):
        self._gestor = gestor

    def listar_expedientes(self) -> list[dict]:
        return self._gestor.listar_dgt_expedientes()

    def get_expediente(self, expediente_id: str) -> dict | None:
        return self._gestor.get_dgt_expediente(expediente_id)

    def get_expediente_por_referencia(self, referencia: str) -> dict | None:
        return self._gestor.get_dgt_expediente_por_referencia(referencia)

    def upsert_expediente(self, expediente: dict) -> str:
        return self._gestor.upsert_dgt_expediente(expediente)

    def validar_expediente(self, expediente_id: str, user_id: int) -> None:
        return self._gestor.validar_dgt_expediente(expediente_id, user_id)

    def insertar_documento_generado(self, doc: dict) -> int:
        return self._gestor.insertar_dgt_documento_generado(doc)

    def listar_documentos_generados(self, expediente_id: str) -> list[dict]:
        return self._gestor.listar_dgt_documentos_generados(expediente_id)
