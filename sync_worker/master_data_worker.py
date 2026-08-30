"""Replica datos maestros de Gest2A3Eco hacia la plataforma de clientes.

El flujo es exclusivamente PostgreSQL del escritorio -> API del backend.
Este proceso no acepta ni aplica cambios procedentes de Flutter.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
from dataclasses import dataclass
from pathlib import Path

import psycopg
import requests
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from sync_worker.config import _required, _secret


LOG = logging.getLogger("gest2a3eco.master_data_sync")


@dataclass(frozen=True)
class MasterDataConfig:
    api_url: str
    api_token: str
    postgres_dsn: str
    interval_seconds: int
    online_series_code: str

    @classmethod
    def from_environment(cls) -> "MasterDataConfig":
        interval = int(os.environ.get("CLIENT_MASTER_SYNC_INTERVAL_SECONDS", "300"))
        if interval < 60:
            raise ValueError("CLIENT_MASTER_SYNC_INTERVAL_SECONDS no puede ser inferior a 60")
        return cls(
            api_url=_required("CLIENT_MASTER_SYNC_API_URL").rstrip("/"),
            api_token=_secret("CLIENT_MASTER_SYNC_TOKEN_FILE"),
            postgres_dsn=make_conninfo(
                host=_required("POSTGRES_HOST"),
                port=int(os.environ.get("POSTGRES_PORT", "5432")),
                dbname=_required("POSTGRES_DB"),
                user=_required("POSTGRES_USER"),
                password=_secret("POSTGRES_PASSWORD_FILE"),
                connect_timeout=10,
                application_name="gest2a3eco-master-data-sync",
            ),
            interval_seconds=interval,
            online_series_code=(
                os.environ.get("CLIENT_ONLINE_SERIES_CODE", "APP").strip().upper()
                or "APP"
            )[:10],
        )


class MasterDataWorker:
    def __init__(self, config: MasterDataConfig, session=None) -> None:
        self.config = config
        self.http = session or requests.Session()
        self.stop_event = threading.Event()

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.config.api_token, "Connection": "close"}

    def _url(self, path: str) -> str:
        return f"{self.config.api_url}/api/v1/messaging/client{path}"

    def _load_companies(self) -> list[dict]:
        with psycopg.connect(self.config.postgres_dsn, row_factory=dict_row) as conn:
            return list(conn.execute(
                """
                SELECT e.codigo,e.ejercicio,e.nombre,e.activo,e.cif,e.direccion,
                       e.cp,e.poblacion,e.provincia,e.pais,e.telefono,e.email
                FROM empresas e
                JOIN (
                  SELECT codigo,MAX(ejercicio) ejercicio
                  FROM empresas GROUP BY codigo
                ) latest ON latest.codigo=e.codigo AND latest.ejercicio=e.ejercicio
                ORDER BY e.codigo
                """
            ).fetchall())

    def _load_customers(self, company_code: str) -> list[dict]:
        with psycopg.connect(self.config.postgres_dsn, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT ON (t.id)
                       t.id,t.nif,COALESCE(NULLIF(t.nombre_legal,''),t.nombre) legal_name,
                       t.direccion,COALESCE(NULLIF(t.codigo_postal,''),t.cp) postal_code,
                       t.poblacion,t.provincia,t.pais,t.email,t.telefono,t.activo,
                       te.subcuenta_cliente,te.ejercicio
                FROM terceros_empresas te
                JOIN terceros t ON t.id=te.tercero_id
                WHERE te.codigo_empresa=%s
                  AND COALESCE(TRIM(te.subcuenta_cliente),'') LIKE '430%%'
                ORDER BY t.id,te.ejercicio DESC
                """,
                (company_code,),
            ).fetchall()
        return [{
            "tax_id": row["nif"] or "",
            "legal_name": row["legal_name"] or "",
            "address": row["direccion"] or "",
            "postal_code": row["postal_code"] or "",
            "city": row["poblacion"] or "",
            "province": row["provincia"] or "",
            "country": row["pais"] or "ES",
            "email": row["email"] or "",
            "phone": row["telefono"] or "",
            "active": bool(row["activo"] if row["activo"] is not None else True),
            "desktop_tercero_id": str(row["id"]),
            "desktop_subcuenta": row["subcuenta_cliente"] or "",
        } for row in rows if str(row["nif"] or "").strip()]

    def run_once(self) -> dict[str, int]:
        companies = self._load_companies()
        customer_count = 0
        for company in companies:
            code = str(company["codigo"] or "").strip().upper()
            if not code:
                continue
            profile = {
                "company_code": code,
                "name": company["nombre"] or code,
                "legal_name": company["nombre"] or code,
                "tax_id": company["cif"] or "",
                "address": company["direccion"] or "",
                "postal_code": company["cp"] or "",
                "city": company["poblacion"] or "",
                "province": company["provincia"] or "",
                "country": company["pais"] or "ES",
                "phone": company["telefono"] or "",
                "email": company["email"] or "",
                "active": bool(
                    company["activo"] if company["activo"] is not None else True
                ),
            }
            response = self.http.put(
                self._url("/internal/sync-profile"),
                headers=self._headers,
                json=profile,
                timeout=30,
            )
            response.raise_for_status()
            org_id = str(response.json().get("organization_id") or "")
            if not org_id:
                raise RuntimeError(f"El backend no devolvio organization_id para {code}")

            customers = self._load_customers(code)
            response = self.http.post(
                self._url("/invoicing/worker/customer-sync"),
                headers=self._headers,
                json={
                    "organization_id": org_id,
                    "customers": customers,
                    "full_snapshot": True,
                },
                timeout=90,
            )
            response.raise_for_status()
            customer_count += len(customers)

            response = self.http.post(
                self._url("/invoicing/worker/series-sync"),
                headers=self._headers,
                json={
                    "organization_id": org_id,
                    "fiscal_year": int(company["ejercicio"]),
                    "series_code": self.config.online_series_code,
                    "description": "FACTURAS EMITIDAS DESDE FLUTTER",
                    "active": bool(profile["active"]),
                },
                timeout=30,
            )
            response.raise_for_status()

        result = {"companies": len(companies), "customers": customer_count}
        LOG.info("Sincronizacion maestra completada: %s", result)
        return result

    def run_forever(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                LOG.exception("Fallo la sincronizacion maestra")
            self.stop_event.wait(self.config.interval_seconds)

    def stop(self, *_args) -> None:
        self.stop_event.set()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    worker = MasterDataWorker(MasterDataConfig.from_environment())
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    LOG.info(
        "Iniciando sincronizador maestro cada %d segundos; serie=%s",
        worker.config.interval_seconds,
        worker.config.online_series_code,
    )
    worker.run_forever()


if __name__ == "__main__":
    main()
