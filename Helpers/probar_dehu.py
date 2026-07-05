"""
Script de prueba manual del conector DEHu (Opcion A).

Uso (desde la raiz del proyecto, con el venv activado):

    # 1a vez (recomendado): login manual para "aprender" la API del portal
    python Helpers/probar_dehu.py --pfx "C:\\ruta\\cliente.pfx" --password "****" --login-manual 120

    # ejecucion normal (headless)
    python Helpers/probar_dehu.py --pfx "C:\\ruta\\cliente.pfx" --password "****"

Opciones:
    --url https://dehu.redsara.es   URL del portal (por defecto DEHu)
    --headed                        abre el navegador con ventana
    --diagnostico                   guarda captura + HTML + JSON de la API en ./logs
    --login-manual SEG              modo aprendizaje: SEG segundos para identificarte
                                    a mano con el certificado mientras se graba la API

No toca la base de datos: valida el certificado y lanza el conector directamente.

Requisitos:  pip install cryptography playwright  &&  playwright install chromium
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.aapp.base import OpcionesSync                    # noqa: E402
from services.aapp.cert_store import CertMaterial, CertStore   # noqa: E402
from services.aapp.dehu_playwright import ConectorDEHU         # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Prueba del conector DEHu")
    ap.add_argument("--pfx", required=True, help="Ruta al certificado .pfx/.p12")
    ap.add_argument("--password", default="", help="Contrasena del certificado")
    ap.add_argument("--url", default="https://dehu.redsara.es")
    ap.add_argument("--headed", action="store_true", help="Mostrar ventana del navegador")
    ap.add_argument("--diagnostico", action="store_true", help="Guardar captura + HTML + API")
    ap.add_argument("--login-manual", type=int, default=0, metavar="SEG",
                    help="Modo aprendizaje: segundos para identificarte a mano con el "
                         "certificado mientras se graba la API (implica ventana visible).")
    args = ap.parse_args()

    if not os.path.isfile(args.pfx):
        print(f"ERROR: no existe el fichero {args.pfx}")
        return 2

    material = CertMaterial(
        cert_id="test",
        nombre=os.path.basename(args.pfx),
        nif_titular=None,
        ruta_archivo=args.pfx,
        password=args.password,
    )

    try:
        store = CertStore.__new__(CertStore)  # sin gestor: solo validar/info
        ok, msg = store.validar(material)
        print(f"[cert] {msg}")
        try:
            print(f"[cert] info: {store.info(material)}")
        except Exception as exc:
            print(f"[cert] no se pudo leer info: {exc}")
        if not ok:
            return 3
    except Exception as exc:
        print(f"[cert] aviso: validacion no disponible ({exc})")

    headed = args.headed or args.login_manual > 0
    opciones = OpcionesSync(
        headless=not headed,
        modo_diagnostico=args.diagnostico or args.login_manual > 0,
        carpeta_diagnostico=os.path.join(os.getcwd(), "logs"),
        pausa_login_segundos=args.login_manual,
        log=lambda m: print(m),
    )
    buzon = {"nombre": "Prueba DEHu", "url_portal": args.url, "organismo_codigo": "DEHU"}

    conector = ConectorDEHU(base_url=args.url)
    res = conector.sincronizar(buzon, material, opciones)
    print(f"\n[resultado] ok={res.ok}  total={res.total}  mensaje={res.mensaje}")
    for i, n in enumerate(res.notificaciones, 1):
        print(f"  {i:>3}. {n.fecha_puesta_disposicion or '----------'}  {n.asunto[:70]}")
    if not res.ok and res.error_detalle:
        print("\n[error]\n" + res.error_detalle)
    print("\nRevisa la carpeta ./logs para las capturas y los JSON de la API (dehu_api_*.json).")
    return 0 if res.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
