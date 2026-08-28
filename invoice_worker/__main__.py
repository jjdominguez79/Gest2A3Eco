"""Punto de entrada del worker de facturacion online.

Incluye:
- Bloqueo de instancia unica (mutex Windows / lockfile)
- Rotacion de logs
- Comprobaciones de arranque
- Apagado controlado
"""

from __future__ import annotations

import argparse
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


def _dry_run(config: WorkerConfig) -> None:
    """Comprueba configuracion, credenciales, Word, plantilla, PostgreSQL
    y backend sin procesar ninguna factura. Sale con codigo 0 si todo OK,
    1 si hay errores criticos."""
    errors = []
    warnings_list = []

    print("=== DRY-RUN: Comprobacion de configuracion del worker ===\n")

    # 1. Token API
    if config.api_token:
        print("[OK] Token API configurado")
    else:
        errors.append("Token API no configurado (Credential Manager: Gest2A3Eco/WorkstationToken)")

    # 2. DSN PostgreSQL
    if config.desktop_dsn:
        print("[OK] DSN PostgreSQL configurado")
        try:
            import psycopg
            with psycopg.connect(config.desktop_dsn, connect_timeout=5) as conn:
                conn.execute("SELECT 1")
            print("[OK] Conexion PostgreSQL establecida")
        except Exception as exc:
            errors.append(f"Error conectando a PostgreSQL: {exc}")
    else:
        errors.append("DSN PostgreSQL no configurado (Credential Manager: Gest2A3Eco/PostgreSQL)")

    # 3. Word COM (solo Windows)
    if sys.platform == "win32":
        try:
            import comtypes.client
            word = comtypes.client.CreateObject("Word.Application")
            word.Quit()
            print("[OK] Microsoft Word COM disponible")
        except Exception as exc:
            errors.append(f"Microsoft Word COM no disponible: {exc}")
    else:
        warnings_list.append("Comprobacion de Word COM omitida (no es Windows)")

    # 4. Plantilla Word
    template_dir = Path(config.word_template_dir)
    if not template_dir.exists():
        errors.append(f"Directorio de plantillas no existe: {template_dir}")
    else:
        docx_files = list(template_dir.glob("*.docx"))
        if docx_files:
            print(f"[OK] Plantilla Word encontrada: {docx_files[0].name}")
        else:
            errors.append(f"No se encontraron plantillas .docx en {template_dir}")

    # 5. Conectividad backend (/health)
    try:
        import requests
        base = config.api_base_url.rsplit("/api/", 1)[0]
        resp = requests.get(f"{base}/health", timeout=10)
        if resp.status_code == 200:
            print(f"[OK] Backend responde en {base}/health")
        else:
            errors.append(f"Backend /health devolvio HTTP {resp.status_code}")
    except Exception as exc:
        errors.append(f"No se pudo conectar al backend: {exc}")

    # 6. Autenticacion con el backend (endpoint no mutante)
    if config.api_token:
        try:
            import requests
            resp = requests.get(
                f"{config.api_base_url}/worker/invoice/dry-run-check/status",
                headers={"x-api-key": config.api_token},
                timeout=10,
            )
            # 404 es esperado (ID no existe), 401/403 indica problema de auth
            if resp.status_code in (200, 404):
                print("[OK] Autenticacion con el backend correcta")
            elif resp.status_code in (401, 403):
                errors.append(f"Token API rechazado por el backend (HTTP {resp.status_code})")
            else:
                warnings_list.append(f"Backend respondio HTTP {resp.status_code} en endpoint de diagnostico")
        except Exception as exc:
            warnings_list.append(f"No se pudo verificar autenticacion: {exc}")

    # 7. Azure (via endpoint de diagnostico del backend)
    if config.api_token:
        try:
            import requests
            base_storage = config.api_base_url.replace("/invoicing", "")
            resp = requests.get(
                f"{base_storage}/documents/internal/storage-health",
                headers={"x-api-key": config.api_token},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    print(f"[OK] Almacenamiento: {data.get('backend')} ({data.get('container', data.get('path', ''))})")
                else:
                    errors.append(f"Almacenamiento no disponible: {data.get('error', 'desconocido')}")
            else:
                warnings_list.append(f"Endpoint /storage-health respondio HTTP {resp.status_code}")
        except Exception as exc:
            warnings_list.append(f"No se pudo verificar almacenamiento Azure: {exc}")

    # Resumen
    print()
    if warnings_list:
        for w in warnings_list:
            print(f"[AVISO] {w}")
    if errors:
        print()
        for e in errors:
            print(f"[ERROR] {e}")
        print(f"\nDry-run FALLIDO: {len(errors)} error(es) critico(s).")
        sys.exit(1)
    else:
        print("Dry-run EXITOSO: el worker esta listo para procesar facturas.")
        sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker de facturacion online")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verificar configuracion sin procesar facturas y salir",
    )
    args = parser.parse_args()

    # Cargar configuracion (con credential store si esta disponible)
    try:
        config = WorkerConfig.from_credential_store()
    except Exception:
        config = WorkerConfig.from_env()

    if args.dry_run:
        _dry_run(config)
        return  # _dry_run llama sys.exit(), pero por si acaso

    # Bloqueo de instancia unica
    lock = _acquire_instance_lock()
    if lock is None:
        raise SystemExit(
            "Ya existe una instancia del worker en ejecucion. "
            "Cierra la otra instancia o elimina el bloqueo."
        )

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
