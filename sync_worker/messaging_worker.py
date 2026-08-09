from __future__ import annotations

import hashlib
import logging
import os
import re
import signal
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import psycopg
import requests
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from sync_worker.config import _required, _secret


LOG = logging.getLogger("gest2a3eco.messaging_sync")


@dataclass(frozen=True)
class MessagingWorkerConfig:
    api_url: str
    sync_token: str
    repository_dir: Path
    postgres_dsn: str
    worker_id: str
    interval_seconds: int

    @classmethod
    def from_environment(cls) -> "MessagingWorkerConfig":
        interval = int(os.environ.get("MESSAGING_SYNC_INTERVAL_SECONDS", "60"))
        if interval < 30:
            raise ValueError("MESSAGING_SYNC_INTERVAL_SECONDS no puede ser inferior a 30 segundos.")
        repository = Path(_required("DOCUMENT_REPOSITORY_DIR"))
        repository.mkdir(parents=True, exist_ok=True)
        return cls(
            api_url=_required("MESSAGING_API_URL").rstrip("/"),
            sync_token=_secret("MESSAGING_SYNC_TOKEN_FILE"),
            repository_dir=repository,
            postgres_dsn=make_conninfo(
                host=_required("POSTGRES_HOST"),
                port=int(os.environ.get("POSTGRES_PORT", "5432")),
                dbname=_required("POSTGRES_DB"),
                user=_required("POSTGRES_USER"),
                password=_secret("POSTGRES_PASSWORD_FILE"),
                connect_timeout=10,
                application_name="gest2a3eco-messaging-sync",
            ),
            worker_id=os.environ.get("MESSAGING_WORKER_ID", "synology").strip() or "synology",
            interval_seconds=interval,
        )


class MessagingAttachmentWorker:
    def __init__(self, config: MessagingWorkerConfig, session=None):
        self.config = config
        self.http = session or requests.Session()
        self.stop_event = threading.Event()

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Sync-Token": self.config.sync_token}

    def _url(self, path: str) -> str:
        return f"{self.config.api_url}/api/v1/messaging{path}"

    def run_once(self) -> tuple[int, int]:
        response = self.http.get(
            self._url("/sync/attachments/pending"), headers=self._headers, timeout=30,
        )
        response.raise_for_status()
        downloaded = errors = 0
        for item in response.json():
            try:
                self._sync_one(item)
                downloaded += 1
            except Exception as exc:
                errors += 1
                LOG.exception("No se pudo sincronizar %s: %s", item.get("name"), exc)
        LOG.info("Adjuntos de mensajeria: procesados=%d errores=%d", downloaded, errors)
        return downloaded, errors

    def sync_organizations(self) -> int:
        rows = self._load_organizations()
        response = self.http.put(
            self._url("/sync/organizations"), headers=self._headers,
            json=rows, timeout=60,
        )
        response.raise_for_status()
        synchronized = int(response.json().get("synchronized") or 0)
        LOG.info("Directorio de clientes sincronizado: %d", synchronized)
        return synchronized

    def _load_organizations(self) -> list[dict]:
        with psycopg.connect(self.config.postgres_dsn, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT e.codigo,e.nombre,e.activo
                FROM empresas e
                JOIN (
                  SELECT codigo,MAX(ejercicio) ejercicio
                  FROM empresas GROUP BY codigo
                ) latest ON latest.codigo=e.codigo AND latest.ejercicio=e.ejercicio
                ORDER BY e.nombre,e.codigo
                """
            ).fetchall()
        return [{
            "company_code": str(row["codigo"] or "").strip(),
            "name": str(row["nombre"] or row["codigo"] or "").strip(),
            "active": bool(row["activo"] if row["activo"] is not None else True),
        } for row in rows if str(row["codigo"] or "").strip()]

    def _sync_one(self, item: dict) -> None:
        destination = self._destination(item)
        existing = self._existing(item["id"])
        if existing and Path(existing[0]).is_file():
            digest = self._file_hash(Path(existing[0]))
            if digest == item["sha256"]:
                self._confirm(item["id"], digest)
                return
        claimed = self.http.post(
            self._url(f"/sync/attachments/{item['id']}/claim"), headers=self._headers,
            data={"worker": self.config.worker_id}, timeout=20,
        )
        claimed.raise_for_status()
        response = self.http.get(
            self._url(f"/sync/attachments/{item['id']}/content"), headers=self._headers,
            params={"worker": self.config.worker_id}, timeout=120,
        )
        response.raise_for_status()
        content = response.content
        digest = hashlib.sha256(content).hexdigest()
        if digest != item["sha256"] or len(content) != int(item["size"]):
            raise ValueError("El hash o el tamano del adjunto no coincide.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        temporary.write_bytes(content)
        os.replace(temporary, destination)
        self._save(item, destination, digest)
        self._confirm(item["id"], digest)

    def _confirm(self, attachment_id: str, digest: str) -> None:
        response = self.http.post(
            self._url(f"/sync/attachments/{attachment_id}/confirm"), headers=self._headers,
            data={"worker": self.config.worker_id, "sha256": digest}, timeout=30,
        )
        response.raise_for_status()

    def _existing(self, attachment_id: str):
        with psycopg.connect(self.config.postgres_dsn) as conn:
            return conn.execute(
                "SELECT ruta_entrada,hash_archivo FROM mensajeria_adjuntos_entrada WHERE id=%s",
                (attachment_id,),
            ).fetchone()

    def _save(self, item: dict, path: Path, digest: str) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with psycopg.connect(self.config.postgres_dsn) as conn:
            conn.execute(
                """
                INSERT INTO mensajeria_adjuntos_entrada
                  (id,mensaje_remoto_id,conversacion_remota_id,codigo_empresa,
                   empresa_nombre,nombre_original,ruta_entrada,hash_archivo,tamano,
                   mime_type,remitente,estado,error_detalle,documento_id,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pendiente_clasificar',NULL,NULL,%s,%s)
                ON CONFLICT(id) DO UPDATE SET
                  ruta_entrada=excluded.ruta_entrada,hash_archivo=excluded.hash_archivo,
                  tamano=excluded.tamano,updated_at=excluded.updated_at,error_detalle=NULL
                """,
                (
                    item["id"], item["message_id"], item["conversation_id"],
                    item["company_code"], item.get("company_name"), item["name"],
                    str(path), digest, item["size"], item.get("content_type"),
                    item.get("author_name"), now, now,
                ),
            )

    def _destination(self, item: dict) -> Path:
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(item["name"]).name).strip(". ") or "adjunto"
        digits = "".join(ch for ch in str(item["company_code"]) if ch.isdigit())
        company = f"E{digits.zfill(5)[:5]}"
        return self.config.repository_dir / "Entrada" / "Mensajeria" / company / f"{item['id']}_{safe}"

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def run_forever(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.sync_organizations()
            except Exception as exc:
                LOG.exception("Fallo al sincronizar el directorio de clientes: %s", exc)
            try:
                self.run_once()
            except Exception as exc:
                LOG.exception("Fallo del sincronizador de mensajeria: %s", exc)
            self.stop_event.wait(self.config.interval_seconds)

    def stop(self, *_args) -> None:
        self.stop_event.set()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    worker = MessagingAttachmentWorker(MessagingWorkerConfig.from_environment())
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    LOG.info("Iniciando sincronizador de adjuntos cada %d segundos", worker.config.interval_seconds)
    worker.run_forever()


if __name__ == "__main__":
    main()
