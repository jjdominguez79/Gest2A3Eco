from __future__ import annotations

import hashlib
import logging
import os
import re
import signal
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath

import psycopg
import requests
from psycopg.conninfo import make_conninfo
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from sync_worker.config import _required, _secret


LOG = logging.getLogger("gest2a3eco.messaging_sync")
WORKER_VERSION = "2026.09.03.1"


@dataclass(frozen=True)
class MessagingWorkerConfig:
    api_url: str
    sync_token: str
    repository_dir: Path
    public_repository_dir: PureWindowsPath
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
            public_repository_dir=PureWindowsPath(_required("DOCUMENT_REPOSITORY_PUBLIC_DIR")),
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
        self.http = session or self._build_session()
        self.stop_event = threading.Event()

    @staticmethod
    def _build_session() -> requests.Session:
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "PUT"}),
            raise_on_status=False,
        )
        session = requests.Session()
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "X-Sync-Token": self.config.sync_token,
            "Connection": "close",
        }

    def _url(self, path: str) -> str:
        return f"{self.config.api_url}/api/v1/messaging{path}"

    def run_once(self) -> tuple[int, int]:
        LOG.info("Consultando adjuntos pendientes en el backend")
        response = self.http.get(
            self._url("/sync/attachments/pending"), headers=self._headers, timeout=30,
        )
        response.raise_for_status()
        pending = response.json()
        LOG.info("Consulta de adjuntos completada: pendientes=%d", len(pending))
        stale = [item for item in pending if item.get("stale")]
        if stale:
            LOG.warning(
                "ALERTA: %d adjunto(s) llevan mas de 1 hora sin confirmar por el NAS: %s",
                len(stale),
                ", ".join(f"{item['id']} ({item.get('name', '?')})" for item in stale),
            )
        downloaded = errors = 0
        for item in pending:
            try:
                self._sync_one(item)
                downloaded += 1
            except Exception as exc:
                errors += 1
                LOG.exception("No se pudo sincronizar %s: %s", item.get("name"), exc)
        LOG.info("Adjuntos de mensajeria: procesados=%d errores=%d", downloaded, errors)
        return downloaded, errors

    def _sync_one(self, item: dict) -> None:
        destination = self._destination(item)
        public_destination = self._public_destination(item)
        existing = self._existing(item["id"])
        if existing and destination.is_file():
            digest = self._file_hash(destination)
            if digest == item["sha256"]:
                self._save(item, public_destination, digest)
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
        self._save(item, public_destination, digest)
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

    def _save(self, item: dict, public_path: str, digest: str) -> None:
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
                    public_path, digest, item["size"], item.get("content_type"),
                    item.get("author_name"), now, now,
                ),
            )

    def _destination(self, item: dict) -> Path:
        return self.config.repository_dir.joinpath(*self._relative_destination(item))

    def _public_destination(self, item: dict) -> str:
        return str(self.config.public_repository_dir.joinpath(*self._relative_destination(item)))

    @staticmethod
    def _relative_destination(item: dict) -> tuple[str, ...]:
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(item["name"]).name).strip(". ") or "adjunto"
        digits = "".join(ch for ch in str(item["company_code"]) if ch.isdigit())
        company = f"E{digits.zfill(5)[:5]}"
        return "Entrada", "Mensajeria", company, f"{item['id']}_{safe}"

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def run_forever(self) -> None:
        while not self.stop_event.is_set():
            LOG.info("Iniciando ciclo de sincronizacion")
            try:
                self.run_once()
            except Exception as exc:
                LOG.exception("Fallo del sincronizador de mensajeria: %s", exc)
            LOG.info(
                "Ciclo finalizado; siguiente consulta en %d segundos",
                self.config.interval_seconds,
            )
            self.stop_event.wait(self.config.interval_seconds)

    def stop(self, *_args) -> None:
        self.stop_event.set()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    worker = MessagingAttachmentWorker(MessagingWorkerConfig.from_environment())
    LOG.info("Iniciando sincronizador de mensajeria version=%s", WORKER_VERSION)
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    LOG.info("Iniciando sincronizador de adjuntos cada %d segundos", worker.config.interval_seconds)
    worker.run_forever()


if __name__ == "__main__":
    main()
