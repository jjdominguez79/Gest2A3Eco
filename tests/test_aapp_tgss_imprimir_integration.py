"""Prueba local del flujo Imprimir; no conecta a TGSS ni usa certificados."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from playwright.sync_api import sync_playwright

from services.aapp.base import OpcionesSync
from services.aapp.certificados import obtener_proveedor


@pytest.mark.parametrize("modo", ["descarga", "inline", "popup"])
def test_imprimir_captura_pdf_con_playwright_real_en_servidor_local(tmp_path, modo):
    posts = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            target = ' target="_blank"' if modo == "popup" else ""
            body = (
                f'<form method="post" action="/documento"{target}>'
                '<button id="ENVIO_10" name="SPM.ACC.IMPRIMIR">Imprimir</button>'
                '</form>'
            ).encode("ascii")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            posts.append(self.path)
            body = b"%PDF-1.7\nprueba local de transporte"
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(body)))
            if modo == "descarga":
                self.send_header("Content-Disposition", 'attachment; filename="certificado.pdf"')
            self.end_headers()
            self.wfile.write(body)

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    hilo = Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        with sync_playwright() as playwright:
            navegador = playwright.chromium.launch(headless=True)
            contexto = navegador.new_context(accept_downloads=True)
            pagina = contexto.new_page()
            pagina.goto(f"http://127.0.0.1:{servidor.server_port}/")
            destino = tmp_path / "tgss.pdf"
            obtenido = obtener_proveedor("TGSS_CORRIENTE")._descargar_boton_tgss(
                pagina, OpcionesSync(ruta_pdf_destino=str(destino), timeout_ms=10000),
                "TGSS_CORRIENTE",
            )
            navegador.close()
        assert obtenido == str(destino)
        assert destino.read_bytes().startswith(b"%PDF-")
        assert posts == ["/documento"]
    finally:
        servidor.shutdown()
        servidor.server_close()
        hilo.join(timeout=2)
