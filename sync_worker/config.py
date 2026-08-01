from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from psycopg.conninfo import make_conninfo


def _required(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise ValueError(f"Falta la variable obligatoria {name}.")
    return value


def _secret(path_name: str) -> str:
    path = Path(_required(path_name))
    if not path.is_file():
        raise ValueError(f"No existe el archivo secreto configurado en {path_name}: {path}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"El archivo secreto {path} esta vacio.")
    return value


@dataclass(frozen=True)
class WorkerConfig:
    tenant_id: str
    client_id: str
    mailbox: str
    certificate_path: Path
    certificate_password: str
    postgres_dsn: str
    interval_seconds: int
    import_existing_on_first_run: bool

    @classmethod
    def from_environment(cls) -> "WorkerConfig":
        interval = int(os.environ.get("SYNC_INTERVAL_SECONDS", "300"))
        if interval < 30:
            raise ValueError("SYNC_INTERVAL_SECONDS no puede ser inferior a 30 segundos.")
        certificate_path = Path(_required("GRAPH_CERTIFICATE_FILE"))
        if not certificate_path.is_file():
            raise ValueError(f"No existe el certificado privado: {certificate_path}")
        postgres_password = _secret("POSTGRES_PASSWORD_FILE")
        return cls(
            tenant_id=_required("GRAPH_TENANT_ID"),
            client_id=_required("GRAPH_CLIENT_ID"),
            mailbox=_required("GRAPH_MAILBOX").lower(),
            certificate_path=certificate_path,
            certificate_password=_secret("GRAPH_CERTIFICATE_PASSWORD_FILE"),
            postgres_dsn=make_conninfo(
                host=_required("POSTGRES_HOST"),
                port=int(os.environ.get("POSTGRES_PORT", "5432")),
                dbname=_required("POSTGRES_DB"),
                user=_required("POSTGRES_USER"),
                password=postgres_password,
                connect_timeout=10,
                application_name="gest2a3eco-mail-sync",
            ),
            interval_seconds=interval,
            import_existing_on_first_run=str(
                os.environ.get("IMPORT_EXISTING_ON_FIRST_RUN", "false")
            ).strip().lower() in {"1", "true", "yes", "si"},
        )
