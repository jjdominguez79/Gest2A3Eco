"""Servidor HTTP efimero para capturar el callback OAuth de Microsoft Entra.

Flujo:
  1. Se crea un servidor en 127.0.0.1 con puerto asignado por el SO.
  2. Se abre el navegador predeterminado apuntando al backend.
  3. Tras la autenticacion Microsoft, el backend redirige a
     http://127.0.0.1:{port}/auth-callback?code={code}
  4. El servidor captura el codigo, responde con HTML de confirmacion y se cierra.
"""
from __future__ import annotations

import logging
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 300  # 5 minutos maximo de espera


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handler HTTP que captura el codigo del callback."""

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/auth-callback":
            self.send_error(404)
            return
        params = parse_qs(parsed.query)
        code = (params.get("code") or [None])[0]
        error = (params.get("error") or [None])[0]

        self.server._oauth_code = code
        self.server._oauth_error = error

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        if code:
            body = (
                "<html><body style='font-family:Segoe UI,sans-serif;text-align:center;padding:40px'>"
                "<h2>Autenticacion completada</h2>"
                "<p>Puedes cerrar esta ventana y volver a Gest2A3Eco.</p>"
                "</body></html>"
            )
        else:
            body = (
                "<html><body style='font-family:Segoe UI,sans-serif;text-align:center;padding:40px'>"
                f"<h2>Error de autenticacion</h2><p>{error or 'Desconocido'}</p>"
                "</body></html>"
            )
        self.wfile.write(body.encode("utf-8"))

        # Programar el cierre del servidor tras enviar la respuesta
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, format, *args):
        # Silenciar logs del servidor HTTP
        pass


class OAuthCodeResult:
    """Resultado de la captura del codigo OAuth."""
    def __init__(self, code: str | None = None, error: str | None = None):
        self.code = code
        self.error = error

    @property
    def success(self) -> bool:
        return bool(self.code)


def run_oauth_flow(backend_url: str, timeout: int = _TIMEOUT_SECONDS) -> OAuthCodeResult:
    """
    Ejecuta el flujo OAuth completo:
    1. Inicia servidor HTTP efimero en 127.0.0.1
    2. Abre navegador hacia el endpoint de login del backend
    3. Espera el callback con el codigo
    4. Devuelve el resultado

    Args:
        backend_url: URL base del backend (ej: https://tramites.gestinem.es)
        timeout: Tiempo maximo de espera en segundos

    Returns:
        OAuthCodeResult con el codigo o error
    """
    server = HTTPServer(("127.0.0.1", 0), _OAuthCallbackHandler)
    server._oauth_code = None
    server._oauth_error = None
    server.timeout = timeout

    port = server.server_address[1]
    login_url = f"{backend_url.rstrip('/')}/api/v1/desktop/auth/login?port={port}"

    logger.info("Servidor OAuth escuchando en 127.0.0.1:%d", port)

    try:
        webbrowser.open(login_url)
    except Exception as exc:
        server.server_close()
        return OAuthCodeResult(error=f"No se pudo abrir el navegador: {exc}")

    # Servir hasta que llegue el callback o se agote el timeout
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    server_thread.join(timeout=timeout)

    if server_thread.is_alive():
        server.shutdown()
        server_thread.join(timeout=5)
        return OAuthCodeResult(error="Tiempo de espera agotado")

    server.server_close()

    if server._oauth_code:
        return OAuthCodeResult(code=server._oauth_code)
    return OAuthCodeResult(error=server._oauth_error or "No se recibio codigo de autenticacion")
