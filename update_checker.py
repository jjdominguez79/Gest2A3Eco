"""
Modulo de comprobacion y gestion de actualizaciones automaticas para Gest2A3Eco.

Flujo de uso:
    1. Llamar a check_for_updates(root) justo despues de crear la ventana Tk principal,
       pero ANTES de root.mainloop().
    2. Si retorna False, llamar a root.destroy() y salir.
    3. Si retorna True, continuar el arranque normal de la app.

El archivo remoto version.json debe tener esta estructura:
    {
        "latest_version":           "1.0.1",
        "minimum_required_version": "1.0.1",
        "download_url":             "https://servidor.com/.../Setup_Gest2A3Eco_1.0.1.exe",
        "changelog":                "Texto con las mejoras",
        "force_update":             true
    }
"""
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import traceback
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk
from typing import Callable, Optional

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

try:
    from packaging.version import Version
    _HAS_PACKAGING = True
except ImportError:
    _HAS_PACKAGING = False

from app_version import APP_VERSION, UPDATE_CHECK_URL
log = logging.getLogger(__name__)
_diag_log = logging.getLogger("update_checker.diagnostic")

_TIMEOUT_CHECK = 5    # segundos para consultar version.json
_TIMEOUT_DL    = 120  # segundos maximo para descargar el instalador

# Paleta coherente con el tema de la aplicacion (ui_theme.py)
_C_PRIMARY  = "#002C57"
_C_WHITE    = "#ffffff"
_C_BG       = "#f5f5f5"
_C_MUTED    = "#6c757d"
_C_DANGER   = "#c0392b"
_C_DANGER_H = "#a93226"
_C_OK       = "#27ae60"
_C_OK_H     = "#219150"
_FONT       = "Segoe UI"
_UPDATE_LOG_FILE = "update_checker.log"


def _get_diag_log_path() -> Path:
    root = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    path = root / "Gestinem" / "Gest2A3Eco" / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path / _UPDATE_LOG_FILE


def _ensure_diag_logger() -> logging.Logger:
    if _diag_log.handlers:
        return _diag_log

    log_path = _get_diag_log_path()
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        "%Y-%m-%d %H:%M:%S",
    ))
    _diag_log.setLevel(logging.INFO)
    _diag_log.addHandler(handler)
    _diag_log.propagate = False
    return _diag_log


def _diag_info(message: str, *args) -> None:
    _ensure_diag_logger().info(message, *args)


def _diag_exception(message: str, exc: BaseException) -> None:
    _ensure_diag_logger().error(
        "%s\n%s",
        message,
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )


# ---------------------------------------------------------------------------
# Modelo de datos
# ---------------------------------------------------------------------------

@dataclass
class _UpdateInfo:
    latest_version: str
    minimum_required_version: str
    download_url: str
    changelog: str
    force_update: bool


# ---------------------------------------------------------------------------
# Logica de red
# ---------------------------------------------------------------------------

def _fetch_info(url: str) -> Optional[_UpdateInfo]:
    """Descarga y parsea el archivo version.json remoto. Retorna None ante cualquier error."""
    _diag_info("---- Inicio comprobacion de actualizaciones ----")
    _diag_info("APP_VERSION local: %s", APP_VERSION)
    _diag_info("UPDATE_CHECK_URL: %s", url)

    if not _HAS_REQUESTS:
        log.warning("Libreria 'requests' no disponible; omitiendo comprobacion de actualizaciones.")
        _diag_info("requests disponible: no")
        return None

    _diag_info("requests disponible: si")
    try:
        resp = requests.get(url, timeout=_TIMEOUT_CHECK)
        _diag_info(
            "Respuesta HTTP: %s %s | headers=%s",
            resp.status_code,
            resp.reason,
            dict(resp.headers),
        )
        resp.raise_for_status()
        _diag_info("Contenido recibido de version.json: %s", resp.text)
        data = resp.json()
        info = _UpdateInfo(
            latest_version           = str(data["latest_version"]),
            minimum_required_version = str(data["minimum_required_version"]),
            download_url             = str(data["download_url"]),
            changelog                = str(data.get("changelog", "")),
            force_update             = bool(data.get("force_update", False)),
        )
        _diag_info("latest_version: %s", info.latest_version)
        _diag_info("minimum_required_version: %s", info.minimum_required_version)
        _diag_info("force_update remoto: %s", info.force_update)
        return info
    except requests.exceptions.ConnectionError as exc:
        log.info("Sin conexion a internet; omitiendo comprobacion de actualizaciones.")
        _diag_exception("Sin conexion a internet al consultar version.json.", exc)
    except requests.exceptions.Timeout as exc:
        log.warning("Timeout al consultar version.json.")
        _diag_exception("Timeout al consultar version.json.", exc)
    except (requests.exceptions.HTTPError, json.JSONDecodeError, KeyError, ValueError) as exc:
        log.warning("Respuesta invalida de version.json: %s", exc)
        _diag_exception("Respuesta invalida al consultar version.json.", exc)
    except Exception as exc:
        log.error("Error inesperado en comprobacion de actualizaciones: %s", exc)
        _diag_exception("Error inesperado en comprobacion de actualizaciones.", exc)
    return None


def _cmp(current: str, target: str) -> int:
    """Compara dos cadenas de version semantica. Retorna -1/0/1."""
    if not _HAS_PACKAGING:
        return 0
    try:
        a, b = Version(current), Version(target)
        return 0 if a == b else (-1 if a < b else 1)
    except Exception:
        return 0


def _download_background(
    url: str,
    dest: Path,
    on_progress: Callable[[int], None],
    on_error: Callable[[str], None],
    on_done: Callable[[], None],
) -> None:
    """Descarga 'url' en 'dest' en un hilo daemon. Los callbacks son llamados desde el hilo."""
    def _run():
        if not _HAS_REQUESTS:
            on_error("La libreria 'requests' no esta instalada.")
            return
        try:
            with requests.get(url, stream=True, timeout=_TIMEOUT_DL) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                done  = 0
                with dest.open("wb") as f:
                    for chunk in resp.iter_content(65_536):
                        if chunk:
                            f.write(chunk)
                            done += len(chunk)
                            if total:
                                on_progress(min(99, int(done * 100 / total)))
            on_progress(100)
            on_done()
        except requests.exceptions.ConnectionError:
            on_error("Sin conexion a internet.")
        except requests.exceptions.Timeout:
            on_error("Tiempo de espera agotado durante la descarga.")
        except requests.exceptions.HTTPError as exc:
            on_error(f"Error del servidor ({exc.response.status_code}).")
        except PermissionError:
            on_error("Sin permisos de escritura en la carpeta temporal.")
        except OSError as exc:
            on_error(f"Error de disco: {exc}")
        except Exception as exc:
            on_error(f"Error inesperado: {exc}")

    threading.Thread(target=_run, daemon=True).start()


def _run_installer(path: Path) -> None:
    """Lanza el instalador .exe y termina la aplicacion actual. Si falla, solo registra el error."""
    launched = False
    try:
        subprocess.Popen(
            [str(path)],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        launched = True
    except PermissionError:
        # Intentar con elevacion de privilegios UAC
        try:
            import ctypes
            ret = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
                None, "runas", str(path), None, None, 1
            )
            launched = int(ret) > 32
        except Exception as exc:
            log.error("ShellExecuteW fallido: %s", exc)
    except FileNotFoundError:
        log.error("Instalador no encontrado: %s", path)
    except Exception as exc:
        log.error("No se pudo ejecutar el instalador: %s", exc)

    if launched:
        sys.exit(0)
    log.error("El instalador no pudo ejecutarse. Ruta: %s", path)


# ---------------------------------------------------------------------------
# Dialogo Tkinter de actualizacion
# ---------------------------------------------------------------------------

class _UpdateDialog(tk.Toplevel):
    """Ventana modal de actualizacion. Compatible con Tkinter antes de mainloop()."""

    def __init__(self, parent: tk.Tk, info: _UpdateInfo, mandatory: bool):
        super().__init__(parent)
        self._info      = info
        self._mandatory = mandatory
        self.installed  = False          # True tras iniciar instalacion con exito
        self._dest: Optional[Path] = None
        self._parent_withdrawn = str(parent.state()) == "withdrawn"

        self.title("Actualizacion — Gest2A3Eco")
        self.resizable(False, False)
        if not self._parent_withdrawn:
            self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build()
        self._center(parent)
        self.lift()
        if self._parent_withdrawn:
            # Cuando root esta oculto, el dialogo necesita forzarse al frente o
            # puede quedar sin foco aparente mientras wait_window() bloquea.
            self.attributes("-topmost", True)
            self.after(250, lambda: self.attributes("-topmost", False))
        self.focus_force()
        _diag_info(
            "Dialogo de actualizacion creado. parent_withdrawn=%s mandatory=%s",
            self._parent_withdrawn,
            self._mandatory,
        )

    # ── Construccion de la interfaz ──────────────────────────────────────

    def _build(self):
        mandatory = self._mandatory

        # Banda superior de color
        tk.Frame(self, bg=_C_PRIMARY, height=4).pack(fill="x")

        # Cabecera
        hdr = tk.Frame(self, bg=_C_PRIMARY, padx=22, pady=14)
        hdr.pack(fill="x")
        hdr_text = "Actualizacion obligatoria" if mandatory else "Nueva version disponible"
        tk.Label(
            hdr, text=hdr_text,
            bg=_C_PRIMARY, fg=_C_WHITE,
            font=(_FONT, 14, "bold"), anchor="w",
        ).pack(fill="x")

        # Cuerpo principal
        body = tk.Frame(self, bg=_C_BG, padx=22, pady=16)
        body.pack(fill="both", expand=True)

        # Informacion de versiones
        tk.Label(
            body, text=f"Version instalada:   {APP_VERSION}",
            bg=_C_BG, fg=_C_MUTED, font=(_FONT, 9), anchor="w",
        ).pack(anchor="w")
        tk.Label(
            body, text=f"Nueva version:         {self._info.latest_version}",
            bg=_C_BG, fg=_C_PRIMARY, font=(_FONT, 11, "bold"), anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        if mandatory:
            tk.Label(
                body,
                text="Es necesario actualizar para continuar usando la aplicacion.",
                bg=_C_BG, fg=_C_DANGER, font=(_FONT, 9, "bold"),
                anchor="w", wraplength=460,
            ).pack(anchor="w", pady=(6, 0))

        # Separador
        tk.Frame(body, bg="#d0d0d0", height=1).pack(fill="x", pady=10)

        # Changelog
        if self._info.changelog.strip():
            tk.Label(
                body, text="Novedades de esta version:",
                bg=_C_BG, fg=_C_PRIMARY, font=(_FONT, 9, "bold"), anchor="w",
            ).pack(anchor="w")
            txt = tk.Text(
                body, height=5, wrap="word",
                bg="#eef2f7", fg="#333333", font=(_FONT, 9),
                relief="flat", padx=10, pady=6,
                borderwidth=0, highlightthickness=0,
            )
            txt.insert("1.0", self._info.changelog)
            txt.config(state="disabled")
            txt.pack(fill="x", pady=(4, 10))

        # Barra de progreso (oculta inicialmente)
        self._pf = tk.Frame(body, bg=_C_BG)
        self._plbl = tk.Label(self._pf, text="", bg=_C_BG, fg=_C_MUTED, font=(_FONT, 8))
        self._plbl.pack(anchor="w")
        self._pvar = tk.IntVar(value=0)
        self._pbar = ttk.Progressbar(
            self._pf, variable=self._pvar, maximum=100,
            mode="determinate", length=460,
        )
        self._pbar.pack(fill="x", pady=(2, 4))

        # Etiqueta de error
        self._elbl = tk.Label(
            body, text="", bg=_C_BG, fg=_C_DANGER,
            font=(_FONT, 9), wraplength=460, anchor="w",
        )
        self._elbl.pack(anchor="w", pady=(0, 4))

        # Fila de botones
        brow = tk.Frame(body, bg=_C_BG)
        brow.pack(fill="x", pady=(8, 0))

        self._btn_ok = tk.Button(
            brow, text="Descargar e instalar",
            command=self._on_download,
            bg=_C_OK, fg=_C_WHITE, font=(_FONT, 10, "bold"),
            relief="flat", padx=16, pady=8, cursor="hand2",
            activebackground=_C_OK_H, activeforeground=_C_WHITE,
        )
        self._btn_ok.pack(side="left", padx=(0, 8))

        self._btn_cancel = tk.Button(
            brow,
            text="Salir" if mandatory else "Ahora no",
            command=self._on_close,
            bg=_C_DANGER if mandatory else "#888888",
            fg=_C_WHITE, font=(_FONT, 10),
            relief="flat", padx=16, pady=8, cursor="hand2",
            activebackground=_C_DANGER_H if mandatory else "#666666",
            activeforeground=_C_WHITE,
        )
        self._btn_cancel.pack(side="left")

    def _center(self, parent: tk.Tk):
        self.update_idletasks()
        w  = 520
        h  = self.winfo_reqheight()
        sw = parent.winfo_screenwidth()
        sh = parent.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    # ── Acciones ──────────────────────────────────────────────────────────

    def _on_download(self):
        _diag_info("Usuario ha pulsado 'Descargar e instalar'.")
        self._btn_ok.config(state="disabled")
        self._btn_cancel.config(state="disabled")
        self._elbl.config(text="")

        self._dest = (
            Path(tempfile.gettempdir())
            / f"Setup_Gest2A3Eco_{self._info.latest_version}.exe"
        )

        self._pf.pack(fill="x", pady=(0, 4), before=self._elbl)
        self._plbl.config(text="Preparando descarga...")
        self._pvar.set(0)

        _download_background(
            url       = self._info.download_url,
            dest      = self._dest,
            on_progress = lambda p: self.after(0, self._set_progress, p),
            on_error    = lambda m: self.after(0, self._show_error, m),
            on_done     = lambda:   self.after(0, self._on_done),
        )

    def _set_progress(self, pct: int):
        self._pvar.set(pct)
        self._plbl.config(text=f"Descargando actualizacion... {pct}%")

    def _show_error(self, msg: str):
        self._pf.pack_forget()
        self._elbl.config(text=f"Error en la descarga: {msg}")
        self._btn_ok.config(state="normal")
        self._btn_cancel.config(state="normal")
        log.error("Error al descargar actualizacion: %s", msg)
        _diag_info("Error mostrado en el dialogo de actualizacion: %s", msg)

    def _on_done(self):
        self._plbl.config(text="Descarga completa. Iniciando instalacion...")
        self.installed = True
        _diag_info("Descarga completada; cerrando dialogo para lanzar instalador.")
        self.after(1200, self.destroy)

    def _on_close(self):
        _diag_info(
            "Dialogo de actualizacion cerrado. mandatory=%s installed=%s",
            self._mandatory,
            self.installed,
        )
        self.destroy()


# ---------------------------------------------------------------------------
# Punto de entrada publico
# ---------------------------------------------------------------------------

def check_for_updates(root: tk.Tk) -> bool:
    """
    Comprueba actualizaciones y muestra un dialogo modal si procede.

    Debe llamarse despues de crear la ventana root (puede estar retirada con
    root.withdraw()) pero ANTES de root.mainloop().

    Retorna:
        True  — la aplicacion debe continuar iniciandose normalmente.
        False — la aplicacion debe cerrarse (actualizacion en curso o rechazada
                en modo obligatorio). El llamador debe hacer root.destroy().
    """
    if not (_HAS_REQUESTS and _HAS_PACKAGING):
        log.warning("'requests' o 'packaging' no disponibles; omitiendo actualizaciones.")
        _diag_info("'requests' o 'packaging' no disponibles; no se comprueban actualizaciones.")
        return True

    log.info("Comprobando actualizaciones: %s", UPDATE_CHECK_URL)
    info = _fetch_info(UPDATE_CHECK_URL)

    if info is None:
        _diag_info("Decision final: no mostrar dialogo (sin informacion remota valida).")
        return True  # Sin conexion o error no critico; continuar

    cmp_min = _cmp(APP_VERSION, info.minimum_required_version)
    cmp_lat = _cmp(APP_VERSION, info.latest_version)
    mandatory = cmp_min < 0 or info.force_update

    _diag_info("Resultado de la comparacion con minimum_required_version: %s", cmp_min)
    _diag_info("Resultado de la comparacion con latest_version: %s", cmp_lat)
    _diag_info("mandatory: %s", mandatory)

    if cmp_min >= 0 and cmp_lat >= 0:
        log.info("Aplicacion actualizada (v%s).", APP_VERSION)
        _diag_info("Si se decide mostrar o no el dialogo: no")
        return True

    _diag_info("Si se decide mostrar o no el dialogo: si")
    log.info(
        "Actualizacion %s disponible: v%s -> v%s",
        "obligatoria" if mandatory else "opcional",
        APP_VERSION, info.latest_version,
    )

    _diag_info("Entrando en wait_window() del dialogo de actualizacion.")
    dlg = _UpdateDialog(root, info, mandatory=mandatory)
    root.wait_window(dlg)
    _diag_info(
        "wait_window() finalizado. installed=%s dest=%s",
        dlg.installed,
        dlg._dest,
    )

    if dlg.installed and dlg._dest and dlg._dest.exists():
        _run_installer(dlg._dest)   # llama sys.exit(0) si el lanzamiento tiene exito
        return False                # si _run_installer retorna, el lanzamiento fallo

    if mandatory:
        return False  # usuario cerro el dialogo en modo obligatorio

    return True  # actualizacion opcional rechazada; continuar
