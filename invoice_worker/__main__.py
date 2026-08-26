"""Punto de entrada del worker de facturacion online.

Incluye:
- Bloqueo de instancia unica (mutex Windows / lockfile)
- Rotacion de logs
- Comprobaciones de arranque
- Apagado controlado
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from invoice_worker.config import WorkerConfig
from invoice_worker.worker import InvoiceWorker


def _acquire_instance_lock() -> object | None:
    """Intenta adquirir un bloqueo de instancia unica.

    En Windows usa un named mutex. En otros sistemas usa un lockfile.
    Devuelve el objeto de bloqueo o None si ya hay otra instancia.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            mutex = ctypes.windll.kernel32.CreateMutexW(
                None, True, "Global\\Gest2A3Eco_InvoiceWorker",
            )
            if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                ctypes.windll.kernel32.CloseHandle(mutex)
                return None
            return mutex
        except Exception:
            return True  # Si falla ctypes, continuar sin bloqueo
    else:
        lock_path = Path(__file__).parent / ".worker.lock"
        try:
            import fcntl
            lock_file = open(lock_path, "w")
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock_file.write(str(os.getpid()))
            lock_file.flush()
            return lock_file
        except (IOError, OSError):
            return None
        except ImportError:
            return True


def _setup_logging(log_dir: str) -> None:
    """Configura logging con rotacion de archivos."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Consola
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # Archivo rotativo (5 MB x 3 backups)
    file_handler = RotatingFileHandler(
        log_path / "invoice_worker.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


def _preflight_checks(config: WorkerConfig) -> list[str]:
    """Ejecuta comprobaciones previas al arranque. Devuelve advertencias."""
    warnings = []

    if not config.api_token:
        raise SystemExit(
            "Token del backend no configurado. "
            "Almacena el token en Windows Credential Manager "
            "o define INVOICE_WORKER_API_TOKEN."
        )

    if not config.desktop_dsn:
        warnings.append(
            "DSN de PostgreSQL no configurado. "
            "El worker no podra importar facturas al escritorio."
        )

    # Comprobar directorio de plantillas Word
    template_dir = Path(config.word_template_dir)
    if not template_dir.exists():
        warnings.append(
            f"Directorio de plantillas no existe: {template_dir}"
        )
    else:
        docx_files = list(template_dir.glob("*.docx"))
        if not docx_files:
            warnings.append(
                f"No se encontraron plantillas .docx en {template_dir}"
            )

    # Comprobar Word COM (solo en Windows)
    if sys.platform == "win32":
        try:
            import comtypes.client  # noqa: F401
        except ImportError:
            warnings.append(
                "comtypes no instalado; "
                "la generacion de PDF con Word COM no funcionara"
            )

    # Comprobar endpoint /health
    try:
        import requests
        base = config.api_base_url.rsplit("/api/", 1)[0]
        resp = requests.get(f"{base}/health", timeout=10)
        if resp.status_code != 200:
            warnings.append(
                f"Endpoint /health respondio con {resp.status_code}"
            )
    except Exception as e:
        warnings.append(f"No se pudo conectar al backend: {e}")

    return warnings


def main() -> None:
    # Bloqueo de instancia unica
    lock = _acquire_instance_lock()
    if lock is None:
        raise SystemExit(
            "Ya existe una instancia del worker en ejecucion. "
            "Cierra la otra instancia o elimina el bloqueo."
        )

    # Cargar configuracion (con credential store si esta disponible)
    try:
        config = WorkerConfig.from_credential_store()
    except Exception:
        config = WorkerConfig.from_env()

    # Logging con rotacion
    _setup_logging(config.log_dir)
    logger = logging.getLogger(__name__)

    # Comprobaciones previas
    warnings = _preflight_checks(config)
    for w in warnings:
        logger.warning("Comprobacion: %s", w)

    logger.info("Configuracion cargada correctamente")
    logger.info("  Backend: %s", config.api_base_url)
    logger.info("  Worker ID: %s", config.worker_id)
    logger.info("  Plantillas: %s", config.word_template_dir)
    logger.info("  PDFs: %s", config.pdf_output_dir)
    logger.info("  DSN configurado: %s", "Si" if config.desktop_dsn else "No")

    worker = InvoiceWorker(config)
    worker.run_forever()


if __name__ == "__main__":
    main()
